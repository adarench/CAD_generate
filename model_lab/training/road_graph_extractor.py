"""
Road Graph Extractor — model_lab

Converts the StreetNetworkCandidate centerlines from the layout engine into
a topological road graph suitable for ML training.

Graph representation:
  nodes  = road endpoints + intersection points (spatially snapped)
  edges  = road segments between consecutive nodes

No production code is modified. Shapely is used for intersection geometry.

Topology notes by network type:
  parallel  — 2-4 parallel lines, no cross-intersections → chains of edges
  spine     — 1 collector + N perpendicular branches → T/X intersection nodes
  loop      — closed loop ring + 1 connector → 2 nodes, 3 edges
  culdesac  — stem + circular bulb → entry node + bulb junction + arc self-loop
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shapely.geometry import LineString, MultiPoint, Point
from shapely.ops import substring

# ---------------------------------------------------------------------------
# Tolerance for snapping nearby points to the same node
# ---------------------------------------------------------------------------
SNAP_TOLERANCE_FT = 1.5


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class RoadNode:
    id: int
    x: float
    y: float

    def to_dict(self) -> dict:
        return {"id": self.id, "x": round(self.x, 4), "y": round(self.y, 4)}


@dataclass
class RoadEdge:
    from_node: int
    to_node: int
    length_ft: float
    coords: List[List[float]]  # polyline vertices for visualisation

    def to_dict(self) -> dict:
        return {
            "from": self.from_node,
            "to": self.to_node,
            "length": round(self.length_ft, 2),
            "coords": [[round(x, 4), round(y, 4)] for x, y in self.coords],
        }


@dataclass
class GraphMetrics:
    node_count: int
    edge_count: int
    intersection_count: int   # nodes with degree >= 3
    dead_end_count: int        # nodes with degree == 1
    avg_edge_length_ft: float
    max_edge_length_ft: float
    total_road_length_ft: float
    road_density_ft_per_acre: float  # total road ft per acre of parcel
    graph_diameter: int              # longest shortest path in edge hops

    def to_dict(self) -> dict:
        return {
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "intersection_count": self.intersection_count,
            "dead_end_count": self.dead_end_count,
            "avg_edge_length_ft": round(self.avg_edge_length_ft, 2),
            "max_edge_length_ft": round(self.max_edge_length_ft, 2),
            "total_road_length_ft": round(self.total_road_length_ft, 2),
            "road_density_ft_per_acre": round(self.road_density_ft_per_acre, 4),
            "graph_diameter": self.graph_diameter,
        }


@dataclass
class RoadGraph:
    nodes: List[RoadNode]
    edges: List[RoadEdge]
    metrics: GraphMetrics

    def to_dict(self) -> dict:
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "metrics": self.metrics.to_dict(),
        }


# ---------------------------------------------------------------------------
# Node registry with spatial snapping
# ---------------------------------------------------------------------------

class _NodeRegistry:
    """Incrementally builds a node list, merging nearby points."""

    def __init__(self, snap_tolerance: float = SNAP_TOLERANCE_FT):
        self._nodes: List[RoadNode] = []
        self._snap = snap_tolerance

    def add(self, x: float, y: float) -> int:
        """Return the id of an existing nearby node or create a new one."""
        for node in self._nodes:
            if math.hypot(node.x - x, node.y - y) <= self._snap:
                return node.id
        new_id = len(self._nodes)
        self._nodes.append(RoadNode(id=new_id, x=x, y=y))
        return new_id

    def find(self, x: float, y: float) -> Optional[int]:
        """Return the id of a nearby node or None."""
        for node in self._nodes:
            if math.hypot(node.x - x, node.y - y) <= self._snap:
                return node.id
        return None

    def nodes(self) -> List[RoadNode]:
        return list(self._nodes)


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _is_closed(line: LineString) -> bool:
    """Return True if the line's first and last coordinates coincide."""
    coords = list(line.coords)
    if len(coords) < 2:
        return False
    return math.hypot(coords[0][0] - coords[-1][0], coords[0][1] - coords[-1][1]) < SNAP_TOLERANCE_FT


