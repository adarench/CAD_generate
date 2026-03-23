"""
Strategy Ranker Analysis — model_lab

Visualisation and diagnostics for the trained strategy ranking model.

Produces a 3-panel figure:
  Panel 1 — Predicted vs Actual score scatter (with topology colour)
  Panel 2 — Feature importance bar chart (top 20 features)
  Panel 3 — Top strategies per parcel (heat-map of predicted scores)

Usage:
    python model_lab/experiments/strategy_ranker_analysis.py

    # Save to file:
    python model_lab/experiments/strategy_ranker_analysis.py --output /tmp/ranker.png

    # Use a specific model or dataset:
    python model_lab/experiments/strategy_ranker_analysis.py \\
        --model model_lab/models/strategy_ranker.pkl \\
        --dataset model_lab/datasets/layout_training/layout_examples.jsonl

No production code is modified.
"""

from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from model_lab.training.feature_extractor import ALL_FEATURE_NAMES, records_to_arrays
from model_lab.training.train_strategy_ranker import (
    load_jsonl,
    parcel_stratified_split,
    ranking_accuracy,
)

DATASET_FILE = REPO_ROOT / "model_lab" / "datasets" / "layout_training" / "layout_examples.jsonl"
MODEL_PATH   = REPO_ROOT / "model_lab" / "models" / "strategy_ranker.pkl"

TOPOLOGY_COLOURS = {
    "loop":      "#2196F3",
    "spine":     "#4CAF50",
    "parallel":  "#FF9800",
    "culdesac":  "#9C27B0",
}


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------

def _load_model(path: Path):
    with open(path, "rb") as f:
        payload = pickle.load(f)
    return payload["model"], payload.get("feature_names", ALL_FEATURE_NAMES), payload.get("metadata", {})


# ---------------------------------------------------------------------------
# Panel 1 — Predicted vs Actual
# ---------------------------------------------------------------------------

def _plot_pred_vs_actual(ax, records, model, feature_names) -> dict:
    X, y_true, _ = records_to_arrays(records, feature_names=feature_names)
    y_pred = model.predict(X)

    topologies = [r.get("layout_metrics", r.get("strategy", {})).get("network_topology",
                         r.get("strategy", {}).get("road_type", "?"))
                  for r in records]

    from sklearn.metrics import r2_score, mean_squared_error
    r2   = r2_score(y_true, y_pred)
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))

    for topo in ["loop", "spine", "parallel", "culdesac"]:
        mask = [t == topo for t in topologies]
        if any(mask):
            ax.scatter(
                [y_true[i] for i, m in enumerate(mask) if m],
                [y_pred[i] for i, m in enumerate(mask) if m],
                s=18, alpha=0.55, c=TOPOLOGY_COLOURS.get(topo, "#607D8B"),
                label=topo, edgecolors="none",
            )

    # Perfect-prediction line
    lo = min(y_true.min(), y_pred.min())
    hi = max(y_true.max(), y_pred.max())
    ax.plot([lo, hi], [lo, hi], "k--", linewidth=1.2, alpha=0.6, label="perfect")

    ax.set_xlabel("Actual score",    fontsize=10)
    ax.set_ylabel("Predicted score", fontsize=10)
    ax.set_title(f"Predicted vs Actual  (R²={r2:.4f}, RMSE={rmse:.4f})", fontsize=11)
    ax.legend(fontsize=8, loc="upper left")
    ax.grid(True, alpha=0.2)
    return {"r2": r2, "rmse": rmse, "y_true": y_true, "y_pred": y_pred}


# ---------------------------------------------------------------------------
# Panel 2 — Feature Importance
# ---------------------------------------------------------------------------

