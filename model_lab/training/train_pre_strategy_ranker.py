"""
Pre-Strategy Ranker Training Script — model_lab

Trains a model to predict layout score from pre-simulation features ONLY:
  - parcel geometry
  - strategy parameters

No road graph features. No layout metrics. Pure pre-simulation ranker.

Uses:
  - XGBoost (if available)
  - GradientBoostingRegressor (sklearn fallback)
  - RandomForestRegressor (comparison baseline)

Saved model: model_lab/models/pre_strategy_ranker.pkl

Usage:
    python model_lab/training/train_pre_strategy_ranker.py
    python model_lab/training/train_pre_strategy_ranker.py --compare-all

No production code is modified.
"""

from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from model_lab.training.pre_ranker_feature_extractor import (
    ALL_PRE_RANKER_FEATURE_NAMES,
    records_to_arrays,
)

DATASET_PATH = (
    REPO_ROOT / "model_lab" / "datasets" / "layout_training" / "pre_ranker_dataset.jsonl"
)
MODELS_DIR = REPO_ROOT / "model_lab" / "models"
MODEL_PATH = MODELS_DIR / "pre_strategy_ranker.pkl"


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_pre_ranker_jsonl(path: Path) -> List[dict]:
    """Load pre-ranker JSONL where features live under a 'features' key."""
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return records


def _pre_ranker_records_to_arrays(
    records: List[dict],
    target: str = "overall_score",
    feature_names: Optional[List[str]] = None,
) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    """Convert pre-ranker JSONL records (features already extracted) to arrays."""
    names = feature_names or ALL_PRE_RANKER_FEATURE_NAMES
    X_rows, y_vals = [], []
    for rec in records:
        feat = rec.get("features", {})
        X_rows.append([feat.get(n, 0.0) for n in names])
        y_vals.append(float(rec.get("score", {}).get(target, 0.0)))
    return (
        np.array(X_rows, dtype=np.float32),
        np.array(y_vals, dtype=np.float64),
        names,
    )


# ---------------------------------------------------------------------------
# Train/test split (parcel-stratified)
# ---------------------------------------------------------------------------

def parcel_stratified_split(
    records: List[dict],
    test_fraction: float = 0.20,
    seed: int = 42,
) -> Tuple[List[dict], List[dict]]:
    rng = np.random.RandomState(seed)
    parcel_ids = list({r["parcel_id"] for r in records})
    rng.shuffle(parcel_ids)
    n_test = max(1, int(len(parcel_ids) * test_fraction))
    test_ids  = set(parcel_ids[:n_test])
    train_ids = set(parcel_ids[n_test:])
    return (
        [r for r in records if r["parcel_id"] in train_ids],
        [r for r in records if r["parcel_id"] in test_ids],
    )


# ---------------------------------------------------------------------------
# Model trainers
# ---------------------------------------------------------------------------

def _train_xgboost(X_train, y_train, n_estimators=400, max_depth=5, lr=0.05):
    import xgboost as xgb
    model = xgb.XGBRegressor(
        n_estimators=n_estimators,
        max_depth=max_depth,
        learning_rate=lr,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_alpha=0.1,
        reg_lambda=1.0,
        min_child_weight=5,
        random_state=42,
        n_jobs=-1,
        early_stopping_rounds=30,
        eval_metric="rmse",
    )
    eval_set = [(X_train, y_train)]
    model.fit(X_train, y_train, eval_set=eval_set, verbose=False)
    return model, "XGBoostRegressor"


def _train_gb(X_train, y_train, n_estimators=400, max_depth=5, lr=0.05):
    from sklearn.ensemble import GradientBoostingRegressor
    model = GradientBoostingRegressor(
        n_estimators=n_estimators,
        max_depth=max_depth,
        learning_rate=lr,
        subsample=0.8,
        min_samples_leaf=5,
        random_state=42,
        validation_fraction=0.1,
        n_iter_no_change=30,
        tol=1e-4,
    )
    model.fit(X_train, y_train)
    return model, "GradientBoostingRegressor"


def _train_rf(X_train, y_train, n_estimators=300):
    from sklearn.ensemble import RandomForestRegressor
    model = RandomForestRegressor(
        n_estimators=n_estimators,
        max_depth=None,
        min_samples_leaf=5,
        n_jobs=-1,
        random_state=42,
    )
    model.fit(X_train, y_train)
    return model, "RandomForestRegressor"


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def evaluate(model, X, y, label: str) -> Dict[str, float]:
    from sklearn.metrics import r2_score, mean_squared_error
    y_pred = model.predict(X)
    r2   = r2_score(y, y_pred)
    rmse = float(np.sqrt(mean_squared_error(y, y_pred)))
    mae  = float(np.mean(np.abs(y - y_pred)))
    print(f"  [{label:20s}]  R²={r2:.4f}  RMSE={rmse:.4f}  MAE={mae:.4f}")
    return {"r2": r2, "rmse": rmse, "mae": mae}