def _extract_shapely_points(geometry) -> List[Tuple[float, float]]:
    """Flatten any shapely geometry into a list of (x, y) coordinate pairs."""
    if geometry.is_empty:
        return []
    if geometry.geom_type == "Point":
        return [(geometry.x, geometry.y)]
    if geometry.geom_type in ("MultiPoint", "GeometryCollection"):
        pts = []
        for part in geometry.geoms:
            pts.extend(_extract_shapely_points(part))
        return pts
    if geometry.geom_type == "LineString":
        return [(geometry.coords[0][0], geometry.coords[0][1])]
    return []


def _nodes_along_line(
    line: LineString,
    registry: _NodeRegistry,
    snap: float = SNAP_TOLERANCE_FT,
) -> List[Tuple[float, int]]:
    """
    Return (arc_distance, node_id) pairs for all registered nodes that lie on `line`.

    A node is considered "on" the line if its nearest point on the line is within
    `snap` feet of the node itself.
    """
    result: List[Tuple[float, int]] = []
    for node in registry.nodes():
        pt = Point(node.x, node.y)
        dist = line.project(pt)
        nearest = line.interpolate(dist)
        if math.hypot(nearest.x - node.x, nearest.y - node.y) <= snap:
            result.append((dist, node.id))
    # Deduplicate by node_id
    seen: set = set()
    unique = []
    for d, nid in result:
        if nid not in seen:
            seen.add(nid)
            unique.append((d, nid))
    unique.sort(key=lambda t: t[0])
    return unique


