"""
Production Graph Prior Inference

Loads the trained graph prior model (graph_prior.pkl) and scores
RoadNetwork candidates before simulation, enabling guided search.

No model_lab imports — self-contained feature extraction.
"""

from __future__ import annotations

import math
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from shapely.geometry import Polygon

from .graph_generator import RoadNetwork

MODEL_PATH = Path(__file__).resolve().parents[4] / "apps" / "python-api" / "models" / "graph_prior.pkl"

# ---------------------------------------------------------------------------
# Feature name lists (must match model_lab training order exactly)
# ---------------------------------------------------------------------------

PARCEL_FEATURE_NAMES = [
    "area_sqft", "area_acres", "perimeter_ft",
    "compactness", "aspect_ratio", "convexity",
    "elongation", "squareness",
    "width_ft", "height_ft",
    "n_vertices", "is_convex",
    "min_angle_deg", "max_angle_deg", "angle_std_deg",
    "largest_inscribed_circle_r",
    "flatness_north", "flatness_south", "flatness_east", "flatness_west",
    "slope_variance", "perimeter_irregularity",
    "bbox_fill_ratio", "diagonal_ratio",
]

GRAPH_FEATURE_NAMES = [
    "node_count", "edge_count", "intersection_count", "dead_end_count", "entry_count",
    "total_road_length_ft", "avg_edge_length_ft", "min_edge_length_ft",
    "max_edge_length_ft", "edge_length_std_ft", "road_density_ft_per_acre",
    "avg_node_degree", "max_node_degree", "branching_factor", "dead_end_ratio",
    "intersection_ratio", "loop_count", "connectivity_ratio",
    "graph_diameter_ft", "bbox_width_ft", "bbox_height_ft", "bbox_aspect_ratio",
    "centroid_offset_x", "centroid_offset_y",
    "gridness", "radial_symmetry", "parallelism",
    "type_spine", "type_loop_custom", "type_grid",
    "type_herringbone", "type_radial", "type_t_junction",
]


# ---------------------------------------------------------------------------
# Parcel feature extraction
# ---------------------------------------------------------------------------

