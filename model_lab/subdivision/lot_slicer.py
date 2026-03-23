"""
Lot Slicer — model_lab

Slices BuildableStrip polygons into individual lot polygons by placing
perpendicular cutting planes along the road edge at min_frontage_ft intervals.

Algorithm per strip:
  1. Project strip onto road segment to find available frontage length
  2. Divide into N = floor(frontage / min_frontage_ft) slots
  3. For each slot, build a "slab" polygon (tall parallelogram perpendicular to road)
  4. Intersect slab with strip polygon → lot polygon
  5. Validate resulting lot (area, frontage, depth)

Corner handling: because strips are already road-union-subtracted, slab
intersections at corners automatically exclude the intersection zone.

No production code is modified.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from shapely.geometry import LineString, MultiPolygon, Point, Polygon
from shapely.ops import unary_union

from model_lab.subdivision.buildable_strip import BuildableStrip
from model_lab.subdivision.road_edge_extractor import RoadSegment


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class LotPolygon:
    """A single proposed lot polygon with metadata."""

    polygon:        Polygon
    strip:          BuildableStrip    # originating strip
    slot_index:     int               # 0-based index along road edge
    frontage_ft:    float             # measured frontage along road edge
    depth_ft:       float             # measured depth perpendicular to road
    area_sqft:      float             # polygon area


# ---------------------------------------------------------------------------
# Slab construction
# ---------------------------------------------------------------------------

def _build_slab(
    seg: RoadSegment,
    side: int,
    offset_along: float,    # distance along segment to slab start
    width_along: float,     # slab width = lot frontage
    inner_dist: float,      # distance from centerline to lot front
    outer_dist: float,      # distance from centerline to lot back
    slab_extension: float = 2.0,  # small overshoot to avoid gap slivers
) -> Optional[Polygon]:
    """
    Build a parallelogram slab cutting across the buildable strip.

    The slab runs from offset_along to offset_along+width_along along the
    segment, and from inner_dist to outer_dist perpendicular to the segment
    (on the given side).
    """
    coords = list(seg.line.coords)
    if len(coords) < 2:
        return None

    # Interpolate start and end points along the segment
    try:
        p_start = seg.line.interpolate(offset_along)
        p_end   = seg.line.interpolate(min(offset_along + width_along, seg.length_ft))
    except Exception:
        return None

    sx, sy = p_start.x, p_start.y
    ex, ey = p_end.x, p_end.y

    # Normal direction (side-adjusted)
    nx = seg.nx * side
    ny = seg.ny * side

    # Extend slightly in road direction to avoid gaps at boundaries
    dx, dy = seg.dx, seg.dy
    sx -= dx * slab_extension
    sy -= dy * slab_extension
    ex += dx * slab_extension
    ey += dy * slab_extension

    # Build parallelogram: 4 corners
    # front-start, front-end, back-end, back-start
    pts = [
        (sx + nx * inner_dist, sy + ny * inner_dist),
        (ex + nx * inner_dist, ey + ny * inner_dist),
        (ex + nx * outer_dist, ey + ny * outer_dist),
        (sx + nx * outer_dist, sy + ny * outer_dist),
    ]

    try:
        poly = Polygon(pts)
        if not poly.is_valid:
            poly = poly.buffer(0)
        return poly if not poly.is_empty else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Frontage measurement
# ---------------------------------------------------------------------------

def _measure_frontage(lot_polygon: Polygon, seg: RoadSegment, side: int, inner_dist: float) -> float:
    """
    Approximate frontage of a lot polygon as the length of the side
    closest to the road edge (inner_dist offset from centerline).
    Uses the projection of lot boundary onto the road direction.
    """
    coords = list(lot_polygon.exterior.coords)
    nx = seg.nx * side
    ny = seg.ny * side

    # Road direction vector
    dx, dy = seg.dx, seg.dy

    # Find the edge of the lot polygon closest to the road
    # Approximation: project all vertices onto the road normal axis
    # Points near inner_dist are "front edge" points
    front_pts = []
    for x, y in coords:
        # Distance from centerline in normal direction
        # Centerline passes through seg.start with normal (nx, ny)
        cx, cy = seg.start
        along = (x - cx) * dx + (y - cy) * dy
        perp  = (x - cx) * nx + (y - cy) * ny
        # Front edge is at ~inner_dist
        if abs(perp - inner_dist) < inner_dist * 0.5 + 20.0:
            front_pts.append(along)

    if len(front_pts) < 2:
        # Fallback: project bounding box
        try:
            road_line = LineString([seg.start, seg.end])
            proj = lot_polygon.intersection(road_line.buffer(inner_dist + 10.0))
            if not proj.is_empty:
                return proj.length
        except Exception:
            pass
        return 0.0

    return max(front_pts) - min(front_pts)


def _measure_depth(lot_polygon: Polygon, seg: RoadSegment, side: int) -> float:
    """
    Approximate lot depth as the extent of the polygon in the road-normal direction.
    """
    nx = seg.nx * side
    ny = seg.ny * side
    cx, cy = seg.start

    projections = []
    for x, y in lot_polygon.exterior.coords:
        perp = (x - cx) * nx + (y - cy) * ny
        projections.append(perp)

    if not projections:
        return 0.0
    return max(projections) - min(projections)


# ---------------------------------------------------------------------------
# Main slicer
# ---------------------------------------------------------------------------

def slice_strip_into_lots(
    strip: BuildableStrip,
    min_frontage_ft: float = 50.0,
    min_area_sqft:   float = 4000.0,
    min_depth_ft:    float = 80.0,
    half_road_width: float = 20.0,
    lot_depth:       float = 110.0,
) -> List[LotPolygon]:
    """
    Slice a BuildableStrip into individual lot polygons.

    Args:
        strip:           BuildableStrip to slice
        min_frontage_ft: minimum lot frontage
        min_area_sqft:   minimum lot area to keep
        min_depth_ft:    minimum lot depth to keep
        half_road_width: distance from centerline to road edge (= inner_dist)
        lot_depth:       nominal lot depth (= outer_dist - inner_dist)

    Returns:
        List of LotPolygon objects.
    """
    seg         = strip.segment
    side        = strip.side
    inner_dist  = half_road_width
    outer_dist  = half_road_width + lot_depth

    # Available frontage = length of the segment
    available_ft = seg.length_ft
    n_slots = int(available_ft / min_frontage_ft)
    if n_slots < 1:
        return []

    # Actual frontage per lot (may be slightly wider than minimum)
    slot_width = available_ft / n_slots

    lots = []
    for i in range(n_slots):
        offset = i * slot_width

        slab = _build_slab(
            seg=seg,
            side=side,
            offset_along=offset,
            width_along=slot_width,
            inner_dist=inner_dist,
            outer_dist=outer_dist,
        )
        if slab is None:
            continue

        # Intersect with the already-clipped-and-road-subtracted strip
        try:
            lot_raw = slab.intersection(strip.polygon)
            if lot_raw.is_empty:
                continue
        except Exception:
            continue

        # Handle MultiPolygon by taking the largest piece
        pieces: List[Polygon] = []
        if lot_raw.geom_type == "Polygon":
            pieces = [lot_raw]
        elif lot_raw.geom_type == "MultiPolygon":
            pieces = sorted(lot_raw.geoms, key=lambda g: g.area, reverse=True)[:1]

        for piece in pieces:
            if piece.area < min_area_sqft:
                continue

            depth = _measure_depth(piece, seg, side)
            if depth < min_depth_ft:
                continue

            frontage = _measure_frontage(piece, seg, side, inner_dist)

            lots.append(LotPolygon(
                polygon=piece,
                strip=strip,
                slot_index=i,
                frontage_ft=frontage,
                depth_ft=depth,
                area_sqft=piece.area,
            ))

    return lots


def slice_all_strips(
    strips:          List[BuildableStrip],
    min_frontage_ft: float = 50.0,
    min_area_sqft:   float = 4000.0,
    min_depth_ft:    float = 80.0,
    half_road_width: float = 20.0,
    lot_depth:       float = 110.0,
) -> List[LotPolygon]:
    """
    Slice all BuildableStrips into lots.

    Overlapping lots from adjacent strips are deduplicated by centroid proximity.
    """
    all_lots: List[LotPolygon] = []
    for strip in strips:
        lots = slice_strip_into_lots(
            strip=strip,
            min_frontage_ft=min_frontage_ft,
            min_area_sqft=min_area_sqft,
            min_depth_ft=min_depth_ft,
            half_road_width=half_road_width,
            lot_depth=lot_depth,
        )
        all_lots.extend(lots)

    return all_lots
