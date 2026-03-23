"""
Graph → Strategy Adapter — model_lab

Converts a ProposedGraph's centerlines into a StreetNetworkCandidate
that the deterministic layout engine can consume directly.

This is the bridge between the graph proposal layer and the production engine.
No production code is modified — we only import production types read-only
and create instances of them.

Usage:
    from model_lab.graph_models.graph_to_strategy import graph_to_candidate
    candidate = graph_to_candidate(proposed_graph, road_width_ft=32.0)
    layout = generate_subdivision(constraints, zoning, candidate, target_lots)
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from model_lab.graph_models.road_graph import ProposedGraph


# ---------------------------------------------------------------------------
# Topology label inference
# ---------------------------------------------------------------------------

_TOPOLOGY_MAP = {
    "spine":       "spine",
    "loop_custom": "loop",
    "grid":        "parallel",     # closest existing label
    "herringbone": "spine",        # closest — has a spine + branches
    "radial":      "loop",         # closest — has connectivity rings
    "t_junction":  "spine",
}

def _infer_topology(generator_type: str) -> str:
    return _TOPOLOGY_MAP.get(generator_type, "collector")


def _infer_orientation(graph: ProposedGraph) -> str:
    """
    Infer road orientation from entry node direction.
    Entry node near south/north edge → north_south.
    """
    if not graph.nodes:
        return "north_south"
    entry_nodes = [n for n in graph.nodes if n.type == "entry"]
    if not entry_nodes:
        return "north_south"
    en = entry_nodes[0]
    xs = [n.x for n in graph.nodes]
    ys = [n.y for n in graph.nodes]
    if not xs:
        return "north_south"
    cx = (min(xs) + max(xs)) / 2.0
    cy = (min(ys) + max(ys)) / 2.0
    # Entry near top/bottom → north_south roads
    dy = abs(en.y - cy)
    dx = abs(en.x - cx)
    return "north_south" if dy >= dx else "east_west"


# ---------------------------------------------------------------------------
# Corridor computation
# ---------------------------------------------------------------------------

def _make_corridors(centerlines, road_width_ft: float):
    """Buffer each centerline to create road corridor polygons."""
    from shapely.geometry import LineString
    corridors = []
    half_w = road_width_ft / 2.0
    for line in centerlines:
        if not isinstance(line, LineString):
            continue
        try:
            buf = line.buffer(half_w, cap_style=2, join_style=2)  # square caps
            if not buf.is_empty:
                corridors.append(buf)
        except Exception:
            pass
    return corridors


# ---------------------------------------------------------------------------
# Main converter
# ---------------------------------------------------------------------------

def graph_to_candidate(
    graph: ProposedGraph,
    road_width_ft: float = 32.0,
    min_edge_length: float = 5.0,
) -> Optional[object]:
    """
    Convert a ProposedGraph to a StreetNetworkCandidate.

    Args:
        graph:           ProposedGraph from model_lab generators
        road_width_ft:   road width for corridor computation
        min_edge_length: edges shorter than this are filtered out

    Returns:
        StreetNetworkCandidate (production type) or None if conversion fails.
    """
    try:
        from ai_subdivision.street_network import StreetNetworkCandidate
        from shapely.geometry import LineString
    except ImportError:
        return None

    centerlines = []
    for line in graph.to_centerlines():
        if line.length >= min_edge_length:
            centerlines.append(line)

    if not centerlines:
        return None

    corridors = _make_corridors(centerlines, road_width_ft)
    if not corridors:
        return None

    topology    = _infer_topology(graph.generator_type)
    orientation = _infer_orientation(graph)
    m = graph.metrics
    metadata = {
        "road_count":    float(m.edge_count),
        "offset_ft":     0.0,
        "generator":     graph.generator_type,
        "node_count":    float(m.node_count),
        "road_length_ft": m.total_road_length_ft,
    }
    metadata.update({k: float(v) for k, v in graph.params.items()
                     if isinstance(v, (int, float))})

    try:
        candidate = StreetNetworkCandidate(
            topology=topology,
            centerlines=centerlines,
            corridors=corridors,
            orientation=orientation,
            metadata=metadata,
        )
        return candidate
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Batch conversion
# ---------------------------------------------------------------------------

def graphs_to_candidates(
    graphs: List[ProposedGraph],
    road_width_ft: float = 32.0,
) -> List[Tuple[ProposedGraph, object]]:
    """
    Convert a list of ProposedGraphs to (graph, candidate) pairs.
    Graphs that fail conversion are skipped.
    """
    results = []
    for g in graphs:
        cand = graph_to_candidate(g, road_width_ft=road_width_ft)
        if cand is not None:
            results.append((g, cand))
    return results
