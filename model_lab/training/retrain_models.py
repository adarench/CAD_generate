"""
Model Retraining Pipeline — model_lab Phase 10

Retrains graph prior (and optionally strategy rankers) using the merged
dataset produced by merge_datasets.py. Supports versioning, comparison
against existing models, and auto-generated training reports.

Models retrained:
  - graph_prior          (primary continuous-learning target)
  - pre_strategy_ranker  (optional — controlled by --no-ranker flag)

Model versioning:
  Versioned copies saved as graph_prior_v{N}.pkl alongside current model.
  Version registry maintained in model_lab/models/versions.json.

Usage:
    python -m model_lab.training.retrain_models [options]

    Options:
      --dataset <path>       Dataset JSONL (default: merged_graph_training.jsonl;
                             falls back to graph_training.jsonl)
      --no-merge             Skip dataset merge step (use existing merged dataset)
      --include-experience   Pass to merge step: include production experiences
      --no-ranker            Skip pre_strategy_ranker retraining
      --dry-run              Evaluate only; do not save new models
      --verbose

No production code is imported.
"""

from __future__ import annotations

import argparse
import json
import pickle
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

MODELS_DIR   = REPO_ROOT / "model_lab" / "models"
DATASETS_DIR = REPO_ROOT / "model_lab" / "datasets"

MERGED_PATH      = DATASETS_DIR / "merged_graph_training.jsonl"
SYNTHETIC_PATH   = DATASETS_DIR / "graph_training.jsonl"
CURRENT_MODEL    = MODELS_DIR / "graph_prior.pkl"
VERSIONS_FILE    = MODELS_DIR / "versions.json"


# ---------------------------------------------------------------------------
# Version registry
# ---------------------------------------------------------------------------

def _load_versions() -> List[Dict]:
    if VERSIONS_FILE.exists():
        with open(VERSIONS_FILE) as f:
            return json.load(f)
    return []


def _save_versions(versions: List[Dict]) -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    with open(VERSIONS_FILE, "w") as f:
        json.dump(versions, f, indent=2)


def _next_version_number() -> int:
    versions = _load_versions()
    if not versions:
        return 2    # v1 is the original baseline
    return max(v.get("version", 1) for v in versions) + 1


def _register_version(
    version_n:  int,
    model_path: Path,
    metrics:    Dict,
    dataset_n:  int,
    dataset_sources: Dict,
    model_name: str,
    notes:      str = "",
) -> None:
    versions = _load_versions()
    versions.append({
        "version":         version_n,
        "model_path":      str(model_path.relative_to(REPO_ROOT)),
        "timestamp":       datetime.now(timezone.utc).isoformat(),
        "model_name":      model_name,
        "dataset_size":    dataset_n,
        "dataset_sources": dataset_sources,
        "metrics":         metrics,
        "notes":           notes,
    })
    _save_versions(versions)


# ---------------------------------------------------------------------------
# Model evaluation helpers  (reuse from train_graph_prior)
# ---------------------------------------------------------------------------

from model_lab.training.train_graph_prior import (
    load_dataset,
    records_to_arrays,
    parcel_split,
    top_k_score_retention,
    ranking_accuracy,
)


def evaluate_model(
    model,
    records: List[Dict],
    X: np.ndarray,
    y: np.ndarray,
    test_idx: List[int],
) -> Dict[str, float]:
    """Evaluate a model on the test split and return metrics."""
    from sklearn.metrics import r2_score

    X_test   = X[test_idx]
    y_test   = y[test_idx]
    rec_test = [records[i] for i in test_idx]

    preds  = model.predict(X_test)
    r2     = r2_score(y_test, preds)
    ret5   = top_k_score_retention(rec_test, preds, k=5)
    ret10  = top_k_score_retention(rec_test, preds, k=10)
    rank   = ranking_accuracy(rec_test, preds)

    return {
        "r2_test":          round(float(r2), 4),
        "top5_retention":   round(float(ret5), 4),
        "top10_retention":  round(float(ret10), 4),
        "rank_accuracy":    round(float(rank), 4),
        "n_test":           len(test_idx),
    }