def ranking_accuracy(model, records, X, y) -> float:
    """Fraction of parcels where model picks the top strategy (by actual score)."""
    parcel_groups: Dict[str, List[int]] = {}
    for i, rec in enumerate(records):
        parcel_groups.setdefault(rec["parcel_id"], []).append(i)

    y_pred = model.predict(X)
    correct = total = 0
    genuine_errors = 0

    for pid, idxs in parcel_groups.items():
        if len(idxs) < 2:
            continue
        actual_best = idxs[int(np.argmax([y[i] for i in idxs]))]
        pred_best   = idxs[int(np.argmax([y_pred[i] for i in idxs]))]
        if actual_best == pred_best:
            correct += 1
        else:
            diff = y[actual_best] - y[pred_best]
            if diff > 0.01:      # genuine ranking error (not a tie)
                genuine_errors += 1
        total += 1

    print(f"  Ranking accuracy: {correct}/{total} = {correct/max(total,1):.1%}"
          f"  (genuine errors: {genuine_errors})")
    return correct / max(total, 1)


def top_k_score_retention(
    model, records, X, y, top_k_fractions=(0.5, 0.33, 0.25)
) -> Dict[str, float]:
    """
    For each parcel: rank all strategies by predicted score, keep top-k%,
    report what fraction of the best actual score is retained.
    """
    parcel_groups: Dict[str, List[int]] = {}
    for i, rec in enumerate(records):
        parcel_groups.setdefault(rec["parcel_id"], []).append(i)

    y_pred = model.predict(X)
    results = {}

    for frac in top_k_fractions:
        retentions = []
        for pid, idxs in parcel_groups.items():
            if len(idxs) < 2:
                continue
            best_actual = max(y[i] for i in idxs)
            if best_actual < 1e-9:
                continue
            # pick top-frac by predicted score
            n_keep = max(1, int(len(idxs) * frac))
            ranked = sorted(idxs, key=lambda i: y_pred[i], reverse=True)
            kept   = ranked[:n_keep]
            best_kept = max(y[i] for i in kept)
            retentions.append(best_kept / best_actual)

        avg = float(np.mean(retentions)) if retentions else 0.0
        label = f"top_{int(frac*100)}pct"
        results[label] = avg
        print(f"  Score retention (keep top {int(frac*100)}%): {avg:.1%}")

    return results


def feature_importance_table(model, feature_names, top_n=20):
    try:
        importances = model.feature_importances_
    except AttributeError:
        # XGBoost
        importances = model.feature_importances_
    pairs = sorted(zip(feature_names, importances), key=lambda t: t[1], reverse=True)
    return pairs[:top_n]


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------

