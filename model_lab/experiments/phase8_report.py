"""
Phase 8 Report — Graph Prior Learning
======================================

Comprehensive evaluation of the graph prior model and guided search.

Sections:
  1. Graph prior model performance (R², retention, feature importance)
  2. Prior accuracy by generator type
  3. Multi-seed guided vs random comparison (reliability analysis)
  4. Simulation budget analysis
  5. Production code integrity check

No production code is modified.
"""

from __future__ import annotations

import json
import pickle
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

MODEL_PATH   = REPO_ROOT / "model_lab" / "models" / "graph_prior.pkl"
DATASET_PATH = REPO_ROOT / "model_lab" / "datasets" / "graph_training.jsonl"


def run_report(
    n_seeds:       int = 10,
    generations:   int = 6,
    n_candidates:  int = 24,
    area_acres:    float = 10.0,
) -> None:
    from model_lab.training.train_graph_prior import (
        load_dataset, records_to_arrays, parcel_split,
        top_k_score_retention, ranking_accuracy,
    )
    from model_lab.experiments.guided_graph_search import run_guided_comparison
    from model_lab.graph_models.graph_prior import GraphPrior
    from sklearn.metrics import r2_score

    print("=" * 68)
    print("PHASE 8 REPORT — GRAPH PRIOR LEARNING")
    print("=" * 68)

    # ------------------------------------------------------------------ #
    # 1. Model performance
    # ------------------------------------------------------------------ #
    print("\n[1] Graph Prior Model Performance")
    print("─" * 68)

    with open(MODEL_PATH, "rb") as f:
        payload = pickle.load(f)
    model       = payload["model"]
    feat_names  = payload["feature_names"]
    model_name  = payload["model_name"]

    records = load_dataset(DATASET_PATH)
    X, y, _ = records_to_arrays(records)
    _, test_idx = parcel_split(records, seed=42)
    X_test   = X[test_idx]
    y_test   = y[test_idx]
    rec_test = [records[i] for i in test_idx]

    y_pred = model.predict(X_test)
    r2     = r2_score(y_test, y_pred)
    ret5   = top_k_score_retention(rec_test, y_pred, k=5)
    ret10  = top_k_score_retention(rec_test, y_pred, k=10)
    rank_acc = ranking_accuracy(rec_test, y_pred)

    print(f"  Model:           {model_name}")
    print(f"  Training set:    {len(records) - len(test_idx)} records")
    print(f"  Test set:        {len(test_idx)} records")
    print(f"  Features:        {X.shape[1]}")
    print(f"  R² (test):       {r2:.4f}")
    print(f"  Top-5 retention: {ret5:.1%}  (score of prior-top-5 vs true-top-5)")
    print(f"  Top-10 retention:{ret10:.1%}")
    print(f"  Rank accuracy:   {rank_acc:.1%}  (% parcels where #1 predicted = #1 actual)")

    # ------------------------------------------------------------------ #
    # 2. Feature importance
    # ------------------------------------------------------------------ #
    print("\n[2] Feature Importance")
    print("─" * 68)

    importances = model.feature_importances_
    ranked = sorted(zip(feat_names, importances), key=lambda x: x[1], reverse=True)

    print(f"  Top-12 features:")
    for name, imp in ranked[:12]:
        bar = "█" * int(imp * 200)
        print(f"    {name:35s}  {imp:.4f}  {bar}")

    from model_lab.training.parcel_feature_extractor import PARCEL_FEATURE_NAMES
    from model_lab.training.graph_feature_extractor  import GRAPH_FEATURE_NAMES
    p_imp = sum(imp for n, imp in ranked if n in PARCEL_FEATURE_NAMES)
    g_imp = sum(imp for n, imp in ranked if n in GRAPH_FEATURE_NAMES)
    print(f"\n  Parcel features: {p_imp:.3f} ({p_imp/(p_imp+g_imp):.0%})")
    print(f"  Graph features:  {g_imp:.3f} ({g_imp/(p_imp+g_imp):.0%})")

    # Key graph topology features
    print(f"\n  Top graph topology features:")
    graph_ranked = [(n, imp) for n, imp in ranked if n in GRAPH_FEATURE_NAMES]
    for name, imp in graph_ranked[:8]:
        bar = "█" * int(imp * 400)
        print(f"    {name:35s}  {imp:.4f}  {bar}")

    # ------------------------------------------------------------------ #
    # 3. Per-type prior accuracy
    # ------------------------------------------------------------------ #
    print("\n[3] Prior Accuracy by Generator Type")
    print("─" * 68)

    type_errors = defaultdict(list)
    for rec, pred in zip(rec_test, y_pred):
        gt    = rec["generator_type"]
        actual = rec["score"]
        err   = abs(float(pred) - actual)
        type_errors[gt].append((float(pred), actual, err))

    print(f"  {'Type':16s}  {'N':>4s}  {'MAE':>6s}  {'Corr':>6s}  {'Avg Actual':>10s}  {'Avg Pred':>8s}")
    print(f"  {'─'*16}  {'─'*4}  {'─'*6}  {'─'*6}  {'─'*10}  {'─'*8}")
    for gt in sorted(type_errors.keys()):
        triples = type_errors[gt]
        n = len(triples)
        mae = np.mean([t[2] for t in triples])
        actual_arr = np.array([t[1] for t in triples])
        pred_arr   = np.array([t[0] for t in triples])
        corr = float(np.corrcoef(pred_arr, actual_arr)[0, 1]) if n > 2 else 0.0
        print(f"  {gt:16s}  {n:4d}  {mae:6.4f}  {corr:6.3f}  "
              f"{actual_arr.mean():10.4f}  {pred_arr.mean():8.4f}")

    # ------------------------------------------------------------------ #
    # 4. Multi-seed guided vs random comparison
    # ------------------------------------------------------------------ #
    print(f"\n[4] Multi-Seed Guided vs Random Search ({n_seeds} seeds)")
    print("─" * 68)
    print(f"  Parcel: {area_acres:.0f}ac square  Gens: {generations}  Pool: {n_candidates}")
    print()

    rand_scores, guid_scores = [], []
    rand_stb_list, guid_stb_list = [], []

    print(f"  {'Seed':>4s}  {'Random':>8s}  {'Guided':>8s}  {'Δ':>7s}  {'RandSTB':>8s}  {'GuidSTB':>8s}")
    print(f"  {'─'*4}  {'─'*8}  {'─'*8}  {'─'*7}  {'─'*8}  {'─'*8}")

    for seed in range(n_seeds):
        rand_r, guid_r = run_guided_comparison(
            area_acres=area_acres,
            parcel_shape="square",
            generations=generations,
            n_candidates=n_candidates,
            seed=seed,
            verbose=False,
        )
        rand_scores.append(rand_r.best_score)
        guid_scores.append(guid_r.best_score)
        rand_stb = rand_r.sims_to_baseline
        guid_stb = guid_r.sims_to_baseline
        rand_stb_list.append(rand_stb)
        guid_stb_list.append(guid_stb)
        delta = guid_r.best_score - rand_r.best_score
        rstb_str = str(rand_stb) if rand_stb else "never"
        gstb_str = str(guid_stb) if guid_stb else "never"
        marker = "★" if delta > 0 else " "
        print(f"  {seed:4d}{marker} {rand_r.best_score:8.4f}  {guid_r.best_score:8.4f}  "
              f"{delta:+7.4f}  {rstb_str:>8s}  {gstb_str:>8s}")

    # Aggregate stats
    avg_rand = np.mean(rand_scores)
    avg_guid = np.mean(guid_scores)
    guided_wins = sum(1 for r, g in zip(rand_scores, guid_scores) if g > r)
    rand_converge = sum(1 for s in rand_stb_list if s is not None)
    guid_converge = sum(1 for s in guid_stb_list if s is not None)

    # Sim reduction (only where both converge, and random sims > 0)
    paired = [(r, g) for r, g in zip(rand_stb_list, guid_stb_list) if r and g]
    reductions = [1.0 - g / r for r, g in paired if r > 0]

    print(f"\n  {'─'*68}")
    print(f"  Average score:    random={avg_rand:.4f}  guided={avg_guid:.4f}  "
          f"Δ={avg_guid-avg_rand:+.4f} ({(avg_guid-avg_rand)/max(avg_rand,1e-9):+.1%})")
    print(f"  Guided wins:      {guided_wins}/{n_seeds} seeds")
    print(f"  Baseline reached: random={rand_converge}/{n_seeds}  "
          f"guided={guid_converge}/{n_seeds}")
    if reductions:
        avg_red = np.mean(reductions)
        med_red = float(np.median(reductions))
        print(f"  Sim reduction (both converge, n={len(reductions)}): "
              f"mean={avg_red:.0%}  median={med_red:.0%}")

    # ------------------------------------------------------------------ #
    # 5. Simulation budget analysis
    # ------------------------------------------------------------------ #
    print(f"\n[5] Simulation Budget Analysis")
    print("─" * 68)
    print(f"  Per generation: {n_candidates} simulations")
    print(f"  Random total ({generations} gens): ~{generations * n_candidates} sims")
    print(f"  Guided: same simulation count, BUT 2× candidate generation + prior scoring")
    print(f"    → Prior scoring cost: ~{n_candidates * 2} model.predict() calls/gen")
    print(f"    → Simulation cost: identical to random ({n_candidates}/gen)")
    print(f"    → Net: same sims, better quality from pre-filtered pool")
    print()
    print(f"  Key finding: guided search is {rand_converge/max(n_seeds,1):.0%} → "
          f"{guid_converge/max(n_seeds,1):.0%} baseline convergence rate")
    if avg_guid > avg_rand:
        improvement = (avg_guid - avg_rand) / max(avg_rand, 1e-9)
        print(f"  Average quality improvement: +{improvement:.1%} over random search")

    # ------------------------------------------------------------------ #
    # 6. Production code integrity
    # ------------------------------------------------------------------ #
    print(f"\n[6] Production Code Integrity Check")
    print("─" * 68)
    prod_dirs = ["ai_subdivision", "apps"]
    for d in prod_dirs:
        prod_path = REPO_ROOT / d
        if prod_path.exists():
            py_files = list(prod_path.rglob("*.py"))
            # Check none import from model_lab
            violations = []
            for f in py_files:
                try:
                    content = f.read_text()
                    if "model_lab" in content:
                        violations.append(str(f.relative_to(REPO_ROOT)))
                except Exception:
                    pass
            if violations:
                print(f"  WARNING: {d}/ — {len(violations)} files import model_lab: {violations[:3]}")
            else:
                print(f"  ✓ {d}/ — {len(py_files)} files, 0 model_lab imports")
        else:
            print(f"  ✓ {d}/ — not found (expected in different env)")

    model_lab_files = list((REPO_ROOT / "model_lab").rglob("*.py"))
    print(f"\n  model_lab/ total: {len(model_lab_files)} Python files")
    print(f"  Phase 8 new files: graph_feature_extractor.py, build_graph_dataset.py,")
    print(f"                     train_graph_prior.py, graph_prior.py,")
    print(f"                     guided_graph_search.py, phase8_report.py")

    print(f"\n{'='*68}")
    print("PHASE 8 SUMMARY")
    print(f"{'='*68}")
    print(f"  Graph prior R²:           {r2:.4f}")
    print(f"  Top-5 score retention:    {ret5:.1%}")
    print(f"  Top-10 score retention:   {ret10:.1%}")
    print(f"  Guided baseline rate:     {guid_converge}/{n_seeds} ({guid_converge/n_seeds:.0%})")
    print(f"  Random baseline rate:     {rand_converge}/{n_seeds} ({rand_converge/n_seeds:.0%})")
    print(f"  Avg score improvement:    {(avg_guid-avg_rand)/max(avg_rand,1e-9):+.1%}")
    if reductions:
        print(f"  Median sim reduction:     {float(np.median(reductions)):.0%} (when both converge)")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--n-seeds",     type=int,   default=10)
    parser.add_argument("--generations", type=int,   default=6)
    parser.add_argument("--n-candidates", type=int,  default=24)
    parser.add_argument("--area-acres",  type=float, default=10.0)
    args = parser.parse_args()
    run_report(
        n_seeds=args.n_seeds,
        generations=args.generations,
        n_candidates=args.n_candidates,
        area_acres=args.area_acres,
    )