def extract_parcel_features(parcel_polygon: Polygon, area_sqft: float) -> Dict[str, float]:
    area_acres = area_sqft / 43560.0
    perimeter = parcel_polygon.length
    minx, miny, maxx, maxy = parcel_polygon.bounds
    width = maxx - minx
    height = maxy - miny

    # Compactness (isoperimetric quotient)
    compactness = 4 * math.pi * area_sqft / max(perimeter ** 2, 1e-9)

    # Aspect ratio
    aspect = width / max(height, 1.0) if height > 0 else 1.0
    aspect_ratio = max(aspect, 1.0 / max(aspect, 1e-9))

    # Convexity
    hull_area = parcel_polygon.convex_hull.area
    convexity = area_sqft / max(hull_area, 1.0)

    # Elongation: 1 - min_dim/max_dim
    elongation = 1.0 - min(width, height) / max(max(width, height), 1.0)

    # Squareness: how close to a square
    squareness = min(width, height) / max(max(width, height), 1.0)

    # Vertices
    coords = list(parcel_polygon.exterior.coords)
    n_vertices = len(coords) - 1  # last coord repeats first
    is_convex = float(parcel_polygon.equals(parcel_polygon.convex_hull))

    # Angles
    angles = []
    n = n_vertices
    for i in range(n):
        p0 = coords[(i - 1) % n]
        p1 = coords[i]
        p2 = coords[(i + 1) % n]
        v1 = (p0[0] - p1[0], p0[1] - p1[1])
        v2 = (p2[0] - p1[0], p2[1] - p1[1])
        mag1 = math.hypot(*v1)
        mag2 = math.hypot(*v2)
        if mag1 < 1e-9 or mag2 < 1e-9:
            continue
        cos_a = (v1[0]*v2[0] + v1[1]*v2[1]) / (mag1 * mag2)
        cos_a = max(-1.0, min(1.0, cos_a))
        angles.append(math.degrees(math.acos(cos_a)))

    min_angle = min(angles) if angles else 90.0
    max_angle = max(angles) if angles else 90.0
    angle_std = float(np.std(angles)) if len(angles) > 1 else 0.0

    # Inscribed circle radius approximation (2*area/perimeter)
    inscribed_r = 2.0 * area_sqft / max(perimeter, 1.0)

    # Flatness per side (fraction of perimeter on each cardinal side)
    def _side_fraction(side: str) -> float:
        total = 0.0
        for i in range(n):
            p1 = coords[i]
            p2 = coords[(i + 1) % n]
            seg_len = math.hypot(p2[0]-p1[0], p2[1]-p1[1])
            dx = p2[0] - p1[0]
            dy = p2[1] - p1[1]
            if seg_len < 1e-9:
                continue
            if side == "north" and dy > 0 and abs(dy) > abs(dx):
                total += seg_len
            elif side == "south" and dy < 0 and abs(dy) > abs(dx):
                total += seg_len
            elif side == "east" and dx > 0 and abs(dx) > abs(dy):
                total += seg_len
            elif side == "west" and dx < 0 and abs(dx) > abs(dy):
                total += seg_len
        return total / max(perimeter, 1.0)

    # Slope variance (approximated as 0 for flat parcels in local feet)
    slope_variance = 0.0

    # Perimeter irregularity: ratio of actual perimeter to convex hull perimeter
    perimeter_irregularity = perimeter / max(parcel_polygon.convex_hull.length, 1.0)

    # Bbox fill ratio
    bbox_area = width * height
    bbox_fill = area_sqft / max(bbox_area, 1.0)

    # Diagonal ratio
    diagonal = math.hypot(width, height)
    diagonal_ratio = diagonal / max(math.sqrt(area_sqft), 1.0)

    return {
        "area_sqft":                area_sqft,
        "area_acres":               area_acres,
        "perimeter_ft":             perimeter,
        "compactness":              compactness,
        "aspect_ratio":             aspect_ratio,
        "convexity":                convexity,
        "elongation":               elongation,
        "squareness":               squareness,
        "width_ft":                 width,
        "height_ft":                height,
        "n_vertices":               float(n_vertices),
        "is_convex":                is_convex,
        "min_angle_deg":            min_angle,
        "max_angle_deg":            max_angle,
        "angle_std_deg":            angle_std,
        "largest_inscribed_circle_r": inscribed_r,
        "flatness_north":           _side_fraction("north"),
        "flatness_south":           _side_fraction("south"),
        "flatness_east":            _side_fraction("east"),
        "flatness_west":            _side_fraction("west"),
        "slope_variance":           slope_variance,
        "perimeter_irregularity":   perimeter_irregularity,
        "bbox_fill_ratio":          bbox_fill,
        "diagonal_ratio":           diagonal_ratio,
    }


# ---------------------------------------------------------------------------
# Graph feature extraction
# ---------------------------------------------------------------------------

