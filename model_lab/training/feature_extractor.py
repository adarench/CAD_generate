"""
Feature Extractor — model_lab

Converts a JSONL dataset record into a flat numeric feature vector for ML training.

Design principle:
  Only pre-simulation features are used — these are features available BEFORE
  running the expensive generate_subdivision() call:
    1. Parcel geometry  (area, shape ratios, compactness)
    2. Strategy params  (topology, density, entry — one-hot encoded)
    3. Road graph       (cheap to extract from candidate centerlines)

  Post-simulation features (lot_count, avg_lot_area, developable_area) are
  deliberately excluded so the ranker generalises to unseen parcels at
  inference time.

No production code is modified.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import numpy as np


# ---------------------------------------------------------------------------
# Feature names — canonical ordering for numpy arrays
# ---------------------------------------------------------------------------

PARCEL_FEATURE_NAMES: List[str] = [
    "parcel_area_sqft",
    "parcel_area_acres",
    "parcel_aspect_ratio",      # bounding_box W / H (or H/W, always ≥ 1)
    "parcel_compactness",        # 4π·area / perimeter²  ∈ (0, 1]
    "parcel_perimeter_ratio",    # perimeter / sqrt(area)  (dimensionless)
    "parcel_vertex_count",
]

STRATEGY_FEATURE_NAMES: List[str] = [
    # road type (4 one-hot)
    "strat_road_loop",
    "strat_road_spine",
    "strat_road_parallel",
    "strat_road_culdesac",
    # entry point (4 one-hot)
    "strat_entry_north",
    "strat_entry_south",
    "strat_entry_east",
    "strat_entry_west",
    # density goal (3 one-hot)
    "strat_density_low",
    "strat_density_medium",
    "strat_density_high",
    # raw count
    "strat_culdesac_count",
]

GRAPH_FEATURE_NAMES: List[str] = [
    "graph_node_count",
    "graph_edge_count",
    "graph_intersection_count",
    "graph_dead_end_count",
    "graph_avg_edge_length_ft",
    "graph_max_edge_length_ft",
    "graph_total_road_length_ft",
    "graph_road_density_ft_per_acre",
    "graph_diameter",
    # derived ratios
    "graph_intersection_ratio",     # intersections / nodes
    "graph_dead_end_ratio",         # dead_ends / nodes
    "graph_road_per_area",          # total_road_ft / area_acres
]

ALL_FEATURE_NAMES: List[str] = (
    PARCEL_FEATURE_NAMES + STRATEGY_FEATURE_NAMES + GRAPH_FEATURE_NAMES
)


# ---------------------------------------------------------------------------
# Target names
# ---------------------------------------------------------------------------

TARGET_NAMES: List[str] = ["yield_score", "efficiency_score", "overall_score"]


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _polygon_stats(geojson: dict) -> Tuple[float, float, float, float, int]:
    """
    Compute (area, perimeter, aspect_ratio, compactness, vertex_count)
    from a GeoJSON polygon.

    Works in any coordinate system — returns dimensionless ratios where
    the coordinate units don't matter, and raw values in the native units.
    For synthetic parcels (feet) area and perimeter are in sqft / ft.
    For geographic parcels (lng/lat) area/perimeter are in degree² / degrees
    but ratios (aspect_ratio, compactness) are still correct.
    """
    try:
        from shapely.geometry import shape
        geom = shape(geojson)
        if geom.geom_type == "MultiPolygon":
            geom = max(geom.geoms, key=lambda g: g.area)
        area = float(geom.area)
        perimeter = float(geom.length)
        bounds = geom.bounds
        bw = bounds[2] - bounds[0]
        bh = bounds[3] - bounds[1]
        aspect = max(bw, bh) / max(min(bw, bh), 1e-9)
        compactness = 4.0 * math.pi * area / (perimeter ** 2) if perimeter > 0 else 0.0
        vcount = len(list(geom.exterior.coords)) - 1  # drop closing vertex
        return area, perimeter, aspect, compactness, vcount
    except Exception:
        return 0.0, 0.0, 1.0, 0.0, 0


# ---------------------------------------------------------------------------
# Per-group extractors
# ---------------------------------------------------------------------------

def _parcel_features(record: dict) -> Dict[str, float]:
    area_sqft = float(record.get("parcel_area_sqft") or 0.0)
    geojson = record.get("parcel_polygon", {})
    raw_area, raw_perim, aspect, compactness, vcount = _polygon_stats(geojson)

    # If the polygon is in local feet, raw_area ≈ area_sqft — use it.
    # If geographic (lng/lat), raw_area is tiny but ratios are fine.
    # For perimeter_ratio, normalise against raw polygon scale.
    perim_ratio = raw_perim / math.sqrt(max(raw_area, 1e-9))

    return {
        "parcel_area_sqft":     area_sqft,
        "parcel_area_acres":    area_sqft / 43560.0,
        "parcel_aspect_ratio":  aspect,
        "parcel_compactness":   compactness,
        "parcel_perimeter_ratio": perim_ratio,
        "parcel_vertex_count":  float(vcount),
    }


def _strategy_features(strategy: dict) -> Dict[str, float]:
    road_type   = strategy.get("road_type", "")
    entry       = strategy.get("entry_point", "")
    density     = strategy.get("density_goal", "")
    cul_count   = float(strategy.get("culdesac_count", 0))

    return {
        "strat_road_loop":       float(road_type == "loop"),
        "strat_road_spine":      float(road_type == "spine"),
        "strat_road_parallel":   float(road_type == "parallel"),
        "strat_road_culdesac":   float(road_type == "culdesac"),
        "strat_entry_north":     float(entry == "north"),
        "strat_entry_south":     float(entry == "south"),
        "strat_entry_east":      float(entry == "east"),
        "strat_entry_west":      float(entry == "west"),
        "strat_density_low":     float(density == "low"),
        "strat_density_medium":  float(density == "medium"),
        "strat_density_high":    float(density == "high"),
        "strat_culdesac_count":  cul_count,
    }


def _graph_features(road_graph: dict, parcel_area_sqft: float) -> Dict[str, float]:
    m = road_graph.get("metrics", {})
    nodes     = float(m.get("node_count", 0))
    edges     = float(m.get("edge_count", 0))
    ixns      = float(m.get("intersection_count", 0))
    dead_ends = float(m.get("dead_end_count", 0))
    avg_el    = float(m.get("avg_edge_length_ft", 0))
    max_el    = float(m.get("max_edge_length_ft", 0))
    total_rd  = float(m.get("total_road_length_ft", 0))
    density   = float(m.get("road_density_ft_per_acre", 0))
    diameter  = float(m.get("graph_diameter", 0))

    acres = parcel_area_sqft / 43560.0 if parcel_area_sqft > 0 else 1.0
    return {
        "graph_node_count":               nodes,
        "graph_edge_count":               edges,
        "graph_intersection_count":       ixns,
        "graph_dead_end_count":           dead_ends,
        "graph_avg_edge_length_ft":       avg_el,
        "graph_max_edge_length_ft":       max_el,
        "graph_total_road_length_ft":     total_rd,
        "graph_road_density_ft_per_acre": density,
        "graph_diameter":                 diameter,
        "graph_intersection_ratio":       ixns / max(nodes, 1),
        "graph_dead_end_ratio":           dead_ends / max(nodes, 1),
        "graph_road_per_area":            total_rd / max(acres, 1e-9),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_features(record: dict) -> Dict[str, float]:
    """
    Extract a flat feature dictionary from a single JSONL dataset record.

    All values are floats. Categorical features are one-hot encoded.
    Only pre-simulation features are included (parcel, strategy, road graph).
    """
    area_sqft = float(record.get("parcel_area_sqft") or 0.0)
    features: Dict[str, float] = {}
    features.update(_parcel_features(record))
    features.update(_strategy_features(record.get("strategy", {})))
    features.update(_graph_features(record.get("road_graph", {}), area_sqft))
    return features


def extract_target(record: dict, target: str = "overall_score") -> float:
    """Extract a single target value from the score dict."""
    return float(record.get("score", {}).get(target, 0.0))


def records_to_arrays(
    records: List[dict],
    target: str = "overall_score",
    feature_names: Optional[List[str]] = None,
) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    """
    Convert a list of JSONL records to (X, y, feature_names) arrays.

    Args:
        records:       list of decoded JSONL dicts
        target:        score field to use as target ("overall_score", "yield_score", etc.)
        feature_names: explicit feature ordering; defaults to ALL_FEATURE_NAMES

    Returns:
        X:  (n_samples, n_features) float32 array
        y:  (n_samples,) float64 target array
        names: list of feature names matching X columns
    """
    names = feature_names or ALL_FEATURE_NAMES
    X_rows, y_vals = [], []

    for rec in records:
        feat_dict = extract_features(rec)
        row = [feat_dict.get(name, 0.0) for name in names]
        X_rows.append(row)
        y_vals.append(extract_target(rec, target))

    X = np.array(X_rows, dtype=np.float32)
    y = np.array(y_vals, dtype=np.float64)
    return X, y, names