def save_model(model, path: Path, metadata: dict, feature_names: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump({
            "model": model,
            "feature_names": feature_names,
            "metadata": metadata,
        }, f, protocol=5)
    print(f"\n  Saved → {path}")


# ---------------------------------------------------------------------------
# Main training pipeline
# ---------------------------------------------------------------------------

def train(
    dataset_path: Path = DATASET_PATH,
    n_estimators: int = 400,
    max_depth: int = 5,
    compare_all: bool = False,
    target: str = "overall_score",
) -> dict:
    print("=" * 64)
    print("PRE-STRATEGY RANKER — TRAINING (parcel + strategy features only)")
    print("=" * 64)

    # 1. Load
    print(f"\nLoading: {dataset_path}")
    records = load_pre_ranker_jsonl(dataset_path)
    print(f"  Records: {len(records)}")

    if len(records) < 50:
        raise ValueError(f"Too few records ({len(records)}). Run build_pre_ranker_dataset.py first.")

    # 2. Split
    train_records, test_records = parcel_stratified_split(records, test_fraction=0.20)
    print(f"  Train: {len(train_records)}  ({len({r['parcel_id'] for r in train_records})} parcels)")
    print(f"  Test:  {len(test_records)}  ({len({r['parcel_id'] for r in test_records})} parcels)")

    X_train, y_train, names = _pre_ranker_records_to_arrays(train_records, target)
    X_test,  y_test,  _     = _pre_ranker_records_to_arrays(test_records,  target)
    print(f"  Features: {X_train.shape[1]}")
    print(f"  Target range: [{y_train.min():.3f}, {y_train.max():.3f}]"
          f"  mean={y_train.mean():.3f}")

    # 3. Baseline
    from sklearn.metrics import r2_score, mean_squared_error
    mean_pred = np.full_like(y_test, y_train.mean())
    baseline_r2   = r2_score(y_test, mean_pred)
    baseline_rmse = float(np.sqrt(mean_squared_error(y_test, mean_pred)))
    print(f"\n  Baseline (mean): R²={baseline_r2:.4f}  RMSE={baseline_rmse:.4f}")

    # 4. Train primary model
    xgb_available = False
    try:
        import xgboost  # noqa
        xgb_available = True
    except ImportError:
        pass

    print(f"\nTraining primary model ({'XGBoost' if xgb_available else 'GradientBoosting'})...")
    if xgb_available:
        primary, model_type = _train_xgboost(X_train, y_train, n_estimators, max_depth)
    else:
        primary, model_type = _train_gb(X_train, y_train, n_estimators, max_depth)

    train_stats = evaluate(primary, X_train, y_train, f"{model_type[:18]} train")
    test_stats  = evaluate(primary, X_test,  y_test,  f"{model_type[:18]} test ")
    rank_acc    = ranking_accuracy(primary, test_records, X_test, y_test)
    print("\n  Top-k score retention:")
    retention   = top_k_score_retention(primary, test_records, X_test, y_test)

    # 5. Feature importance
    print(f"\n  Top-20 Feature Importances ({model_type}):")
    for feat, imp in feature_importance_table(primary, names, top_n=20):
        bar = "█" * int(imp * 200)
        tag = ("parcel" if not feat.startswith("strat_") else "strategy")
        print(f"    {feat:40s} {imp:.4f}  [{tag}]  {bar}")

    # Parcel vs strategy importance totals
    parcel_total   = sum(imp for n, imp in zip(names, primary.feature_importances_)
                         if not n.startswith("strat_"))
    strategy_total = sum(imp for n, imp in zip(names, primary.feature_importances_)
                         if n.startswith("strat_"))
    print(f"\n  Parcel features total importance:   {parcel_total:.3f} ({parcel_total:.1%})")
    print(f"  Strategy features total importance: {strategy_total:.3f} ({strategy_total:.1%})")

    # 6. Save
    metadata = {
        "model_type":        model_type,
        "stage":             "pre-simulation",
        "target":            target,
        "train_r2":          train_stats["r2"],
        "test_r2":           test_stats["r2"],
        "test_rmse":         test_stats["rmse"],
        "ranking_accuracy":  rank_acc,
        "score_retention":   retention,
        "n_train":           len(train_records),
        "n_test":            len(test_records),
        "feature_count":     len(names),
        "n_parcel_features": sum(1 for n in names if not n.startswith("strat_")),
        "n_strategy_features": sum(1 for n in names if n.startswith("strat_")),
    }
    save_model(primary, MODEL_PATH, metadata, names)
    results = {"primary": {**train_stats, **test_stats, "ranking_accuracy": rank_acc,
                           "retention": retention}}

    # 7. Optional: compare RF and (if applicable) the other model
    if compare_all:
        comparison = []
        comparison.append((model_type, test_stats["r2"], test_stats["rmse"], rank_acc))

        print("\nTraining RandomForest for comparison...")
        rf, rf_type = _train_rf(X_train, y_train)
        rf_test = evaluate(rf, X_test, y_test, "RF test")
        rf_rank = ranking_accuracy(rf, test_records, X_test, y_test)
        comparison.append((rf_type, rf_test["r2"], rf_test["rmse"], rf_rank))

        if xgb_available:
            print("\nTraining GradientBoosting for comparison...")
            gb, gb_type = _train_gb(X_train, y_train, n_estimators, max_depth)
            gb_test = evaluate(gb, X_test, y_test, "GB test")
            gb_rank = ranking_accuracy(gb, test_records, X_test, y_test)
            comparison.append((gb_type, gb_test["r2"], gb_test["rmse"], gb_rank))

        print("\n  ─── Model Comparison ───────────────────────────────────")
        print(f"  {'Model':30s}  {'R²':>8}  {'RMSE':>8}  {'Rank Acc':>9}")
        print(f"  {'Baseline (mean)':30s}  {baseline_r2:8.4f}  {baseline_rmse:8.4f}  {'N/A':>9}")
        for name, r2, rmse, ra in comparison:
            print(f"  {name:30s}  {r2:8.4f}  {rmse:8.4f}  {ra:9.1%}")

    print("\n" + "=" * 64)
    print("Training complete.")
    print("=" * 64)
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train pre-simulation strategy ranker (parcel + strategy features only).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--dataset",      type=Path, default=DATASET_PATH)
    parser.add_argument("--n-estimators", type=int,  default=400)
    parser.add_argument("--max-depth",    type=int,  default=5)
    parser.add_argument("--compare-all",  action="store_true",
                        help="Also train RF and GradientBoosting for comparison.")
    parser.add_argument("--target",       type=str,  default="overall_score",
                        choices=["overall_score", "yield_score", "efficiency_score"])
    args = parser.parse_args()
    train(
        dataset_path=args.dataset,
        n_estimators=args.n_estimators,
        max_depth=args.max_depth,
        compare_all=args.compare_all,
        target=args.target,
    )


if __name__ == "__main__":
    main()