def extract_graph_features(network: RoadNetwork, parcel_area_sqft: float) -> Dict[str, float]:
    lines = network.centerlines
    if not lines:
        return {k: 0.0 for k in GRAPH_FEATURE_NAMES}

    # Collect all segment endpoints as nodes (rounded to 0.5ft grid)
    def _snap(v: float, snap: float = 0.5) -> float:
        return round(v / snap) * snap

    nodes: Dict[Tuple[float, float], int] = {}
    edges: List[Tuple[int, int, float]] = []

    def _node(x: float, y: float) -> int:
        key = (_snap(x), _snap(y))
        if key not in nodes:
            nodes[key] = len(nodes)
        return nodes[key]

    for line in lines:
        coords = list(line.coords)
        for i in range(len(coords) - 1):
            u = _node(*coords[i])
            v = _node(*coords[i + 1])
            length = math.hypot(coords[i+1][0]-coords[i][0], coords[i+1][1]-coords[i][1])
            if length > 0.5:
                edges.append((u, v, length))

    if not edges:
        return {k: 0.0 for k in GRAPH_FEATURE_NAMES}

    n_nodes = len(nodes)
    n_edges = len(edges)

    # Node degree
    degree: Dict[int, int] = {}
    for u, v, _ in edges:
        degree[u] = degree.get(u, 0) + 1
        degree[v] = degree.get(v, 0) + 1

    degrees = list(degree.values())
    avg_degree = sum(degrees) / max(n_nodes, 1)
    max_degree = max(degrees) if degrees else 0

    # Topology counts
    dead_ends = sum(1 for d in degrees if d == 1)
    intersections = sum(1 for d in degrees if d >= 3)
    entries = sum(1 for d in degrees if d == 1)  # approximation

    # Edge lengths
    lengths = [l for _, _, l in edges]
    total_len = sum(lengths)
    avg_len = total_len / max(n_edges, 1)
    min_len = min(lengths)
    max_len = max(lengths)
    len_std = float(np.std(lengths)) if len(lengths) > 1 else 0.0

    # Road density
    area_acres = parcel_area_sqft / 43560.0
    road_density = total_len / max(area_acres, 0.01)

    # Branching factor
    branching = intersections / max(n_nodes, 1)
    dead_end_ratio = dead_ends / max(n_nodes, 1)
    intersection_ratio = intersections / max(n_nodes, 1)

    # Loop count (edges - nodes + 1 for connected graph approximation)
    loop_count = max(0, n_edges - n_nodes + 1)

    # Connectivity ratio (actual edges / max possible)
    max_edges = n_nodes * (n_nodes - 1) / 2
    connectivity = n_edges / max(max_edges, 1.0)

    # Bounding box of all endpoints
    all_pts = list(nodes.keys())
    xs = [p[0] for p in all_pts]
    ys = [p[1] for p in all_pts]
    bbox_w = max(xs) - min(xs) if xs else 0.0
    bbox_h = max(ys) - min(ys) if ys else 0.0
    bbox_aspect = bbox_w / max(bbox_h, 1.0)

    cx = sum(xs) / max(len(xs), 1)
    cy = sum(ys) / max(len(ys), 1)

    # Graph diameter (approximate as max edge length × connectivity proxy)
    diameter = max_len * math.log1p(n_nodes)

    # Structural metrics
    def _gridness() -> float:
        """Fraction of edges that are nearly axis-aligned."""
        if not lines:
            return 0.0
        aligned = 0
        for line in lines:
            coords = list(line.coords)
            for i in range(len(coords) - 1):
                dx = abs(coords[i+1][0] - coords[i][0])
                dy = abs(coords[i+1][1] - coords[i][1])
                seg_len = math.hypot(dx, dy)
                if seg_len < 1e-9:
                    continue
                # Aligned if within 15° of horizontal or vertical
                angle = math.degrees(math.atan2(dy, dx)) % 90
                if angle < 15 or angle > 75:
                    aligned += 1
        total_segs = sum(max(0, len(list(l.coords)) - 1) for l in lines)
        return aligned / max(total_segs, 1)

    def _radial_symmetry() -> float:
        """Score based on how evenly spokes radiate from centroid."""
        if n_nodes < 3:
            return 0.0
        spoke_angles = []
        for pt in all_pts:
            dx = pt[0] - cx
            dy = pt[1] - cy
            dist = math.hypot(dx, dy)
            if dist > 10.0:
                spoke_angles.append(math.atan2(dy, dx))
        if len(spoke_angles) < 3:
            return 0.0
        spoke_angles.sort()
        gaps = [spoke_angles[i+1] - spoke_angles[i] for i in range(len(spoke_angles)-1)]
        gaps.append((spoke_angles[0] + 2*math.pi) - spoke_angles[-1])
        ideal_gap = 2 * math.pi / len(spoke_angles)
        variance = float(np.std(gaps))
        return math.exp(-variance / max(ideal_gap, 0.1))

    def _parallelism() -> float:
        """Fraction of edge pairs that are nearly parallel."""
        if len(lines) < 2:
            return 0.0
        line_angles = []
        for line in lines:
            coords = list(line.coords)
            if len(coords) < 2:
                continue
            dx = coords[-1][0] - coords[0][0]
            dy = coords[-1][1] - coords[0][1]
            if math.hypot(dx, dy) < 1e-9:
                continue
            line_angles.append(math.atan2(dy, dx) % math.pi)
        if len(line_angles) < 2:
            return 0.0
        parallel = 0
        total = 0
        for i in range(len(line_angles)):
            for j in range(i+1, min(i+10, len(line_angles))):
                diff = abs(line_angles[i] - line_angles[j]) % math.pi
                diff = min(diff, math.pi - diff)
                if diff < math.radians(15):
                    parallel += 1
                total += 1
        return parallel / max(total, 1)

    # One-hot type encoding
    gt = network.generator_type
    type_feats = {
        "type_spine":       float(gt == "spine"),
        "type_loop_custom": float(gt == "loop_custom"),
        "type_grid":        float(gt == "grid"),
        "type_herringbone": float(gt == "herringbone"),
        "type_radial":      float(gt == "radial"),
        "type_t_junction":  float(gt == "t_junction"),
    }

    return {
        "node_count":             float(n_nodes),
        "edge_count":             float(n_edges),
        "intersection_count":     float(intersections),
        "dead_end_count":         float(dead_ends),
        "entry_count":            float(entries),
        "total_road_length_ft":   total_len,
        "avg_edge_length_ft":     avg_len,
        "min_edge_length_ft":     min_len,
        "max_edge_length_ft":     max_len,
        "edge_length_std_ft":     len_std,
        "road_density_ft_per_acre": road_density,
        "avg_node_degree":        avg_degree,
        "max_node_degree":        float(max_degree),
        "branching_factor":       branching,
        "dead_end_ratio":         dead_end_ratio,
        "intersection_ratio":     intersection_ratio,
        "loop_count":             float(loop_count),
        "connectivity_ratio":     connectivity,
        "graph_diameter_ft":      diameter,
        "bbox_width_ft":          bbox_w,
        "bbox_height_ft":         bbox_h,
        "bbox_aspect_ratio":      bbox_aspect,
        "centroid_offset_x":      cx,
        "centroid_offset_y":      cy,
        "gridness":               _gridness(),
        "radial_symmetry":        _radial_symmetry(),
        "parallelism":            _parallelism(),
        **type_feats,
    }


