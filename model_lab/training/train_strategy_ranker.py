"""
Strategy Ranker Training Script — model_lab

Trains a model to predict layout score from pre-simulation features
(parcel geometry + strategy parameters + road graph structure).

Trained model saved to:  model_lab/models/strategy_ranker.pkl

Usage:
    python model_lab/training/train_strategy_ranker.py

    # Specify dataset file:
    python model_lab/training/train_strategy_ranker.py --dataset path/to/file.jsonl

    # Tune hyperparameters:
    python model_lab/training/train_strategy_ranker.py --n-estimators 500 --max-depth 5

    # Also train a random forest for comparison:
    python model_lab/training/train_strategy_ranker.py --compare-rf

Notes on train/test split:
  Split is performed by parcel_id (not record index) to prevent data leakage.
  Each parcel contributes records for multiple strategies, so a random record-
  level split would leak parcel geometry into the test set.

Model selection:
  GradientBoostingRegressor is used as the primary model (equivalent to
  XGBoost without the external dependency). RandomForestRegressor is trained
  as a comparison baseline.

No production code is modified.
"""

from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from model_lab.training.feature_extractor import (
    ALL_FEATURE_NAMES,
    records_to_arrays,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

DATASET_FILE  = REPO_ROOT / "model_lab" / "datasets" / "layout_training" / "layout_examples.jsonl"
MODELS_DIR    = REPO_ROOT / "model_lab" / "models"
MODEL_PATH    = MODELS_DIR / "strategy_ranker.pkl"
RF_MODEL_PATH = MODELS_DIR / "strategy_ranker_rf.pkl"


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_jsonl(path: Path) -> List[dict]:
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


def parcel_stratified_split(
    records: List[dict],
    test_fraction: float = 0.20,
    seed: int = 42,
) -> Tuple[List[dict], List[dict]]:
    """
    Split records into train/test by parcel_id (not by record index).

    All strategies for a given parcel go to the same split to prevent leakage.
    """
    rng = np.random.RandomState(seed)
    parcel_ids = list({r["parcel_id"] for r in records})
    rng.shuffle(parcel_ids)
    n_test = max(1, int(len(parcel_ids) * test_fraction))
    test_ids  = set(parcel_ids[:n_test])
    train_ids = set(parcel_ids[n_test:])
    train = [r for r in records if r["parcel_id"] in train_ids]
    test  = [r for r in records if r["parcel_id"] in test_ids]
    return train, test


# ---------------------------------------------------------------------------
# Model training
# ---------------------------------------------------------------------------

def train_gradient_boosting(
    X_train: np.ndarray,
    y_train: np.ndarray,
    n_estimators: int = 300,
    max_depth: int = 4,
    learning_rate: float = 0.05,
    subsample: float = 0.8,
) -> object:
    from sklearn.ensemble import GradientBoostingRegressor
    model = GradientBoostingRegressor(
        n_estimators=n_estimators,
        max_depth=max_depth,
        learning_rate=learning_rate,
        subsample=subsample,
        min_samples_leaf=5,
        random_state=42,
        validation_fraction=0.1,
        n_iter_no_change=30,
        tol=1e-4,
    )
    model.fit(X_train, y_train)
    return model


def train_random_forest(
    X_train: np.ndarray,
    y_train: np.ndarray,
    n_estimators: int = 200,
    max_depth: int = None,
) -> object:
    from sklearn.ensemble import RandomForestRegressor
    model = RandomForestRegressor(
        n_estimators=n_estimators,
        max_depth=max_depth,
        min_samples_leaf=5,
        n_jobs=-1,
        random_state=42,
    )
    model.fit(X_train, y_train)
    return model


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def evaluate(model, X: np.ndarray, y: np.ndarray, label: str) -> Dict[str, float]:
    from sklearn.metrics import r2_score, mean_squared_error
    y_pred = model.predict(X)
    r2   = r2_score(y, y_pred)
    rmse = float(np.sqrt(mean_squared_error(y, y_pred)))
    mae  = float(np.mean(np.abs(y - y_pred)))

    # Ranking accuracy: for each parcel in the split, does the model rank
    # the best strategy correctly?
    print(f"\n  [{label}]  R²={r2:.4f}  RMSE={rmse:.4f}  MAE={mae:.4f}")
    return {"r2": r2, "rmse": rmse, "mae": mae, "y_pred": y_pred.tolist()}


def ranking_accuracy(
    model,
    records: List[dict],
    X: np.ndarray,
    y: np.ndarray,
) -> float:
    """
    Fraction of parcels where the model correctly identifies the top strategy.

    For each parcel, compare the model's top-ranked strategy against the
    ground-truth best strategy (by actual score).
    """
    from itertools import groupby

    # Group by parcel_id
    parcel_order: Dict[str, List[int]] = {}
    for i, rec in enumerate(records):
        pid = rec["parcel_id"]
        parcel_order.setdefault(pid, []).append(i)

    y_pred = model.predict(X)
    correct = 0
    total   = 0

    for pid, indices in parcel_order.items():
        if len(indices) < 2:
            continue
        actual_best = indices[int(np.argmax([y[i] for i in indices]))]
        pred_best   = indices[int(np.argmax([y_pred[i] for i in indices]))]
        if actual_best == pred_best:
            correct += 1
        total += 1

    return correct / total if total > 0 else 0.0


def feature_importance_table(model, feature_names: List[str], top_n: int = 15) -> List[Tuple[str, float]]:
    """Return sorted (feature_name, importance) pairs."""
    importances = model.feature_importances_
    pairs = sorted(zip(feature_names, importances), key=lambda t: t[1], reverse=True)
    return pairs[:top_n]


# ---------------------------------------------------------------------------
# Save / load
# ---------------------------------------------------------------------------

def save_model(model, path: Path, metadata: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "model": model,
        "feature_names": ALL_FEATURE_NAMES,
        "metadata": metadata,
    }
    with open(path, "wb") as f:
        pickle.dump(payload, f, protocol=5)
    print(f"\n  Saved → {path}")


# ---------------------------------------------------------------------------
# Main training pipeline
# ---------------------------------------------------------------------------

def train(
    dataset_path: Path = DATASET_FILE,
    n_estimators: int = 300,
    max_depth: int = 4,
    compare_rf: bool = False,
    target: str = "overall_score",
) -> dict:
    print("=" * 60)
    print("STRATEGY RANKER — TRAINING")
    print("=" * 60)

    # 1. Load data
    print(f"\nLoading dataset: {dataset_path}")
    records = load_jsonl(dataset_path)
    print(f"  Records loaded : {len(records)}")

    if len(records) < 50:
        raise ValueError(f"Too few records ({len(records)}). Generate more data first.")

    # 2. Parcel-stratified split
    train_records, test_records = parcel_stratified_split(records, test_fraction=0.20)
    print(f"  Train records  : {len(train_records)}  ({len({r['parcel_id'] for r in train_records})} parcels)")
    print(f"  Test records   : {len(test_records)}  ({len({r['parcel_id'] for r in test_records})} parcels)")

    X_train, y_train, names = records_to_arrays(train_records, target=target)
    X_test,  y_test,  _     = records_to_arrays(test_records,  target=target)
    print(f"  Feature dims   : {X_train.shape[1]} features")
    print(f"  Target range   : [{y_train.min():.3f}, {y_train.max():.3f}]  (mean={y_train.mean():.3f})")

    # 3. Train baseline (mean predictor)
    mean_pred = np.full_like(y_test, y_train.mean())
    from sklearn.metrics import r2_score, mean_squared_error
    baseline_r2   = r2_score(y_test, mean_pred)
    baseline_rmse = float(np.sqrt(mean_squared_error(y_test, mean_pred)))
    print(f"\n  Baseline (mean): R²={baseline_r2:.4f}  RMSE={baseline_rmse:.4f}")

    # 4. Train GradientBoosting (primary)
    print(f"\nTraining GradientBoostingRegressor (n_estimators={n_estimators}, depth={max_depth})...")
    gb_model = train_gradient_boosting(X_train, y_train, n_estimators=n_estimators, max_depth=max_depth)
    gb_train = evaluate(gb_model, X_train, y_train, "GB train")
    gb_test  = evaluate(gb_model, X_test,  y_test,  "GB test ")
    gb_rank  = ranking_accuracy(gb_model, test_records, X_test, y_test)
    print(f"  Ranking accuracy (top-1 per parcel): {gb_rank:.1%}")

    # 5. Feature importance
    print("\n  Top-15 Feature Importances (GradientBoosting):")
    for feat, imp in feature_importance_table(gb_model, names, top_n=15):
        bar = "█" * int(imp * 200)
        print(f"    {feat:40s} {imp:.4f}  {bar}")

    # 6. Save primary model
    gb_metadata = {
        "model_type": "GradientBoostingRegressor",
        "target": target,
        "n_estimators": getattr(gb_model, "n_estimators_", n_estimators),
        "max_depth": max_depth,
        "train_r2": gb_train["r2"],
        "test_r2": gb_test["r2"],
        "test_rmse": gb_test["rmse"],
        "ranking_accuracy": gb_rank,
        "n_train": len(train_records),
        "n_test": len(test_records),
        "feature_count": len(names),
    }
    save_model(gb_model, MODEL_PATH, gb_metadata)

    results = {
        "gradient_boosting": {**gb_train, **{"ranking_accuracy": gb_rank}},
        "test": gb_test,
        "model_path": str(MODEL_PATH),
    }

    # 7. Optionally compare RandomForest
    if compare_rf:
        print("\nTraining RandomForestRegressor for comparison...")
        rf_model = train_random_forest(X_train, y_train)
        rf_train = evaluate(rf_model, X_train, y_train, "RF train")
        rf_test  = evaluate(rf_model, X_test,  y_test,  "RF test ")
        rf_rank  = ranking_accuracy(rf_model, test_records, X_test, y_test)
        print(f"  Ranking accuracy: {rf_rank:.1%}")
        rf_metadata = {
            "model_type": "RandomForestRegressor",
            "target": target,
            "test_r2": rf_test["r2"],
            "test_rmse": rf_test["rmse"],
            "ranking_accuracy": rf_rank,
        }
        save_model(rf_model, RF_MODEL_PATH, rf_metadata)
        results["random_forest"] = {**rf_train, **{"ranking_accuracy": rf_rank}}

        # Model comparison
        print("\n  ─── Model Comparison ───────────────────────────────")
        print(f"  {'Model':30s}  {'R² (test)':>10}  {'RMSE':>8}  {'Rank Acc':>9}")
        print(f"  {'Baseline (mean)':30s}  {baseline_r2:10.4f}  {baseline_rmse:8.4f}  {'N/A':>9}")
        print(f"  {'GradientBoosting':30s}  {gb_test['r2']:10.4f}  {gb_test['rmse']:8.4f}  {gb_rank:9.1%}")
        print(f"  {'RandomForest':30s}  {rf_test['r2']:10.4f}  {rf_test['rmse']:8.4f}  {rf_rank:9.1%}")

    print("\n" + "=" * 60)
    print("Training complete.")
    print("=" * 60)
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train layout strategy ranking model.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--dataset",       type=Path,  default=DATASET_FILE)
    parser.add_argument("--n-estimators",  type=int,   default=300)
    parser.add_argument("--max-depth",     type=int,   default=4)
    parser.add_argument("--compare-rf",    action="store_true",
                        help="Also train RandomForest for comparison.")
    parser.add_argument("--target",        type=str,   default="overall_score",
                        choices=["overall_score", "yield_score", "efficiency_score"])
    args = parser.parse_args()

    train(
        dataset_path=args.dataset,
        n_estimators=args.n_estimators,
        max_depth=args.max_depth,
        compare_rf=args.compare_rf,
        target=args.target,
    )


if __name__ == "__main__":
    main()