def _plot_feature_importance(ax, model, feature_names, top_n=20) -> None:
    importances = model.feature_importances_
    pairs = sorted(zip(feature_names, importances), key=lambda t: t[1], reverse=True)[:top_n]
    names, vals = zip(*pairs)

    colours = []
    for name in names:
        if name.startswith("parcel_"):
            colours.append("#795548")
        elif name.startswith("strat_road"):
            colours.append("#2196F3")
        elif name.startswith("strat_density"):
            colours.append("#FF9800")
        elif name.startswith("strat_entry"):
            colours.append("#9E9E9E")
        elif name.startswith("graph_"):
            colours.append("#4CAF50")
        else:
            colours.append("#607D8B")

    y_pos = np.arange(len(names))
    ax.barh(y_pos, vals, color=colours, edgecolor="white", linewidth=0.5)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(names, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("Feature importance", fontsize=10)
    ax.set_title(f"Top {top_n} Feature Importances", fontsize=11)
    ax.grid(True, alpha=0.2, axis="x")

    # Legend for colour groups
    import matplotlib.patches as mpatches
    legend_patches = [
        mpatches.Patch(color="#795548", label="Parcel geometry"),
        mpatches.Patch(color="#2196F3", label="Road type"),
        mpatches.Patch(color="#FF9800", label="Density goal"),
        mpatches.Patch(color="#4CAF50", label="Road graph"),
        mpatches.Patch(color="#9E9E9E", label="Entry point"),
    ]
    ax.legend(handles=legend_patches, fontsize=7, loc="lower right")


# ---------------------------------------------------------------------------
# Panel 3 — Top strategies per parcel heatmap
# ---------------------------------------------------------------------------

def _plot_top_strategies(ax, records, model, feature_names, max_parcels=20) -> None:
    X, y_true, _ = records_to_arrays(records, feature_names=feature_names)
    y_pred = model.predict(X)

    # Group by parcel
    parcel_groups: Dict[str, List[int]] = {}
    for i, rec in enumerate(records):
        pid = rec["parcel_id"]
        parcel_groups.setdefault(pid, []).append(i)

    # Sort parcels by their best actual score and pick top max_parcels
    parcel_best = {pid: max(y_true[idxs]) for pid, idxs in parcel_groups.items()}
    top_parcels = sorted(parcel_best, key=parcel_best.get, reverse=True)[:max_parcels]

    # For each selected parcel, find the best strategy (by predicted score)
    road_types = ["loop", "spine", "parallel", "culdesac"]
    density_goals = ["low", "medium", "high"]
    strategy_labels = [f"{rt[:3]}/{dg[:1]}" for rt in road_types for dg in density_goals]

    heat = np.full((len(top_parcels), len(strategy_labels)), np.nan)

    for row_i, pid in enumerate(top_parcels):
        idxs = parcel_groups[pid]
        for idx in idxs:
            rec = records[idx]
            s = rec.get("strategy", {})
            rt = s.get("road_type", "")
            dg = s.get("density_goal", "")
            lbl = f"{rt[:3]}/{dg[:1]}"
            if lbl in strategy_labels:
                col_j = strategy_labels.index(lbl)
                heat[row_i, col_j] = float(y_pred[idx])

    # Normalise each row so colours are relative per parcel
    row_min = np.nanmin(heat, axis=1, keepdims=True)
    row_max = np.nanmax(heat, axis=1, keepdims=True)
    heat_norm = (heat - row_min) / np.maximum(row_max - row_min, 1e-9)

    im = ax.imshow(heat_norm, aspect="auto", cmap="YlOrRd", vmin=0, vmax=1)
    ax.set_xticks(range(len(strategy_labels)))
    ax.set_xticklabels(strategy_labels, rotation=45, ha="right", fontsize=7)
    ax.set_yticks(range(len(top_parcels)))
    ax.set_yticklabels([pid[:18] for pid in top_parcels], fontsize=7)
    ax.set_xlabel("Strategy (road/density)", fontsize=10)
    ax.set_title(f"Predicted Score Heatmap — Top {len(top_parcels)} Parcels\n(normalised per row; yellow=best)", fontsize=10)

    import matplotlib.pyplot as plt
    plt.colorbar(im, ax=ax, fraction=0.02, pad=0.04, label="Normalised predicted score")


# ---------------------------------------------------------------------------
# Main analysis function
# ---------------------------------------------------------------------------

def run_analysis(
    model_path: Path = MODEL_PATH,
    dataset_path: Path = DATASET_FILE,
    output: Optional[Path] = None,
) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("ERROR: matplotlib required. Install: pip install matplotlib")
        sys.exit(1)

    # Load data
    print(f"Loading model: {model_path}")
    model, feature_names, metadata = _load_model(model_path)
    print(f"  Model: {metadata.get('model_type','?')}  "
          f"R²={metadata.get('test_r2',0):.4f}  "
          f"RMSE={metadata.get('test_rmse',0):.4f}  "
          f"rank_acc={metadata.get('ranking_accuracy',0):.1%}")

    print(f"Loading dataset: {dataset_path}")
    records = load_jsonl(dataset_path)
    print(f"  Records: {len(records)}")

    # Use the held-out test split for honest evaluation
    _, test_records = parcel_stratified_split(records, test_fraction=0.20)
    print(f"  Test records (20%): {len(test_records)}")

    rank_acc = ranking_accuracy(model, test_records,
                                *records_to_arrays(test_records, feature_names=feature_names)[:2])

    # Build figure
    fig, axes = plt.subplots(1, 3, figsize=(20, 7))
    fig.suptitle(
        f"Strategy Ranker Analysis  —  {metadata.get('model_type','Model')}\n"
        f"Test R²={metadata.get('test_r2',0):.4f}  "
        f"RMSE={metadata.get('test_rmse',0):.4f}  "
        f"Top-1 Ranking Accuracy={rank_acc:.1%}  "
        f"({metadata.get('n_train',0)} train / {metadata.get('n_test',0)} test records)",
        fontsize=12, fontweight="bold",
    )

    # Panel 1
    pred_stats = _plot_pred_vs_actual(axes[0], test_records, model, feature_names)
    # Panel 2
    _plot_feature_importance(axes[1], model, feature_names, top_n=20)
    # Panel 3
    _plot_top_strategies(axes[2], test_records, model, feature_names, max_parcels=20)

    plt.tight_layout()
    if output:
        plt.savefig(str(output), dpi=150, bbox_inches="tight")
        print(f"\nSaved → {output}")
    else:
        plt.show()

    # Print console summary
    print(f"\n{'='*56}")
    print("RANKER ANALYSIS SUMMARY")
    print(f"{'='*56}")
    print(f"  Test R²:              {pred_stats['r2']:.4f}")
    print(f"  Test RMSE:            {pred_stats['rmse']:.4f}")
    print(f"  Top-1 rank accuracy:  {rank_acc:.1%}")

    # Topology-level accuracy
    X_test, y_test, _ = records_to_arrays(test_records, feature_names=feature_names)
    y_pred = model.predict(X_test)
    from sklearn.metrics import r2_score
    for topo in ["loop", "spine", "parallel", "culdesac"]:
        mask = np.array([
            r.get("layout_metrics", r.get("strategy", {})).get("network_topology",
                   r.get("strategy", {}).get("road_type", "")) == topo
            for r in test_records
        ])
        if mask.sum() >= 2:
            r2_topo = r2_score(y_test[mask], y_pred[mask])
            print(f"  R² ({topo:10s}):     {r2_topo:.4f}  (n={mask.sum()})")
    print(f"{'='*56}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(
        description="Analyse and visualise the trained strategy ranker.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--model",   type=Path, default=MODEL_PATH)
    parser.add_argument("--dataset", type=Path, default=DATASET_FILE)
    parser.add_argument("--output",  type=Path, default=None,
                        help="Save figure to this path (PNG/PDF).")
    args = parser.parse_args()
    run_analysis(model_path=args.model, dataset_path=args.dataset, output=args.output)


if __name__ == "__main__":
    main()
