"""
Train Graph Prior Model — model_lab Phase 8

Trains a model that predicts layout score from:
  parcel geometry features + graph topology features

This is the "graph prior" — it scores graph candidates before any
simulation, enabling guided graph search.

Architecture:
  GradientBoostingRegressor (primary)
  RandomForestRegressor     (comparison)

Metrics:
  R² on held-out test set
  Top-K ranking accuracy (per parcel)
  Score retention at various K thresholds

Saves:
  model_lab/models/graph_prior.pkl
  (also logs feature importance)

No production code is modified.
"""

from __future__ import annotations

import json
import pickle
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DATASET_PATH = REPO_ROOT / "model_lab" / "datasets" / "graph_training.jsonl"
MODEL_PATH   = REPO_ROOT / "model_lab" / "models" / "graph_prior.pkl"

from model_lab.training.graph_feature_extractor  import GRAPH_FEATURE_NAMES
from model_lab.training.parcel_feature_extractor import PARCEL_FEATURE_NAMES

FEATURE_NAMES = PARCEL_FEATURE_NAMES + GRAPH_FEATURE_NAMES


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_dataset(path: Path = DATASET_PATH) -> List[dict]:
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def records_to_arrays(records: List[dict]) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    """Build feature matrix X and target vector y."""
    X_rows, y_vals = [], []
    for rec in records:
        pf = rec.get("parcel_features", {})
        gf = rec.get("graph_features", {})
        row = [float(pf.get(k, 0.0)) for k in PARCEL_FEATURE_NAMES] + \
              [float(gf.get(k, 0.0)) for k in GRAPH_FEATURE_NAMES]
        X_rows.append(row)
        y_vals.append(float(rec["score"]))
    return np.array(X_rows, dtype=np.float32), np.array(y_vals, dtype=np.float32), FEATURE_NAMES


# ---------------------------------------------------------------------------
# Evaluation helpers
# ---------------------------------------------------------------------------

def top_k_score_retention(
    records: List[dict],
    predictions: np.ndarray,
    k: int,
) -> float:
    """
    For each parcel, rank graphs by predicted score, take top-k.
    Return: (mean score of top-k predicted) / (mean score of top-k actual).
    Measures how much of the true best score the model captures.
    """
    by_parcel: Dict[str, List[Tuple[float, float]]] = defaultdict(list)
    for rec, pred in zip(records, predictions):
        by_parcel[rec["parcel_id"]].append((float(pred), float(rec["score"])))

    retentions = []
    for pid, pairs in by_parcel.items():
        if len(pairs) < k:
            continue
        # True top-k by actual score
        true_top_k = sorted(pairs, key=lambda x: x[1], reverse=True)[:k]
        true_mean  = np.mean([s for _, s in true_top_k])
        # Predicted top-k
        pred_top_k = sorted(pairs, key=lambda x: x[0], reverse=True)[:k]
        pred_mean  = np.mean([s for _, s in pred_top_k])  # actual scores of predicted top-k
        retentions.append(pred_mean / max(true_mean, 1e-9))
    return float(np.mean(retentions)) if retentions else 0.0


def ranking_accuracy(
    records: List[dict],
    predictions: np.ndarray,
) -> float:
    """
    Per-parcel: does the model correctly identify the best graph?
    Returns fraction of parcels where predicted best == true best.
    """
    by_parcel: Dict[str, List[Tuple[float, float, int]]] = defaultdict(list)
    for i, (rec, pred) in enumerate(zip(records, predictions)):
        by_parcel[rec["parcel_id"]].append((float(pred), float(rec["score"]), i))

    correct = 0
    total = 0
    for pid, triples in by_parcel.items():
        if len(triples) < 2:
            continue
        pred_best  = max(triples, key=lambda x: x[0])[2]
        true_best  = max(triples, key=lambda x: x[1])[2]
        # Count as correct if true score of predicted best is within 2% of true best
        pb_score = triples[pred_best - triples[0][2]][1] if False else \
                   next(s for p, s, i in triples if i == pred_best)
        tb_score = next(s for p, s, i in triples if i == true_best)
        if abs(pb_score - tb_score) / max(tb_score, 1e-9) < 0.02:
            correct += 1
        total += 1

    return correct / max(total, 1)


# ---------------------------------------------------------------------------
# Parcel-stratified split
# ---------------------------------------------------------------------------

