"""
Training Report Generator — model_lab Phase 10

Generates comprehensive reports on dataset composition, model accuracy,
version history, and search efficiency across all trained model versions.

Sections:
  1. Dataset composition (size, diversity, source breakdown)
  2. Model version history
  3. Model accuracy comparison (R², retention, rank accuracy)
  4. Search efficiency simulation (guided vs random, by version)
  5. Production data integration status

Usage:
    python -m model_lab.experiments.training_report [options]

    Options:
      --dataset <path>   Dataset to report on (default: merged_graph_training.jsonl)
      --all-versions     Compare all saved versions (slow)
      --save <path>      Save report to text file
      --verbose

No production code is imported.
"""

from __future__ import annotations

import argparse
import json
import pickle
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

MODELS_DIR   = REPO_ROOT / "model_lab" / "models"
DATASETS_DIR = REPO_ROOT / "model_lab" / "datasets"

VERSIONS_FILE     = MODELS_DIR / "versions.json"
MERGED_PATH       = DATASETS_DIR / "merged_graph_training.jsonl"
SYNTHETIC_PATH    = DATASETS_DIR / "graph_training.jsonl"
EXPERIENCE_PATH   = DATASETS_DIR / "layout_experience.jsonl"
CURRENT_MODEL     = MODELS_DIR / "graph_prior.pkl"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_versions() -> List[Dict]:
    if VERSIONS_FILE.exists():
        with open(VERSIONS_FILE) as f:
            return json.load(f)
    return []


def _load_model(path: Path) -> Optional[Dict]:
    try:
        with open(path, "rb") as f:
            return pickle.load(f)
    except Exception:
        return None


