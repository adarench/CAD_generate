"""
Road Graph Visualizer — model_lab

Loads a dataset record from layout_examples.jsonl and produces a matplotlib
plot showing:
  - Parcel polygon outline
  - Road graph edges (coloured by topology)
  - Nodes: red for intersections (degree ≥ 3), orange for dead ends (degree 1),
           grey for pass-through nodes (degree 2)
  - Node IDs as labels

Usage:
    # Visualize the first record in the default dataset:
    python model_lab/experiments/visualize_road_graph.py

    # Visualize record index N:
    python model_lab/experiments/visualize_road_graph.py --index 5

    # Visualize all topologies (one figure per topology, first match each):
    python model_lab/experiments/visualize_road_graph.py --topology all

    # Save to file instead of showing interactively:
    python model_lab/experiments/visualize_road_graph.py --output /tmp/graph.png

    # Visualize from a specific JSONL file:
    python model_lab/experiments/visualize_road_graph.py --file path/to/file.jsonl

No production code is modified.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DATASET_FILE = REPO_ROOT / "model_lab" / "datasets" / "layout_training" / "layout_examples.jsonl"

# ---------------------------------------------------------------------------
# Topology colour palette
# ---------------------------------------------------------------------------
TOPOLOGY_COLOURS = {
    "loop":      "#2196F3",   # blue
    "spine":     "#4CAF50",   # green
    "parallel":  "#FF9800",   # orange
    "culdesac":  "#9C27B0",   # purple
    "collector": "#607D8B",   # grey-blue
}
NODE_COLOURS = {
    "intersection": "#E53935",  # red  — degree >= 3
    "dead_end":     "#FF6F00",  # amber — degree == 1
    "through":      "#757575",  # grey  — degree == 2
    "isolated":     "#BDBDBD",  # light grey — degree == 0
}


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def _load_records(jsonl_path: Path) -> List[dict]:
    if not jsonl_path.exists():
        raise FileNotFoundError(f"Dataset file not found: {jsonl_path}")
    records = []
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return records


def _node_degrees(edges: List[dict]) -> Dict[int, int]:
    degrees: Dict[int, int] = {}
    for edge in edges:
        for key in ("from", "to"):
            nid = edge[key]
            degrees[nid] = degrees.get(nid, 0) + 1
    return degrees


def _classify_node(degree: int) -> str:
    if degree >= 3:
        return "intersection"
    if degree == 1:
        return "dead_end"
    if degree == 2:
        return "through"
    return "isolated"


def _exterior_ring(geojson: dict) -> List[Tuple[float, float]]:
    geom_type = geojson.get("type", "")
    coords = geojson.get("coordinates", [])
    if geom_type == "Polygon":
        ring = coords[0]
    elif geom_type == "MultiPolygon":
        ring = max(coords, key=lambda poly: len(poly[0]))[0]
    else:
        raise ValueError(f"Unsupported geometry type: {geom_type}")
    return [(float(c[0]), float(c[1])) for c in ring]


# ---------------------------------------------------------------------------
# Core plot function
# ---------------------------------------------------------------------------

def plot_road_graph(
    record: dict,
    ax=None,
    title: Optional[str] = None,
    show_node_ids: bool = True,
) -> "matplotlib.axes.Axes":
    """
    Draw a single road graph record onto a matplotlib Axes.

    Returns the Axes object.
    """
    try:
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        from matplotlib.patches import Polygon as MplPolygon
        from matplotlib.collections import PatchCollection
    except ImportError:
        raise RuntimeError(
            "matplotlib is required for visualization.\n"
            "Install it with: pip install matplotlib"
        )

    if ax is None:
        fig, ax = plt.subplots(figsize=(10, 10))

    road_graph = record.get("road_graph", {})
    nodes_data = road_graph.get("nodes", [])
    edges_data = road_graph.get("edges", [])
    metrics    = road_graph.get("metrics", {})
    topo       = record.get("layout_metrics", {}).get("network_topology", "unknown")
    parcel_geom = record.get("parcel_polygon", {})

    # ---- Parcel outline ------------------------------------------------
    try:
        ring = _exterior_ring(parcel_geom)
        xs = [p[0] for p in ring] + [ring[0][0]]
        ys = [p[1] for p in ring] + [ring[0][1]]
        ax.fill(xs, ys, alpha=0.06, color="#795548")
        ax.plot(xs, ys, color="#795548", linewidth=1.5, label="Parcel boundary")
    except Exception:
        pass

    # ---- Road edges ----------------------------------------------------
    edge_colour = TOPOLOGY_COLOURS.get(topo, "#607D8B")
    for edge in edges_data:
        coords = edge.get("coords", [])
        if len(coords) >= 2:
            ex = [c[0] for c in coords]
            ey = [c[1] for c in coords]
            ax.plot(ex, ey, color=edge_colour, linewidth=2.5, alpha=0.85, solid_capstyle="round")

    # ---- Nodes ---------------------------------------------------------
    degrees = _node_degrees(edges_data)
    node_by_id = {n["id"]: n for n in nodes_data}

    plotted_classes: set = set()
    for node in nodes_data:
        nid = node["id"]
        deg = degrees.get(nid, 0)
        cls = _classify_node(deg)
        colour = NODE_COLOURS[cls]
        size = 80 if cls == "intersection" else 50
        label = cls if cls not in plotted_classes else None
        ax.scatter(
            node["x"], node["y"],
            s=size, color=colour, zorder=5,
            label=label, edgecolors="white", linewidths=0.8,
        )
        plotted_classes.add(cls)
        if show_node_ids:
            ax.annotate(
                str(nid),
                (node["x"], node["y"]),
                textcoords="offset points",
                xytext=(5, 5),
                fontsize=7,
                color="#333333",
                zorder=6,
            )

    # ---- Title + metadata label ----------------------------------------
    parcel_id = record.get("parcel_id", "")
    lots = record.get("layout_metrics", {}).get("lot_count", "?")
    strat = record.get("strategy", {})
    density = strat.get("density_goal", "")
    score = record.get("score", {}).get("overall_score", 0)

    auto_title = (
        f"Road Graph — {topo.upper()}  |  {parcel_id[:20]}\n"
        f"lots={lots}  nodes={metrics.get('node_count','?')}  "
        f"edges={metrics.get('edge_count','?')}  "
        f"ixns={metrics.get('intersection_count','?')}  "
        f"dead_ends={metrics.get('dead_end_count','?')}  "
        f"diameter={metrics.get('graph_diameter','?')}  "
        f"score={score:.3f}  density={density}"
    )
    ax.set_title(title or auto_title, fontsize=9)
    ax.set_aspect("equal")
    ax.set_xlabel("x (feet)")
    ax.set_ylabel("y (feet)")
    ax.legend(fontsize=8, loc="lower right")
    ax.grid(True, alpha=0.2)

    return ax


# ---------------------------------------------------------------------------
# Multi-topology panel
# ---------------------------------------------------------------------------

def plot_topology_panel(records: List[dict], output: Optional[Path] = None) -> None:
    """Plot one example per topology in a 2×2 panel."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        raise RuntimeError("matplotlib is required: pip install matplotlib")

    topologies = ["loop", "spine", "parallel", "culdesac"]
    by_topo: Dict[str, Optional[dict]] = {t: None for t in topologies}
    for rec in records:
        topo = rec.get("layout_metrics", {}).get("network_topology")
        if topo in by_topo and by_topo[topo] is None:
            by_topo[topo] = rec

    fig, axes = plt.subplots(2, 2, figsize=(16, 16))
    fig.suptitle("Road Graph Extraction — All Topologies", fontsize=14, fontweight="bold")
    axes_flat = axes.flatten()

    for i, topo in enumerate(topologies):
        ax = axes_flat[i]
        rec = by_topo.get(topo)
        if rec is None:
            ax.set_title(f"{topo.upper()} — no examples found")
            ax.axis("off")
            continue
        plot_road_graph(rec, ax=ax, show_node_ids=True)

    plt.tight_layout()
    if output:
        plt.savefig(str(output), dpi=150, bbox_inches="tight")
        print(f"Saved panel to {output}")
    else:
        plt.show()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Visualize road graphs from the layout training dataset.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--file",     type=Path, default=DATASET_FILE,
                        help="Path to JSONL dataset file.")
    parser.add_argument("--index",    type=int, default=0,
                        help="Record index to visualize (0-based).")
    parser.add_argument("--topology", type=str, default=None,
                        choices=["loop", "spine", "parallel", "culdesac", "all"],
                        help="Filter by topology, or 'all' for a 2×2 panel.")
    parser.add_argument("--output",   type=Path, default=None,
                        help="Save figure to this path instead of showing interactively.")
    parser.add_argument("--no-ids",   action="store_true",
                        help="Hide node ID labels.")
    args = parser.parse_args()

    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("ERROR: matplotlib is required.\nInstall: pip install matplotlib")
        sys.exit(1)

    records = _load_records(args.file)
    if not records:
        print(f"No records found in {args.file}")
        sys.exit(1)

    print(f"Loaded {len(records)} records from {args.file}")

    if args.topology == "all":
        plot_topology_panel(records, output=args.output)
        return

    # Filter by topology if specified
    if args.topology:
        filtered = [r for r in records
                    if r.get("layout_metrics", {}).get("network_topology") == args.topology]
        if not filtered:
            print(f"No records with topology '{args.topology}'")
            sys.exit(1)
        record = filtered[min(args.index, len(filtered) - 1)]
    else:
        record = records[min(args.index, len(records) - 1)]

    topo = record.get("layout_metrics", {}).get("network_topology", "?")
    gm   = record.get("road_graph", {}).get("metrics", {})
    print(f"\nRecord:   {record.get('parcel_id')}")
    print(f"Topology: {topo}")
    print(f"Nodes:    {gm.get('node_count', '?')}")
    print(f"Edges:    {gm.get('edge_count', '?')}")
    print(f"Ixns:     {gm.get('intersection_count', '?')}")
    print(f"Dead ends:{gm.get('dead_end_count', '?')}")
    print(f"Diameter: {gm.get('graph_diameter', '?')}")

    fig, ax = plt.subplots(figsize=(10, 10))
    plot_road_graph(record, ax=ax, show_node_ids=not args.no_ids)
    plt.tight_layout()

    if args.output:
        plt.savefig(str(args.output), dpi=150, bbox_inches="tight")
        print(f"\nSaved to {args.output}")
    else:
        plt.show()


if __name__ == "__main__":
    main()