# ---------------------------------------------------------------------------
# Prior model wrapper
# ---------------------------------------------------------------------------

@dataclass
class ScoredNetwork:
    network:         RoadNetwork
    predicted_score: float
    rank:            int


class GraphPriorInference:
    """Loads and applies the trained graph prior model."""

    def __init__(self, model, feature_names: List[str]):
        self._model = model
        self._feature_names = feature_names

    @classmethod
    def load(cls, path: Path = MODEL_PATH) -> "GraphPriorInference":
        with open(path, "rb") as f:
            payload = pickle.load(f)
        return cls(payload["model"], payload["feature_names"])

    def _build_row(self, parcel_feats: dict, graph_feats: dict) -> List[float]:
        all_names = PARCEL_FEATURE_NAMES + GRAPH_FEATURE_NAMES
        return [float(parcel_feats.get(k, 0.0)) if k in PARCEL_FEATURE_NAMES
                else float(graph_feats.get(k, 0.0))
                for k in all_names]

    def rank_networks(
        self,
        networks: List[RoadNetwork],
        parcel_polygon: Polygon,
        area_sqft: float,
    ) -> List[ScoredNetwork]:
        """Score and rank candidates by prior-predicted score (descending)."""
        if not networks:
            return []

        pf = extract_parcel_features(parcel_polygon, area_sqft)
        rows = [self._build_row(pf, extract_graph_features(n, area_sqft)) for n in networks]
        X = np.array(rows, dtype=np.float32)
        preds = self._model.predict(X)

        paired = sorted(zip(preds, networks), key=lambda x: x[0], reverse=True)
        return [
            ScoredNetwork(network=net, predicted_score=float(s), rank=i+1)
            for i, (s, net) in enumerate(paired)
        ]


# Module-level lazy singleton
_prior: Optional[GraphPriorInference] = None


def get_prior() -> Optional[GraphPriorInference]:
    """Return cached prior, loading on first call. Returns None if model not found."""
    global _prior
    if _prior is None:
        if MODEL_PATH.exists():
            try:
                _prior = GraphPriorInference.load()
            except Exception:
                pass
    return _prior