def parcel_split(
    records: List[dict],
    test_frac: float = 0.2,
    seed: int = 42,
) -> Tuple[List[int], List[int]]:
    """Split by parcel_id so all graphs for a parcel stay in one split."""
    rng = np.random.default_rng(seed)
    parcel_ids = list({r["parcel_id"] for r in records})
    rng.shuffle(parcel_ids)
    n_test = max(1, int(len(parcel_ids) * test_frac))
    test_pids  = set(parcel_ids[:n_test])
    train_idx = [i for i, r in enumerate(records) if r["parcel_id"] not in test_pids]
    test_idx  = [i for i, r in enumerate(records) if r["parcel_id"] in test_pids]
    return train_idx, test_idx


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train(
    dataset_path: Path = DATASET_PATH,
    model_path:   Path = MODEL_PATH,
    verbose:      bool = True,
) -> dict:
    from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
    from sklearn.metrics import r2_score

    records = load_dataset(dataset_path)
    if verbose:
        print(f"Loaded {len(records)} records from {dataset_path}")

    X, y, feat_names = records_to_arrays(records)
    train_idx, test_idx = parcel_split(records)

    X_train, y_train = X[train_idx], y[train_idx]
    X_test,  y_test  = X[test_idx],  y[test_idx]
    rec_test = [records[i] for i in test_idx]

    if verbose:
        print(f"  Train: {len(train_idx)}  Test: {len(test_idx)}  Features: {X.shape[1]}")

    # --- GradientBoosting ---
    gb = GradientBoostingRegressor(
        n_estimators=200,
        max_depth=5,
        learning_rate=0.08,
        subsample=0.8,
        min_samples_leaf=5,
        random_state=42,
    )
    gb.fit(X_train, y_train)
    gb_pred  = gb.predict(X_test)
    gb_r2    = r2_score(y_test, gb_pred)
    gb_ret5  = top_k_score_retention(rec_test, gb_pred, k=5)
    gb_ret10 = top_k_score_retention(rec_test, gb_pred, k=10)
    gb_acc   = ranking_accuracy(rec_test, gb_pred)

    # --- RandomForest ---
    rf = RandomForestRegressor(
        n_estimators=200,
        max_depth=12,
        min_samples_leaf=3,
        random_state=42,
        n_jobs=-1,
    )
    rf.fit(X_train, y_train)
    rf_pred  = rf.predict(X_test)
    rf_r2    = r2_score(y_test, rf_pred)
    rf_ret5  = top_k_score_retention(rec_test, rf_pred, k=5)
    rf_acc   = ranking_accuracy(rec_test, rf_pred)

    # Choose primary model
    primary_model = gb if gb_r2 >= rf_r2 else rf
    primary_name  = "GradientBoosting" if gb_r2 >= rf_r2 else "RandomForest"

    if verbose:
        print(f"\n{'─'*60}")
        print(f"  Model               R²      Top-5 Ret  Top-10 Ret  Rank Acc")
        print(f"  {'─'*56}")
        print(f"  GradientBoosting  {gb_r2:6.4f}   {gb_ret5:7.1%}    {gb_ret10:7.1%}   {gb_acc:7.1%}")
        print(f"  RandomForest      {rf_r2:6.4f}   {rf_ret5:7.1%}    {'—':>7s}   {rf_acc:7.1%}")
        print(f"\n  Primary model: {primary_name}")

    # --- Feature importance ---
    if verbose:
        importances = primary_model.feature_importances_
        ranked = sorted(zip(feat_names, importances), key=lambda x: x[1], reverse=True)
        print(f"\n  Top-15 Feature Importances ({primary_name}):")
        for name, imp in ranked[:15]:
            bar = "█" * int(imp * 200)
            print(f"    {name:35s}  {imp:.4f}  {bar}")

        # Group by category
        parcel_imp = sum(imp for name, imp in ranked if name in PARCEL_FEATURE_NAMES)
        graph_imp  = sum(imp for name, imp in ranked if name in GRAPH_FEATURE_NAMES)
        print(f"\n  Parcel features total importance: {parcel_imp:.3f}")
        print(f"  Graph features total importance:  {graph_imp:.3f}")

    # Save model + metadata
    model_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "model":        primary_model,
        "model_name":   primary_name,
        "feature_names": feat_names,
        "r2_test":      gb_r2 if primary_model is gb else rf_r2,
        "ret5":         gb_ret5 if primary_model is gb else rf_ret5,
        "gb_r2":        gb_r2,
        "rf_r2":        rf_r2,
    }
    with open(model_path, "wb") as f:
        pickle.dump(payload, f)
    if verbose:
        print(f"\n  Saved → {model_path}")

    return payload


if __name__ == "__main__":
    train()