def load_current_model_metrics() -> Optional[Dict]:
    """Load metrics from the currently saved model, if any."""
    if not CURRENT_MODEL.exists():
        return None
    try:
        with open(CURRENT_MODEL, "rb") as f:
            payload = pickle.load(f)
        return {
            "r2_test":        payload.get("r2_test", 0.0),
            "top5_retention": payload.get("ret5", 0.0),
            "model_name":     payload.get("model_name", "unknown"),
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Retraining — graph prior
# ---------------------------------------------------------------------------

def retrain_graph_prior(
    records:   List[Dict],
    verbose:   bool = True,
) -> Tuple[Any, str, Dict, np.ndarray, np.ndarray, List[int]]:
    """
    Retrain the graph prior model.

    Returns:
        (model, model_name, metrics, X, y, test_idx)
    """
    from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
    from sklearn.metrics import r2_score

    t0 = time.perf_counter()
    X, y, feat_names = records_to_arrays(records)
    train_idx, test_idx = parcel_split(records, seed=42)

    X_train, y_train = X[train_idx], y[train_idx]
    X_test,  y_test  = X[test_idx],  y[test_idx]
    rec_test = [records[i] for i in test_idx]

    if verbose:
        print(f"  Train: {len(train_idx)}  Test: {len(test_idx)}  "
              f"Features: {X.shape[1]}")

    # GradientBoosting
    gb = GradientBoostingRegressor(
        n_estimators=200, max_depth=5, learning_rate=0.08,
        subsample=0.8, min_samples_leaf=5, random_state=42,
    )
    gb.fit(X_train, y_train)
    gb_preds = gb.predict(X_test)
    gb_r2    = float(r2_score(y_test, gb_preds))

    # RandomForest
    rf = RandomForestRegressor(
        n_estimators=200, max_depth=12, min_samples_leaf=3,
        random_state=42, n_jobs=-1,
    )
    rf.fit(X_train, y_train)
    rf_preds = rf.predict(X_test)
    rf_r2    = float(r2_score(y_test, rf_preds))

    # Select best
    if gb_r2 >= rf_r2:
        primary, primary_name, primary_preds = gb, "GradientBoosting", gb_preds
    else:
        primary, primary_name, primary_preds = rf, "RandomForest",     rf_preds

    elapsed = time.perf_counter() - t0
    metrics = evaluate_model(primary, records, X, y, test_idx)
    metrics["gb_r2"]    = round(gb_r2, 4)
    metrics["rf_r2"]    = round(rf_r2, 4)
    metrics["train_sec"] = round(elapsed, 1)

    if verbose:
        print(f"\n  {'Model':20}  {'R²':>6}  {'Top-5':>7}  {'Top-10':>7}  {'RankAcc':>8}")
        print(f"  {'─'*56}")
        gb_m = evaluate_model(gb, records, X, y, test_idx)
        rf_m = evaluate_model(rf, records, X, y, test_idx)
        print(f"  {'GradientBoosting':20}  {gb_m['r2_test']:6.4f}  "
              f"{gb_m['top5_retention']:7.1%}  {gb_m['top10_retention']:7.1%}  "
              f"{gb_m['rank_accuracy']:8.1%}")
        print(f"  {'RandomForest':20}  {rf_m['r2_test']:6.4f}  "
              f"{rf_m['top5_retention']:7.1%}  {rf_m['top10_retention']:7.1%}  "
              f"{rf_m['rank_accuracy']:8.1%}")
        print(f"\n  Selected: {primary_name}  (R²={metrics['r2_test']:.4f})")
        print(f"  Training time: {elapsed:.1f}s")

    return primary, primary_name, metrics, X, y, test_idx


# ---------------------------------------------------------------------------
# Retraining — pre-strategy ranker (lightweight)
# ---------------------------------------------------------------------------

def retrain_pre_strategy_ranker(verbose: bool = True) -> Optional[Dict]:
    """
    Retrain the pre_strategy_ranker using its own dataset.
    Returns metrics dict or None if dataset not found.
    """
    ranker_dataset = DATASETS_DIR / "layout_training" / "pre_ranker_dataset_v2.jsonl"
    ranker_model   = MODELS_DIR / "pre_strategy_ranker.pkl"

    if not ranker_dataset.exists():
        if verbose:
            print(f"  SKIP pre_strategy_ranker — dataset not found: {ranker_dataset.name}")
        return None

    try:
        from model_lab.training.train_pre_strategy_ranker import train as _train_pre
        if verbose:
            print(f"  Retraining pre_strategy_ranker from {ranker_dataset.name}...")
        result = _train_pre(
            dataset_path=ranker_dataset,
            model_path=ranker_model,
            verbose=verbose,
        )
        return result
    except Exception as exc:
        if verbose:
            print(f"  WARN: pre_strategy_ranker retraining failed: {exc}")
        return None


# ---------------------------------------------------------------------------
# Model comparison
# ---------------------------------------------------------------------------

def compare_models(
    current_metrics: Optional[Dict],
    new_metrics:     Dict,
    verbose:         bool = True,
) -> Dict[str, Any]:
    """
    Compare new model metrics against current model.

    Returns comparison dict with delta values and improvement flags.
    """
    if current_metrics is None:
        if verbose:
            print("  No previous model to compare against (first training run)")
        return {"first_run": True}

    delta_r2   = new_metrics.get("r2_test", 0) - current_metrics.get("r2_test", 0)
    delta_ret5 = new_metrics.get("top5_retention", 0) - current_metrics.get("top5_retention", 0)
    improved   = delta_r2 > -0.01   # allow ≤1pp regression (more data = harder)

    comparison = {
        "previous_r2":    current_metrics.get("r2_test", 0),
        "new_r2":         new_metrics.get("r2_test", 0),
        "delta_r2":       round(delta_r2, 4),
        "previous_ret5":  current_metrics.get("top5_retention", 0),
        "new_ret5":       new_metrics.get("top5_retention", 0),
        "delta_ret5":     round(delta_ret5, 4),
        "improved":       improved,
    }

    if verbose:
        print("\n  Model Comparison:")
        print(f"  {'Metric':20}  {'Previous':>10}  {'New':>10}  {'Δ':>8}")
        print(f"  {'─'*52}")
        print(f"  {'R² (test)':20}  {current_metrics.get('r2_test',0):10.4f}  "
              f"{new_metrics.get('r2_test',0):10.4f}  {delta_r2:+8.4f}")
        print(f"  {'Top-5 retention':20}  {current_metrics.get('top5_retention',0):10.1%}  "
              f"{new_metrics.get('top5_retention',0):10.1%}  {delta_ret5:+8.1%}")
        if improved:
            print(f"\n  ✓ New model is better or within tolerance — recommend deploy")
        else:
            print(f"\n  ⚠ New model regressed > 1pp — investigate before deploying")

    return comparison


# ---------------------------------------------------------------------------
# Save versioned model
# ---------------------------------------------------------------------------

def save_versioned_model(
    model,
    model_name:      str,
    metrics:         Dict,
    feature_names:   List[str],
    dataset_n:       int,
    dataset_sources: Dict,
    dry_run:         bool = False,
    notes:           str = "",
    verbose:         bool = True,
) -> Optional[Path]:
    """
    Save model as current + versioned copy, update version registry.

    Returns path to versioned model file (or None if dry_run).
    """
    version_n     = _next_version_number()
    versioned_path = MODELS_DIR / f"graph_prior_v{version_n}.pkl"

    payload = {
        "model":          model,
        "model_name":     model_name,
        "feature_names":  feature_names,
        "r2_test":        metrics.get("r2_test", 0.0),
        "ret5":           metrics.get("top5_retention", 0.0),
        "gb_r2":          metrics.get("gb_r2", 0.0),
        "rf_r2":          metrics.get("rf_r2", 0.0),
        "version":        version_n,
        "dataset_size":   dataset_n,
        "timestamp":      datetime.now(timezone.utc).isoformat(),
    }

    if dry_run:
        if verbose:
            print(f"\n  DRY RUN — would save v{version_n} to {versioned_path.name}")
        return None

    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    # Save versioned copy
    with open(versioned_path, "wb") as f:
        pickle.dump(payload, f)

    # Overwrite current model
    with open(CURRENT_MODEL, "wb") as f:
        pickle.dump(payload, f)

    # Update version registry
    _register_version(
        version_n=version_n,
        model_path=versioned_path,
        metrics=metrics,
        dataset_n=dataset_n,
        dataset_sources=dataset_sources,
        model_name=model_name,
        notes=notes,
    )

    if verbose:
        print(f"\n  Saved → {versioned_path.name}  (v{version_n})")
        print(f"  Current model updated → {CURRENT_MODEL.name}")

    return versioned_path


# ---------------------------------------------------------------------------
# Main retraining pipeline
# ---------------------------------------------------------------------------

def run_retraining(
    dataset_path:        Optional[Path] = None,
    include_experience:  bool = False,
    skip_merge:          bool = False,
    skip_ranker:         bool = False,
    dry_run:             bool = False,
    verbose:             bool = True,
) -> Dict[str, Any]:
    """
    Full retraining pipeline.

    1. (Optional) Merge datasets
    2. Load merged dataset
    3. Retrain graph prior
    4. Compare against current model
    5. Save versioned model
    6. (Optional) Retrain pre_strategy_ranker
    7. Return summary

    Returns comprehensive results dict.
    """
    from model_lab.training.graph_feature_extractor  import GRAPH_FEATURE_NAMES
    from model_lab.training.parcel_feature_extractor import PARCEL_FEATURE_NAMES
    FEATURE_NAMES = PARCEL_FEATURE_NAMES + GRAPH_FEATURE_NAMES

    print("=" * 64)
    print("RETRAINING PIPELINE — model_lab Phase 10")
    print("=" * 64)

    # ------------------------------------------------------------------
    # 1. Merge (unless skipped or dataset explicitly provided)
    # ------------------------------------------------------------------
    if dataset_path is None and not skip_merge:
        print("\n[1] Dataset merge")
        print("─" * 64)
        from model_lab.training.merge_datasets import merge_datasets
        merge_result = merge_datasets(
            include_experience=include_experience,
            verbose=verbose,
        )
        actual_dataset = MERGED_PATH
    elif dataset_path is not None:
        print(f"\n[1] Using provided dataset: {dataset_path.name}")
        actual_dataset = dataset_path
        merge_result   = {}
    else:
        print(f"\n[1] Skip merge — using existing: {MERGED_PATH.name}")
        actual_dataset = MERGED_PATH if MERGED_PATH.exists() else SYNTHETIC_PATH
        merge_result   = {}

    # ------------------------------------------------------------------
    # 2. Load dataset
    # ------------------------------------------------------------------
    print(f"\n[2] Loading dataset: {actual_dataset.name}")
    print("─" * 64)

    records = load_dataset(actual_dataset)
    print(f"  Records: {len(records)}")

    if len(records) < 50:
        print(f"  ERROR: too few records ({len(records)}) — aborting")
        return {"error": "insufficient_data", "n_records": len(records)}

    # Dataset composition
    from collections import Counter
    sources = Counter(r.get("source", "synthetic") for r in records)
    types   = Counter(r.get("generator_type", "unknown") for r in records)

    # ------------------------------------------------------------------
    # 3. Retrain graph prior
    # ------------------------------------------------------------------
    print(f"\n[3] Retraining graph prior")
    print("─" * 64)

    current_metrics = load_current_model_metrics()
    if current_metrics and verbose:
        print(f"  Current model: {current_metrics.get('model_name', '?')}  "
              f"R²={current_metrics.get('r2_test', 0):.4f}  "
              f"Top-5={current_metrics.get('top5_retention', 0):.1%}")
    print()

    model, model_name, new_metrics, X, y, test_idx = retrain_graph_prior(
        records, verbose=verbose,
    )

    # ------------------------------------------------------------------
    # 4. Model comparison
    # ------------------------------------------------------------------
    print(f"\n[4] Model comparison")
    print("─" * 64)
    comparison = compare_models(current_metrics, new_metrics, verbose=verbose)

    # ------------------------------------------------------------------
    # 5. Save
    # ------------------------------------------------------------------
    print(f"\n[5] Saving versioned model")
    print("─" * 64)

    dataset_sources = dict(sources)
    versioned_path = save_versioned_model(
        model=model,
        model_name=model_name,
        metrics=new_metrics,
        feature_names=FEATURE_NAMES,
        dataset_n=len(records),
        dataset_sources=dataset_sources,
        dry_run=dry_run,
        notes=(f"auto-retrain  include_experience={include_experience}"),
        verbose=verbose,
    )

    # ------------------------------------------------------------------
    # 6. Pre-strategy ranker (optional)
    # ------------------------------------------------------------------
    ranker_result = None
    if not skip_ranker:
        print(f"\n[6] Pre-strategy ranker")
        print("─" * 64)
        ranker_result = retrain_pre_strategy_ranker(verbose=verbose)

    # ------------------------------------------------------------------
    # 7. Summary
    # ------------------------------------------------------------------
    print(f"\n{'='*64}")
    print("RETRAINING SUMMARY")
    print(f"{'='*64}")
    print(f"  Dataset:          {len(records)} records  {dict(sources)}")
    print(f"  Types:            {dict(types)}")
    print(f"  Model selected:   {model_name}")
    print(f"  R² (test):        {new_metrics.get('r2_test', 0):.4f}")
    print(f"  Top-5 retention:  {new_metrics.get('top5_retention', 0):.1%}")
    print(f"  Top-10 retention: {new_metrics.get('top10_retention', 0):.1%}")
    print(f"  Rank accuracy:    {new_metrics.get('rank_accuracy', 0):.1%}")
    if not dry_run and versioned_path:
        version_n = _next_version_number() - 1
        print(f"  Version:          v{version_n} → {versioned_path.name}")
    elif dry_run:
        print(f"  DRY RUN — no models saved")
    if comparison.get("improved"):
        print(f"  Status:           ✓ IMPROVED vs previous")
    elif comparison.get("first_run"):
        print(f"  Status:           ✓ FIRST TRAINING RUN")
    else:
        print(f"  Status:           ⚠ REGRESSION — review before deploying")

    return {
        "model_name":      model_name,
        "new_metrics":     new_metrics,
        "comparison":      comparison,
        "dataset_n":       len(records),
        "dataset_sources": dataset_sources,
        "versioned_path":  str(versioned_path) if versioned_path else None,
        "ranker_retrained": ranker_result is not None,
        "dry_run":         dry_run,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Retrain graph prior model on merged dataset",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--dataset",    default=None,
                        help="Path to training JSONL (overrides auto-merge)")
    parser.add_argument("--no-merge",   action="store_true",
                        help="Skip dataset merge; use existing merged_graph_training.jsonl")
    parser.add_argument("--include-experience", action="store_true",
                        help="Include production layout_experience.jsonl during merge")
    parser.add_argument("--no-ranker",  action="store_true",
                        help="Skip pre_strategy_ranker retraining")
    parser.add_argument("--dry-run",    action="store_true",
                        help="Evaluate but do not save models")
    parser.add_argument("--verbose",    action="store_true", default=True)
    args = parser.parse_args()

    run_retraining(
        dataset_path=Path(args.dataset) if args.dataset else None,
        include_experience=args.include_experience,
        skip_merge=args.no_merge,
        skip_ranker=args.no_ranker,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )
