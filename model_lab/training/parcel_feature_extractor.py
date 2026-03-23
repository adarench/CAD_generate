"""
Parcel Feature Extractor — model_lab

Computes a rich set of geometric features from a parcel polygon.

All features depend only on the parcel geometry — no road graph, no strategy,
no simulation output. Safe to use as pre-simulation inputs.

Supports both:
  - Synthetic parcels (coordinates in local feet)
  - Geographic parcels (WGS84 lng/lat — dimensionless ratios still valid)

No production code is modified.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# Feature name registry
# ---------------------------------------------------------------------------

PARCEL_FEATURE_NAMES: List[str] = [
    # Size
    "parcel_area_sqft",
    "parcel_area_acres",
    "parcel_perimeter_ft",          # raw perimeter (or deg for geographic)
    # Bounding box
    "bbox_width_ft",
    "bbox_height_ft",
    "bbox_aspect_ratio",            # max(w,h) / min(w,h) ≥ 1
    "bbox_area_ratio",              # polygon_area / bbox_area  (fill ratio)
    # Shape descriptors
    "compactness",                  # 4π·area / perimeter²  ∈ (0,1]
    "convex_hull_ratio",            # polygon_area / convex_hull_area  ∈ (0,1]
    "perimeter_ratio",              # perimeter / sqrt(area)  — dimensionless
    "elongation",                   # 1 - minor_axis / major_axis  ∈ [0,1)
    # Vertex / edge complexity
    "vertex_count",
    "edge_count",                   # same as vertex_count for simple polygon
    "major_edge_count",             # edges longer than 0.5 × median edge
    "longest_edge_ft",
    "shortest_edge_ft",
    "average_edge_ft",
    "edge_length_std_ft",           # std of edge lengths
    "edge_length_cv",               # coefficient of variation  (std / mean)
    # Orientation / directional balance
    "dominant_orientation_deg",     # angle of longest edge  [0, 180)
    "orientation_spread_deg",       # circular std of edge orientations
    "near_axis_edge_ratio",         # fraction of edges within 15° of N/S/E/W
    # Frontage candidates
    "frontage_candidate_count",     # edges that could plausibly face a street
    "longest_frontage_ratio",       # longest_edge / perimeter
]


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _exterior_coords(geojson: dict) -> List[Tuple[float, float]]:
    """Return exterior ring as list of (x, y) tuples (closing vertex included)."""
    gtype = geojson.get("type", "")
    if gtype == "Polygon":
        return [(x, y) for x, y in geojson["coordinates"][0]]
    if gtype == "MultiPolygon":
        # pick largest ring
        best = max(geojson["coordinates"], key=lambda rings: _shoelace_area(rings[0]))
        return [(x, y) for x, y in best[0]]
    return []


def _shoelace_area(ring: list) -> float:
    """Signed area via shoelace formula (ring is list of [x,y])."""
    n = len(ring)
    s = 0.0
    for i in range(n):
        x0, y0 = ring[i][0], ring[i][1]
        x1, y1 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
        s += x0 * y1 - x1 * y0
    return abs(s) / 2.0


def _convex_hull_area(coords: List[Tuple[float, float]]) -> float:
    """Convex hull area using Graham scan, fallback to bbox if degenerate."""
    try:
        from shapely.geometry import MultiPoint
        pts = MultiPoint(coords)
        return float(pts.convex_hull.area)
    except Exception:
        pass
    # Fallback: bounding box
    xs = [p[0] for p in coords]
    ys = [p[1] for p in coords]
    return (max(xs) - min(xs)) * (max(ys) - min(ys))


def _pca_axes(coords: List[Tuple[float, float]]) -> Tuple[float, float]:
    """
    Returns (major_axis_length, minor_axis_length) via PCA of vertex coords.
    Used to compute elongation.
    """
    pts = np.array(coords)
    pts = pts - pts.mean(axis=0)
    cov = np.cov(pts.T)
    if cov.ndim < 2:
        return 1.0, 1.0
    try:
        eigvals = np.linalg.eigvalsh(cov)
        eigvals = np.sort(np.abs(eigvals))[::-1]
        major = math.sqrt(max(eigvals[0], 1e-12))
        minor = math.sqrt(max(eigvals[1], 1e-12))
        return major, minor
    except Exception:
        return 1.0, 1.0


def _edge_stats(coords: List[Tuple[float, float]]) -> dict:
    """
    Compute per-edge lengths and orientations from exterior ring.
    Returns dict with raw edge data.
    """
    # Drop closing vertex if present
    ring = coords[:-1] if coords and coords[0] == coords[-1] else coords
    n = len(ring)
    if n < 2:
        return {"lengths": [], "angles": []}

    lengths, angles = [], []
    for i in range(n):
        x0, y0 = ring[i]
        x1, y1 = ring[(i + 1) % n]
        dx, dy = x1 - x0, y1 - y0
        length = math.sqrt(dx * dx + dy * dy)
        lengths.append(length)
        # Orientation in [0, 180) — undirected
        angle = math.degrees(math.atan2(dy, dx)) % 180.0
        angles.append(angle)

    return {"lengths": lengths, "angles": angles}


def _circular_std(angles_deg: List[float]) -> float:
    """Circular standard deviation of angles in degrees."""
    if not angles_deg:
        return 0.0
    rads = [math.radians(2 * a) for a in angles_deg]  # double to wrap [0,360)
    sx = sum(math.cos(r) for r in rads)
    sy = sum(math.sin(r) for r in rads)
    n = len(rads)
    R = math.sqrt(sx * sx + sy * sy) / n
    return math.degrees(math.sqrt(-2.0 * math.log(max(R, 1e-9)))) / 2.0


# ---------------------------------------------------------------------------
# Main extractor
# ---------------------------------------------------------------------------

def extract_parcel_features(
    parcel_polygon: dict,
    parcel_area_sqft: float = 0.0,
) -> Dict[str, float]:
    """
    Extract rich geometric features from a GeoJSON polygon.

    Args:
        parcel_polygon:  GeoJSON geometry dict (Polygon or MultiPolygon)
        parcel_area_sqft: pre-computed area in sqft (from database / record);
                          if 0, estimated from raw polygon coords.

    Returns:
        Flat dict of floats — all keys listed in PARCEL_FEATURE_NAMES.
    """
    coords = _exterior_coords(parcel_polygon)

    # --- Basic area / perimeter via shapely if available ---
    raw_area, raw_perim = 0.0, 0.0
    try:
        from shapely.geometry import shape
        geom = shape(parcel_polygon)
        if geom.geom_type == "MultiPolygon":
            geom = max(geom.geoms, key=lambda g: g.area)
        raw_area = float(geom.area)
        raw_perim = float(geom.length)
        bounds = geom.bounds
        bw = bounds[2] - bounds[0]
        bh = bounds[3] - bounds[1]
    except Exception:
        raw_area = _shoelace_area([list(c) for c in coords]) if coords else 0.0
        raw_perim = sum(
            math.sqrt((coords[i][0] - coords[(i+1) % len(coords)][0])**2 +
                      (coords[i][1] - coords[(i+1) % len(coords)][1])**2)
            for i in range(len(coords) - 1)
        )
        xs = [c[0] for c in coords]
        ys = [c[1] for c in coords]
        bw = max(xs) - min(xs) if xs else 0.0
        bh = max(ys) - min(ys) if ys else 0.0

    # Use parcel_area_sqft from record if provided; else raw
    area_sqft = parcel_area_sqft if parcel_area_sqft > 0 else raw_area
    area_acres = area_sqft / 43560.0

    # Dimensionless perimeter: scale raw perimeter to match area scale
    # For synthetic parcels raw_perim is in feet. For geographic it's in degrees
    # but ratios are still valid.
    perim = raw_perim
    perim_ratio = perim / math.sqrt(max(raw_area, 1e-9))

    # Bounding box
    bbox_aspect = max(bw, bh) / max(min(bw, bh), 1e-9)
    bbox_area = bw * bh
    bbox_fill = raw_area / max(bbox_area, 1e-9)

    # Compactness
    compactness = 4.0 * math.pi * raw_area / (raw_perim ** 2) if raw_perim > 0 else 0.0

    # Convex hull
    hull_area = _convex_hull_area(coords) if coords else raw_area
    convex_hull_ratio = raw_area / max(hull_area, 1e-9)

    # PCA elongation
    ring = coords[:-1] if coords and coords[0] == coords[-1] else coords
    major_ax, minor_ax = _pca_axes(ring) if len(ring) >= 3 else (1.0, 1.0)
    elongation = 1.0 - (minor_ax / max(major_ax, 1e-9))

    # Edge stats
    es = _edge_stats(coords)
    lengths = es["lengths"]
    angles  = es["angles"]

    n_edges = len(lengths)
    if lengths:
        arr = np.array(lengths)
        median_len = float(np.median(arr))
        avg_len    = float(np.mean(arr))
        std_len    = float(np.std(arr))
        cv_len     = std_len / max(avg_len, 1e-9)
        longest    = float(np.max(arr))
        shortest   = float(np.min(arr))
        major_edge_count = int((arr > 0.5 * median_len).sum())
    else:
        avg_len = std_len = cv_len = longest = shortest = median_len = 0.0
        major_edge_count = 0

    # Dominant orientation (orientation of longest edge)
    dom_orient = 0.0
    if lengths:
        dom_orient = angles[int(np.argmax(lengths))]

    # Orientation spread (circular std of all edge orientations)
    orient_spread = _circular_std(angles) if angles else 0.0

    # Edges near axis (within 15° of 0, 45, 90, 135)
    near_axis = 0
    for a in angles:
        for axis in [0.0, 45.0, 90.0, 135.0]:
            if min(abs(a - axis), 180.0 - abs(a - axis)) <= 15.0:
                near_axis += 1
                break
    near_axis_ratio = near_axis / max(n_edges, 1)

    # Frontage candidates: edges long enough to serve as street frontage
    # (≥ 40 ft in real units; we use ≥ 10% of longest edge as a proxy)
    frontage_thresh = longest * 0.10
    frontage_count = sum(1 for l in lengths if l >= frontage_thresh)

    longest_frontage_ratio = longest / max(perim, 1e-9)

    vertex_count = len(ring)

    return {
        # Size
        "parcel_area_sqft":         area_sqft,
        "parcel_area_acres":         area_acres,
        "parcel_perimeter_ft":       perim,
        # Bounding box
        "bbox_width_ft":             bw,
        "bbox_height_ft":            bh,
        "bbox_aspect_ratio":         bbox_aspect,
        "bbox_area_ratio":           bbox_fill,
        # Shape
        "compactness":               compactness,
        "convex_hull_ratio":         convex_hull_ratio,
        "perimeter_ratio":           perim_ratio,
        "elongation":                elongation,
        # Vertex / edge
        "vertex_count":              float(vertex_count),
        "edge_count":                float(n_edges),
        "major_edge_count":          float(major_edge_count),
        "longest_edge_ft":           longest,
        "shortest_edge_ft":          shortest,
        "average_edge_ft":           avg_len,
        "edge_length_std_ft":        std_len,
        "edge_length_cv":            cv_len,
        # Orientation
        "dominant_orientation_deg":  dom_orient,
        "orientation_spread_deg":    orient_spread,
        "near_axis_edge_ratio":      near_axis_ratio,
        # Frontage
        "frontage_candidate_count":  float(frontage_count),
        "longest_frontage_ratio":    longest_frontage_ratio,
    }
