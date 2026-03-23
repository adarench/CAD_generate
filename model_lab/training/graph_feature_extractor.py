"""
Graph Feature Extractor — model_lab Phase 8

Extracts structural topology features from a ProposedGraph for use as
inputs to the Graph Prior Model.

Features capture:
  - Size / density metrics
  - Connectivity structure
  - Shape / spatial layout
  - Topology type indicators

No production code is modified.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Set, Tuple

from model_lab.graph_models.road_graph import (
    NODE_DEAD_END,
    NODE_ENTRY,
    NODE_INTERSECTION,
    NODE_TERMINUS,
    GraphEdge,
    GraphNode,
    ProposedGraph,
)

# ---------------------------------------------------------------------------
# Feature name registry
# ---------------------------------------------------------------------------

GRAPH_FEATURE_NAMES: List[str] = [
    # --- basic counts ---
    "node_count",
    "edge_count",
    "intersection_count",
    "dead_end_count",
    "entry_count",
    # --- length metrics ---
    "total_road_length_ft",
    "avg_edge_length_ft",
    "min_edge_length_ft",
    "max_edge_length_ft",
    "edge_length_std_ft",
    "road_density_ft_per_acre",         # total_road_length / parcel_acres
    # --- connectivity ---
    "avg_node_degree",
    "max_node_degree",
    "branching_factor",                 # avg degree of intersection nodes
    "dead_end_ratio",                   # dead_ends / nodes
    "intersection_ratio",               # intersections / nodes
    "loop_count",                       # estimated # of independent cycles
    "connectivity_ratio",               # edges / nodes  (>1 implies cycles)
    # --- spatial layout ---
    "graph_diameter_ft",                # longest shortest-path (BFS on ft)
    "bbox_width_ft",
    "bbox_height_ft",
    "bbox_aspect_ratio",
    "centroid_offset_x",                # graph centroid normalized to bbox [-1,1]
    "centroid_offset_y",
    # --- topology descriptors ---
    "gridness",                         # fraction of angles near 0/90/180 deg
    "radial_symmetry",                  # variance of spoke-angle differences
    "parallelism",                      # fraction of edge-pairs with similar angle
    # --- type one-hot (6 types) ---
    "type_spine",
    "type_loop_custom",
    "type_grid",
    "type_herringbone",
    "type_radial",
    "type_t_junction",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _adjacency(graph: ProposedGraph) -> Dict[int, List[Tuple[int, float]]]:
    """Build adjacency list: nid → [(neighbor_nid, length_ft)]."""
    adj: Dict[int, List[Tuple[int, float]]] = {n.id: [] for n in graph.nodes}
    for e in graph.edges:
        adj.setdefault(e.from_node, []).append((e.to_node, e.length_ft))
        adj.setdefault(e.to_node,   []).append((e.from_node, e.length_ft))
    return adj


def _node_degrees(graph: ProposedGraph) -> Dict[int, int]:
    deg: Dict[int, int] = {n.id: 0 for n in graph.nodes}
    for e in graph.edges:
        deg[e.from_node] = deg.get(e.from_node, 0) + 1
        deg[e.to_node]   = deg.get(e.to_node,   0) + 1
    return deg


def _bfs_diameter(graph: ProposedGraph, adj: Dict) -> float:
    """Approximate graph diameter: BFS from each entry/intersection node, return max distance."""
    if not graph.nodes:
        return 0.0
    start_nodes = [n.id for n in graph.nodes
                   if n.type in (NODE_ENTRY, NODE_INTERSECTION)][:4]  # limit for speed
    if not start_nodes:
        start_nodes = [graph.nodes[0].id]

    max_dist = 0.0
    for src in start_nodes:
        dist = {src: 0.0}
        queue = [src]
        qi = 0
        while qi < len(queue):
            cur = queue[qi]; qi += 1
            for nbr, length in adj.get(cur, []):
                if nbr not in dist:
                    dist[nbr] = dist[cur] + length
                    queue.append(nbr)
        if dist:
            max_dist = max(max_dist, max(dist.values()))
    return max_dist


def _loop_count(graph: ProposedGraph) -> int:
    """
    Number of independent cycles = edges - nodes + connected_components
    (circuit rank / cyclomatic number).
    """
    if not graph.nodes:
        return 0
    node_ids = {n.id for n in graph.nodes}
    adj = _adjacency(graph)

    # Count connected components via BFS
    visited: Set[int] = set()
    components = 0
    for start in node_ids:
        if start not in visited:
            components += 1
            q = [start]
            qi = 0
            while qi < len(q):
                cur = q[qi]; qi += 1
                if cur in visited:
                    continue
                visited.add(cur)
                for nbr, _ in adj.get(cur, []):
                    if nbr not in visited:
                        q.append(nbr)

    return max(0, len(graph.edges) - len(graph.nodes) + components)


def _edge_angles(graph: ProposedGraph) -> List[float]:
    """Angle (degrees, 0–180) of each edge's primary direction."""
    angles = []
    for e in graph.edges:
        if len(e.coords) >= 2:
            dx = e.coords[-1][0] - e.coords[0][0]
            dy = e.coords[-1][1] - e.coords[0][1]
            if abs(dx) + abs(dy) > 1e-6:
                ang = math.degrees(math.atan2(dy, dx)) % 180
                angles.append(ang)
    return angles