def _line_to_coords(line: LineString) -> List[List[float]]:
    return [[float(x), float(y)] for x, y in line.coords]


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_road_graph(
    centerlines: List[LineString],
    parcel_area_sqft: float = 0.0,
) -> RoadGraph:
    """
    Build a road graph from the StreetNetworkCandidate centerlines.

    Args:
        centerlines:      list of Shapely LineString objects from StreetNetworkCandidate
        parcel_area_sqft: used to compute road_density_ft_per_acre

    Returns:
        RoadGraph with nodes, edges, and computed metrics.
    """
    if not centerlines:
        empty_metrics = GraphMetrics(
            node_count=0, edge_count=0, intersection_count=0,
            dead_end_count=0, avg_edge_length_ft=0.0, max_edge_length_ft=0.0,
            total_road_length_ft=0.0, road_density_ft_per_acre=0.0, graph_diameter=0,
        )
        return RoadGraph(nodes=[], edges=[], metrics=empty_metrics)

    registry = _NodeRegistry()

    # ------------------------------------------------------------------
    # Pass 1 — Register all endpoints and pairwise intersection points
    # ------------------------------------------------------------------
    for line in centerlines:
        coords = list(line.coords)
        if not coords:
            continue
        # Start endpoint
        registry.add(*coords[0][:2])
        # End endpoint (only if not a closed ring — avoids duplicate node)
        if not _is_closed(line):
            registry.add(*coords[-1][:2])

    # Pairwise intersections
    for i, line_a in enumerate(centerlines):
        for line_b in centerlines[i + 1:]:
            try:
                ix = line_a.intersection(line_b)
            except Exception:
                continue
            for x, y in _extract_shapely_points(ix):
                registry.add(x, y)

    # ------------------------------------------------------------------
    # Pass 2 — Split each centerline into edges at registered nodes
    # ------------------------------------------------------------------
    edges: List[RoadEdge] = []

    for line in centerlines:
        closed = _is_closed(line)
        total_len = line.length
        if total_len < 0.1:
            continue

        # Find all nodes on this line and their arc-distances
        node_stops = _nodes_along_line(line, registry)

        if len(node_stops) < 2:
            # No split points found — entire line is one edge with its two endpoints
            coords_list = list(line.coords)
            if not coords_list:
                continue
            n_start = registry.add(*coords_list[0][:2])
            n_end = registry.add(*coords_list[-1][:2]) if not closed else n_start
            seg = line
            edges.append(RoadEdge(
                from_node=n_start,
                to_node=n_end,
                length_ft=float(seg.length),
                coords=_line_to_coords(seg),
            ))
            continue

        # For a closed line, ensure we wrap the last segment back to the first node
        if closed:
            first_d, first_nid = node_stops[0]
            last_d, last_nid = node_stops[-1]
            # Add a synthetic stop at total_len mapped back to first_nid so the ring closes
            if abs(last_d - total_len) > SNAP_TOLERANCE_FT:
                node_stops.append((total_len, first_nid))

        # Create one edge per consecutive pair of stops
        for k in range(len(node_stops) - 1):
            d_start, n_start = node_stops[k]
            d_end, n_end = node_stops[k + 1]

            if abs(d_end - d_start) < 0.1:
                continue  # zero-length segment — skip

            try:
                seg = substring(line, d_start, d_end)
            except Exception:
                continue

            if seg.is_empty or seg.length < 0.1:
                continue

            # Normalise segment to a LineString (substring can return Point for zero-len)
            if seg.geom_type != "LineString":
                continue

            edges.append(RoadEdge(
                from_node=n_start,
                to_node=n_end,
                length_ft=float(seg.length),
                coords=_line_to_coords(seg),
            ))

    # ------------------------------------------------------------------
    # Pass 3 — Compute graph metrics
    # ------------------------------------------------------------------
    nodes = registry.nodes()
    degrees: Dict[int, int] = {n.id: 0 for n in nodes}
    for edge in edges:
        degrees[edge.from_node] = degrees.get(edge.from_node, 0) + 1
        degrees[edge.to_node] = degrees.get(edge.to_node, 0) + 1

    intersection_count = sum(1 for d in degrees.values() if d >= 3)
    dead_end_count = sum(1 for d in degrees.values() if d == 1)

    edge_lengths = [e.length_ft for e in edges]
    total_road_ft = sum(edge_lengths)
    avg_edge_ft = total_road_ft / len(edge_lengths) if edge_lengths else 0.0
    max_edge_ft = max(edge_lengths) if edge_lengths else 0.0

    parcel_acres = parcel_area_sqft / 43560.0 if parcel_area_sqft > 0 else 1.0
    road_density = total_road_ft / parcel_acres if parcel_acres > 0 else 0.0

    diameter = _graph_diameter(nodes, edges)

    metrics = GraphMetrics(
        node_count=len(nodes),
        edge_count=len(edges),
        intersection_count=intersection_count,
        dead_end_count=dead_end_count,
        avg_edge_length_ft=avg_edge_ft,
        max_edge_length_ft=max_edge_ft,
        total_road_length_ft=total_road_ft,
        road_density_ft_per_acre=road_density,
        graph_diameter=diameter,
    )

    return RoadGraph(nodes=nodes, edges=edges, metrics=metrics)


# ---------------------------------------------------------------------------
# Graph diameter via BFS (cheap for small subdivision graphs)
# ---------------------------------------------------------------------------

def _graph_diameter(nodes: List[RoadNode], edges: List[RoadEdge]) -> int:
    """
    Compute graph diameter in edge hops using BFS from every node.

    For typical subdivision graphs (< 30 nodes) this is negligible cost.
    Returns 0 for empty or single-node graphs.
    """
    if len(nodes) <= 1:
        return 0

    # Build adjacency
    adj: Dict[int, List[int]] = {n.id: [] for n in nodes}
    for edge in edges:
        if edge.from_node != edge.to_node:  # skip self-loops
            adj[edge.from_node].append(edge.to_node)
            adj[edge.to_node].append(edge.from_node)

    max_dist = 0
    for start in adj:
        dist = {start: 0}
        queue = [start]
        head = 0
        while head < len(queue):
            current = queue[head]
            head += 1
            for neighbour in adj[current]:
                if neighbour not in dist:
                    dist[neighbour] = dist[current] + 1
                    queue.append(neighbour)
        if dist:
            max_dist = max(max_dist, max(dist.values()))

    return max_dist