def _format_ts(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return iso[:16]


# ---------------------------------------------------------------------------
# Section 1 — Dataset composition
# ---------------------------------------------------------------------------

def report_dataset(path: Path, out: List[str]) -> Dict:
    def _h(s):
        out.append(s)

    _h(f"\n[1] Dataset Composition")
    _h("─" * 68)

    if not path.exists():
        _h(f"  Not found: {path}")
        return {}

    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except Exception:
                    pass

    if not records:
        _h("  Empty dataset")
        return {}

    scores      = [float(r.get("score", 0)) for r in records]
    lot_counts  = [int(r.get("lot_count", 0)) for r in records]
    parcel_ids  = {r.get("parcel_id", "") for r in records}
    type_counts = Counter(r.get("generator_type", "?") for r in records)
    sources     = Counter(r.get("source", "synthetic") for r in records)

    def _m(xs): return sum(xs) / max(len(xs), 1)
    def _s(xs):
        m = _m(xs)
        return (sum((x-m)**2 for x in xs) / max(len(xs)-1, 1)) ** 0.5

    _h(f"  File:          {path.name}")
    _h(f"  Records:       {len(records)}")
    _h(f"  Unique parcels:{len(parcel_ids)}")
    _h(f"  Score:         {_m(scores):.4f} ± {_s(scores):.4f}  "
       f"[{min(scores):.4f}, {max(scores):.4f}]")
    _h(f"  Avg lot count: {_m(lot_counts):.1f}")

    _h(f"\n  Source breakdown:")
    for src, cnt in sorted(sources.items()):
        pct = cnt / max(len(records), 1)
        bar = "█" * int(pct * 40)
        _h(f"    {src:16}  {cnt:5d}  ({pct:5.1%})  {bar}")

    _h(f"\n  Type breakdown:")
    for gt, cnt in sorted(type_counts.items()):
        pct = cnt / max(len(records), 1)
        bar = "█" * int(pct * 40)
        _h(f"    {gt:16}  {cnt:5d}  ({pct:5.1%})  {bar}")

    return {
        "n_records": len(records),
        "n_parcels": len(parcel_ids),
        "score_mean": _m(scores),
        "score_std": _s(scores),
        "type_counts": dict(type_counts),
        "source_counts": dict(sources),
    }


# ---------------------------------------------------------------------------
# Section 2 — Version history
# ---------------------------------------------------------------------------

def report_version_history(out: List[str]) -> None:
    def _h(s): out.append(s)

    _h(f"\n[2] Model Version History")
    _h("─" * 68)

    versions = _load_versions()

    # Baseline v1
    if CURRENT_MODEL.exists() and not versions:
        payload = _load_model(CURRENT_MODEL)
        if payload:
            _h(f"  v1  (baseline)  {payload.get('model_name', '?'):20}  "
               f"R²={payload.get('r2_test', 0):.4f}  "
               f"Top-5={payload.get('ret5', 0):.1%}  "
               f"dataset=1549")
            return

    if not versions:
        _h("  No version history found (models/versions.json missing)")
        _h("  Baseline model: graph_prior.pkl (Phase 8 trained)")
        return

    _h(f"  {'Ver':>3}  {'Date':>17}  {'Model':20}  {'R²':>6}  "
       f"{'Top-5':>7}  {'Top-10':>7}  {'Dataset':>8}  {'Sources'}")
    _h(f"  {'─'*3}  {'─'*17}  {'─'*20}  {'─'*6}  "
       f"{'─'*7}  {'─'*7}  {'─'*8}  {'─'*20}")

    for v in versions:
        m = v.get("metrics", {})
        ts = _format_ts(v.get("timestamp", ""))
        src = v.get("dataset_sources", {})
        src_str = "  ".join(f"{k}={n}" for k, n in sorted(src.items()))
        _h(f"  v{str(v.get('version', '?')):>2}  {ts:>17}  "
           f"{v.get('model_name','?'):20}  "
           f"{m.get('r2_test',0):6.4f}  "
           f"{m.get('top5_retention',0):7.1%}  "
           f"{m.get('top10_retention',0):7.1%}  "
           f"{v.get('dataset_size',0):8d}  "
           f"{src_str}")


# ---------------------------------------------------------------------------
# Section 3 — Model accuracy
# ---------------------------------------------------------------------------

def report_model_accuracy(
    dataset_path: Path,
    compare_all_versions: bool,
    out: List[str],
) -> None:
    def _h(s): out.append(s)

    from model_lab.training.train_graph_prior import (
        load_dataset, records_to_arrays, parcel_split,
        top_k_score_retention, ranking_accuracy,
    )
    from sklearn.metrics import r2_score

    _h(f"\n[3] Model Accuracy")
    _h("─" * 68)

    if not dataset_path.exists():
        _h(f"  Dataset not found: {dataset_path.name}")
        return

    records = load_dataset(dataset_path)
    X, y, _  = records_to_arrays(records)
    _, test_idx = parcel_split(records, seed=42)
    rec_test = [records[i] for i in test_idx]
    X_test   = X[test_idx]
    y_test   = y[test_idx]

    _h(f"  Dataset: {dataset_path.name}  ({len(records)} records, "
       f"{len(test_idx)} test)")

    def _eval_model(path: Path, label: str) -> Optional[Dict]:
        payload = _load_model(path)
        if payload is None:
            return None
        model  = payload["model"]
        preds  = model.predict(X_test)
        r2     = r2_score(y_test, preds)
        ret5   = top_k_score_retention(rec_test, preds, k=5)
        ret10  = top_k_score_retention(rec_test, preds, k=10)
        rank   = ranking_accuracy(rec_test, preds)
        return {"label": label, "r2": r2, "ret5": ret5, "ret10": ret10, "rank": rank}

    results = []

    # Current model
    r = _eval_model(CURRENT_MODEL, "current (graph_prior.pkl)")
    if r:
        results.append(r)

    # Versioned models
    if compare_all_versions:
        for vf in sorted(MODELS_DIR.glob("graph_prior_v*.pkl")):
            r = _eval_model(vf, vf.stem)
            if r:
                results.append(r)

    if not results:
        _h("  No models found to evaluate")
        return

    _h(f"\n  {'Model':32}  {'R²':>6}  {'Top-5':>7}  {'Top-10':>7}  {'RankAcc':>8}")
    _h(f"  {'─'*32}  {'─'*6}  {'─'*7}  {'─'*7}  {'─'*8}")
    for r in results:
        _h(f"  {r['label']:32}  {r['r2']:6.4f}  {r['ret5']:7.1%}  "
           f"{r['ret10']:7.1%}  {r['rank']:8.1%}")


# ---------------------------------------------------------------------------
# Section 4 — Search efficiency
# ---------------------------------------------------------------------------

def report_search_efficiency(out: List[str], n_seeds: int = 5) -> None:
    def _h(s): out.append(s)

    _h(f"\n[4] Search Efficiency (guided vs random, {n_seeds} seeds)")
    _h("─" * 68)

    try:
        from model_lab.experiments.guided_graph_search import run_guided_comparison
    except ImportError:
        _h("  SKIP — guided_graph_search not importable")
        return

    rand_scores, guid_scores = [], []
    rand_stb, guid_stb = [], []

    _h(f"  {'Seed':>4}  {'Random':>8}  {'Guided':>8}  {'Δ':>7}  "
       f"{'RandSTB':>8}  {'GuidSTB':>8}")
    _h(f"  {'─'*4}  {'─'*8}  {'─'*8}  {'─'*7}  {'─'*8}  {'─'*8}")

    for seed in range(n_seeds):
        try:
            rand_r, guid_r = run_guided_comparison(
                area_acres=10.0, parcel_shape="square",
                generations=4, n_candidates=16,
                seed=seed, verbose=False,
            )
            rand_scores.append(rand_r.best_score)
            guid_scores.append(guid_r.best_score)
            rand_stb.append(rand_r.sims_to_baseline)
            guid_stb.append(guid_r.sims_to_baseline)
            delta = guid_r.best_score - rand_r.best_score
            rstb = str(rand_r.sims_to_baseline) if rand_r.sims_to_baseline else "never"
            gstb = str(guid_r.sims_to_baseline) if guid_r.sims_to_baseline else "never"
            mark = "★" if delta > 0 else " "
            _h(f"  {seed:4d}{mark} {rand_r.best_score:8.4f}  {guid_r.best_score:8.4f}  "
               f"{delta:+7.4f}  {rstb:>8}  {gstb:>8}")
        except Exception as exc:
            _h(f"  {seed:4d}  ERROR: {exc}")

    if rand_scores and guid_scores:
        avg_rand = np.mean(rand_scores)
        avg_guid = np.mean(guid_scores)
        wins = sum(1 for r, g in zip(rand_scores, guid_scores) if g > r)
        pct  = (avg_guid - avg_rand) / max(avg_rand, 1e-9)

        paired = [(r, g) for r, g in zip(rand_stb, guid_stb) if r and g]
        reductions = [1.0 - g / r for r, g in paired if r > 0]

        _h(f"\n  Average:  random={avg_rand:.4f}  guided={avg_guid:.4f}  "
           f"Δ={avg_guid-avg_rand:+.4f} ({pct:+.1%})")
        _h(f"  Wins:     guided wins {wins}/{n_seeds} seeds")
        if reductions:
            _h(f"  Sim reduction (both converge): "
               f"mean={np.mean(reductions):.0%}  median={float(np.median(reductions)):.0%}")


# ---------------------------------------------------------------------------
# Section 5 — Production integration status
# ---------------------------------------------------------------------------

def report_production_status(out: List[str]) -> None:
    def _h(s): out.append(s)

    _h(f"\n[5] Production Data Integration Status")
    _h("─" * 68)

    # Experience dataset
    if EXPERIENCE_PATH.exists():
        records = []
        with open(EXPERIENCE_PATH) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except Exception:
                        pass
        sources = Counter(r.get("source", "?") for r in records)
        types   = Counter(r.get("generator_type", "?") for r in records)
        _h(f"  Experience dataset:  {len(records)} records")
        _h(f"  Sources:             {dict(sources)}")
        _h(f"  Types:               {dict(types)}")
        if records:
            scores = [float(r.get("score", 0)) for r in records]
            _h(f"  Score range:         {min(scores):.4f} – {max(scores):.4f}")
    else:
        _h(f"  Experience dataset:  Not yet created (no production data imported)")
        _h(f"  To import:  python -m model_lab.training.import_layout_logs "
           f"--input <production_log.jsonl>")

    # Version registry
    versions = _load_versions()
    _h(f"\n  Model versions:      {len(versions)} retrain(s) recorded")
    _h(f"  Version registry:    {'✓ exists' if VERSIONS_FILE.exists() else '✗ not yet created'}")
    _h(f"  Current model:       {'✓ exists' if CURRENT_MODEL.exists() else '✗ not found'}")

    # Versioned files
    versioned = sorted(MODELS_DIR.glob("graph_prior_v*.pkl"))
    if versioned:
        _h(f"  Versioned models:    {len(versioned)}  "
           f"({', '.join(f.stem for f in versioned[-3:])}{'...' if len(versioned) > 3 else ''})")
    else:
        _h(f"  Versioned models:    None (first retrain will create v2)")


# ---------------------------------------------------------------------------
# Main report
# ---------------------------------------------------------------------------

def run_report(
    dataset_path:   Optional[Path] = None,
    compare_all:    bool = False,
    save_path:      Optional[Path] = None,
    search_seeds:   int = 5,
    verbose:        bool = True,
) -> None:
    if dataset_path is None:
        dataset_path = MERGED_PATH if MERGED_PATH.exists() else SYNTHETIC_PATH

    lines: List[str] = []
    lines.append("=" * 68)
    lines.append("TRAINING REPORT — model_lab Phase 10 Continuous Learning")
    lines.append(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("=" * 68)

    report_dataset(dataset_path, lines)
    report_version_history(lines)
    report_model_accuracy(dataset_path, compare_all, lines)
    report_search_efficiency(lines, n_seeds=search_seeds)
    report_production_status(lines)

    lines.append(f"\n{'='*68}")
    lines.append("END OF REPORT")
    lines.append("=" * 68)

    full_report = "\n".join(lines)

    if verbose:
        print(full_report)

    if save_path:
        save_path = Path(save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, "w") as f:
            f.write(full_report + "\n")
        if verbose:
            print(f"\nReport saved → {save_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate training report for continuous learning system",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--dataset",      default=None, help="Dataset JSONL path")
    parser.add_argument("--all-versions", action="store_true",
                        help="Evaluate all saved model versions")
    parser.add_argument("--save",         default=None, help="Save report to file")
    parser.add_argument("--search-seeds", type=int, default=5,
                        help="Seeds for search efficiency evaluation")
    parser.add_argument("--verbose",      action="store_true", default=True)
    args = parser.parse_args()

    run_report(
        dataset_path=Path(args.dataset) if args.dataset else None,
        compare_all=args.all_versions,
        save_path=Path(args.save) if args.save else None,
        search_seeds=args.search_seeds,
        verbose=args.verbose,
    )
