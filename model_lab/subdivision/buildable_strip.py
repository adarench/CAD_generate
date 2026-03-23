"""
Buildable Strip Generator — model_lab

For each road segment, computes the buildable strip polygons on each side.

A buildable strip is the zone between:
  front boundary: road centerline + half_road_width  (front setback = 0)
  back boundary:  road centerline + half_road_width + lot_depth

Strips are:
  1. Constructed from offset geometry of each road segment
  2. Clipped to the parcel boundary
  3. Differenced with the road union (removes road right-of-way area)

Corner handling: stripping road union from all buildable areas handles
intersection overlaps automatically — lots cannot extend into the roadway.

No production code is modified.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

from shapely.geometry import (
    LinearRing,
    LineString,
    MultiPolygon,
    Point,
    Polygon,
    box,
)
from shapely.ops import unary_union

from model_lab.subdivision.road_edge_extractor import RoadSegment


@dataclass
class BuildableStrip:
    """A clipped buildable zone alongside a single road segment."""

    polygon:     Polygon          # buildable area (clipped, road removed)
    segment:     RoadSegment      # originating road segment
    side:        int              # +1 = left, -1 = right of travel direction
    road_edge_length_ft: float    # usable frontage length ≈ segment length
    depth_ft:    float            # lot depth used to generate strip


def _offset_polygon(
    seg: RoadSegment,
    inner_dist: float,    # offset from centerline to strip front (= half road width)
    outer_dist: float,    # offset from centerline to strip back (= half road + lot depth)
    cap_extension: float = 0.0,
) -> Optional[Polygon]:
    """
    Build a strip polygon by buffering the road segment on one side.

    Works by building a parallelogram between the inner and outer offset lines.
    The cap_extension extends each end slightly to cover intersection zones.
    """
    coords = list(seg.line.coords)
    if len(coords) < 2:
        return None

    nx, ny = seg.nx, seg.ny   # left normal (pre-computed)

    # Extend the segment endpoints by cap_extension in the travel direction
    # to cover corners correctly
    dx, dy = seg.dx, seg.dy
    start = coords[0]
    end   = coords[-1]

    if cap_extension > 0:
        extended_start = (start[0] - dx * cap_extension, start[1] - dy * cap_extension)
        extended_end   = (end[0]   + dx * cap_extension, end[1]   + dy * cap_extension)
    else:
        extended_start, extended_end = start, end

    # Build polygon from offset points of each vertex
    inner_left  = [(x + nx * inner_dist, y + ny * inner_dist) for x, y in coords]
    outer_left  = [(x + nx * outer_dist, y + ny * outer_dist) for x, y in coords]

    # Prepend/append extended start/end
    if cap_extension > 0:
        inner_left = [(extended_start[0] + nx * inner_dist, extended_start[1] + ny * inner_dist)] + \
                     inner_left + \
                     [(extended_end[0] + nx * inner_dist, extended_end[1] + ny * inner_dist)]
        outer_left = [(extended_start[0] + nx * outer_dist, extended_start[1] + ny * outer_dist)] + \
                     outer_left + \
                     [(extended_end[0] + nx * outer_dist, extended_end[1] + ny * outer_dist)]

    ring = inner_left + list(reversed(outer_left))
    if len(ring) < 3:
        return None

    try:
        poly = Polygon(ring)
        if not poly.is_valid:
            poly = poly.buffer(0)
        return poly if not poly.is_empty else None
    except Exception:
        return None


def compute_buildable_strips(
    segments:          List[RoadSegment],
    parcel_polygon:    Polygon,
    road_union:        Polygon,
    half_road_width:   float = 20.0,   # half of road width
    lot_depth:         float = 110.0,
    min_strip_area:    float = 500.0,  # sqft — ignore slivers
) -> List[BuildableStrip]:
    """
    Compute buildable strips for all road segments.

    Steps per segment, per side:
      1. Build strip polygon (inner=half_road, outer=half_road+lot_depth)
      2. Clip to parcel boundary
      3. Subtract road union (handles corners, eliminates road area)
      4. Keep only valid strips above min_strip_area

    Args:
        segments:        road segments from road_edge_extractor
        parcel_polygon:  parcel boundary as Polygon
        road_union:      union of all road corridor polygons
        half_road_width: half the road width
        lot_depth:       how deep lots extend from road edge
        min_strip_area:  minimum strip area to keep (filters slivers)

    Returns:
        list of BuildableStrip objects
    """
    strips = []
    inner_dist = half_road_width
    outer_dist = half_road_width + lot_depth

    for seg in segments:
        # Generate both sides (left = +1, right = -1)
        for side in [1, -1]:
            # Adjust normal for right side
            nx, ny = seg.nx * side, seg.ny * side

            # Build raw strip
            coords = list(seg.line.coords)
            inner_pts = [(x + nx * inner_dist, y + ny * inner_dist) for x, y in coords]
            outer_pts = [(x + nx * outer_dist, y + ny * outer_dist) for x, y in coords]

            ring_pts = inner_pts + list(reversed(outer_pts))
            if len(ring_pts) < 3:
                continue

            try:
                raw_strip = Polygon(ring_pts)
                if not raw_strip.is_valid:
                    raw_strip = raw_strip.buffer(0)
                if raw_strip.is_empty or raw_strip.area < min_strip_area:
                    continue
            except Exception:
                continue

            # Clip to parcel
            try:
                clipped = raw_strip.intersection(parcel_polygon)
                if clipped.is_empty:
                    continue
            except Exception:
                continue

            # Subtract road union (handles corners and road area)
            try:
                clipped = clipped.difference(road_union)
                if clipped.is_empty:
                    continue
            except Exception:
                continue

            # Handle MultiPolygon by keeping significant pieces
            pieces = []
            if clipped.geom_type == "Polygon":
                pieces = [clipped] if clipped.area >= min_strip_area else []
            elif clipped.geom_type == "MultiPolygon":
                pieces = [g for g in clipped.geoms if g.area >= min_strip_area]

            for piece in pieces:
                strips.append(BuildableStrip(
                    polygon=piece,
                    segment=seg,
                    side=side,
                    road_edge_length_ft=seg.length_ft,
                    depth_ft=lot_depth,
                ))

    return strips


def compute_road_union(
    segments:       List[RoadSegment],
    half_road_width: float = 20.0,
) -> Polygon:
    """
    Union of all road corridor polygons (road half-width buffer on each side).
    Used to subtract road area from buildable strips.
    """
    road_polys = []
    for seg in segments:
        try:
            buf = seg.line.buffer(half_road_width, cap_style=2, join_style=2)
            if not buf.is_empty:
                road_polys.append(buf)
        except Exception:
            pass
    if not road_polys:
        return Polygon()
    return unary_union(road_polys)