def _gridness(angles: List[float]) -> float:
    """
    Fraction of edges whose angle is within 10° of 0, 90, or 180°.
    A perfect grid returns 1.0; a diagonal herringbone ~0.
    """
    if not angles:
        return 0.0
    near_axis = sum(
        1 for a in angles
        if min(a % 90, 90 - a % 90) < 10.0
    )
    return near_axis / len(angles)


def _radial_symmetry(graph: ProposedGraph) -> float:
    """
    Measure of radial symmetry: look at angles of edges from each
    high-degree intersection. If they are evenly distributed (like spokes),
    variance of angular gaps is low → high radial symmetry.
    Returns 1.0 for perfect radial, 0.0 for none.
    """
    adj = _adjacency(graph)
    node_map = {n.id: n for n in graph.nodes}
    deg = _node_degrees(graph)
    hub_nodes = [nid for nid, d in deg.items() if d >= 3]
    if not hub_nodes:
        return 0.0

    symmetry_scores = []
    for hub_id in hub_nodes:
        hub = node_map.get(hub_id)
        if not hub:
            continue
        spoke_angles = []
        for nbr_id, _ in adj.get(hub_id, []):
            nbr = node_map.get(nbr_id)
            if not nbr:
                continue
            ang = math.degrees(math.atan2(nbr.y - hub.y, nbr.x - hub.x)) % 360
            spoke_angles.append(ang)
        if len(spoke_angles) < 2:
            continue
        spoke_angles.sort()
        gaps = [(spoke_angles[(i+1) % len(spoke_angles)] - spoke_angles[i]) % 360
                for i in range(len(spoke_angles))]
        ideal_gap = 360.0 / len(gaps)
        variance = sum((g - ideal_gap)**2 for g in gaps) / len(gaps)
        max_variance = ideal_gap ** 2
        symmetry_scores.append(1.0 - min(variance / max(max_variance, 1.0), 1.0))

    return sum(symmetry_scores) / len(symmetry_scores) if symmetry_scores else 0.0


def _parallelism(angles: List[float]) -> float:
    """
    Fraction of edge-pairs that are parallel (angle difference < 15°).
    High in grids and spines; low in radial/herringbone.
    """
    if len(angles) < 2:
        return 0.0
    pairs = 0
    parallel = 0
    for i in range(len(angles)):
        for j in range(i + 1, min(i + 8, len(angles))):  # limit O(n²) for large graphs
            diff = abs(angles[i] - angles[j]) % 180
            diff = min(diff, 180 - diff)
            pairs += 1
            if diff < 15.0:
                parallel += 1
    return parallel / max(pairs, 1)


# ---------------------------------------------------------------------------
# Main extractor
# ---------------------------------------------------------------------------

def extract_graph_features(
    graph: ProposedGraph,
    parcel_area_sqft: float = 0.0,
) -> Dict[str, float]:
    """
    Extract all structural features from a ProposedGraph.

    Args:
        graph:            ProposedGraph to featurize
        parcel_area_sqft: used for road density; falls back to graph.parcel_area_sqft

    Returns:
        Dict mapping feature name → float value.
    """
    area = parcel_area_sqft or graph.parcel_area_sqft or 43560.0
    acres = area / 43560.0

    m = graph.metrics
    nodes = graph.nodes
    edges = graph.edges

    # --- basic counts ---
    n_nodes        = len(nodes)
    n_edges        = len(edges)
    n_intersect    = m.intersection_count
    n_dead         = m.dead_end_count
    n_entry        = m.entry_count

    # --- length metrics ---
    lengths = [e.length_ft for e in edges]
    total_len = sum(lengths)
    avg_len   = total_len / n_edges if n_edges else 0.0
    min_len   = min(lengths) if lengths else 0.0
    max_len   = max(lengths) if lengths else 0.0
    std_len   = (sum((l - avg_len)**2 for l in lengths) / n_edges)**0.5 if n_edges > 1 else 0.0
    density   = total_len / max(acres, 0.1)

    # --- connectivity ---
    deg = _node_degrees(graph)
    degrees = list(deg.values())
    avg_deg = sum(degrees) / n_nodes if n_nodes else 0.0
    max_deg = max(degrees) if degrees else 0
    inter_degrees = [deg[n.id] for n in nodes if n.type == NODE_INTERSECTION]
    branch_factor = sum(inter_degrees) / len(inter_degrees) if inter_degrees else 0.0
    dead_ratio    = n_dead / max(n_nodes, 1)
    inter_ratio   = n_intersect / max(n_nodes, 1)
    loops         = _loop_count(graph)
    conn_ratio    = n_edges / max(n_nodes, 1)

    # --- spatial layout ---
    adj = _adjacency(graph)
    diameter = _bfs_diameter(graph, adj)

    xs = [n.x for n in nodes]
    ys = [n.y for n in nodes]
    if xs:
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        bw = max_x - min_x
        bh = max_y - min_y
        aspect = max(bw, bh) / max(min(bw, bh), 1.0)
        cx = (min_x + max_x) / 2
        cy = (min_y + max_y) / 2
        gcx = sum(xs) / len(xs)
        gcy = sum(ys) / len(ys)
        # Normalize offset to [-1, 1] relative to half bbox
        cx_off = (gcx - cx) / max(bw / 2, 1.0)
        cy_off = (gcy - cy) / max(bh / 2, 1.0)
    else:
        bw = bh = aspect = cx_off = cy_off = 0.0

    # --- topology descriptors ---
    angles = _edge_angles(graph)
    gridness     = _gridness(angles)
    radial_sym   = _radial_symmetry(graph)
    parallel     = _parallelism(angles)

    # --- type one-hot ---
    gt = graph.generator_type
    type_spine      = 1.0 if gt == "spine"       else 0.0
    type_loop       = 1.0 if gt == "loop_custom" else 0.0
    type_grid       = 1.0 if gt == "grid"        else 0.0
    type_herring    = 1.0 if gt == "herringbone" else 0.0
    type_radial     = 1.0 if gt == "radial"      else 0.0
    type_tjunc      = 1.0 if gt == "t_junction"  else 0.0

    return {
        "node_count":            float(n_nodes),
        "edge_count":            float(n_edges),
        "intersection_count":    float(n_intersect),
        "dead_end_count":        float(n_dead),
        "entry_count":           float(n_entry),
        "total_road_length_ft":  total_len,
        "avg_edge_length_ft":    avg_len,
        "min_edge_length_ft":    min_len,
        "max_edge_length_ft":    max_len,
        "edge_length_std_ft":    std_len,
        "road_density_ft_per_acre": density,
        "avg_node_degree":       avg_deg,
        "max_node_degree":       float(max_deg),
        "branching_factor":      branch_factor,
        "dead_end_ratio":        dead_ratio,
        "intersection_ratio":    inter_ratio,
        "loop_count":            float(loops),
        "connectivity_ratio":    conn_ratio,
        "graph_diameter_ft":     diameter,
        "bbox_width_ft":         bw,
        "bbox_height_ft":        bh,
        "bbox_aspect_ratio":     aspect,
        "centroid_offset_x":     cx_off,
        "centroid_offset_y":     cy_off,
        "gridness":              gridness,
        "radial_symmetry":       radial_sym,
        "parallelism":           parallel,
        "type_spine":            type_spine,
        "type_loop_custom":      type_loop,
        "type_grid":             type_grid,
        "type_herringbone":      type_herring,
        "type_radial":           type_radial,
        "type_t_junction":       type_tjunc,
    }


def features_to_array(features: Dict[str, float]) -> "list[float]":
    """Return feature values in canonical GRAPH_FEATURE_NAMES order."""
    return [features.get(k, 0.0) for k in GRAPH_FEATURE_NAMES]
