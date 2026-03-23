"""
Production Lot Subdivision Engine

Topology-agnostic subdivision pipeline:
  centerlines → road segments → buildable strips → lot slicing
  → overlap deduplication → validation → SubdivisionResult

All coordinates are in local feet (origin at parcel centroid).
No model_lab imports — self-contained production implementation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from shapely.geometry import LineString, Polygon, MultiPolygon
from shapely.ops import unary_union


# ---------------------------------------------------------------------------
# Road segment extraction
# ---------------------------------------------------------------------------

@dataclass
class RoadSegment:
    line:       LineString
    start:      Tuple[float, float]
    end:        Tuple[float, float]
    length_ft:  float
    dx:         float   # unit direction
    dy:         float
    nx:         float   # left normal (-dy, dx)
    ny:         float
    edge_id:    int


def _extract_segments(centerlines: List[LineString]) -> List[RoadSegment]:
    segments = []
    for edge_id, line in enumerate(centerlines):
        coords = list(line.coords)
        for i in range(len(coords) - 1):
            x0, y0 = coords[i]
            x1, y1 = coords[i + 1]
            length = math.hypot(x1 - x0, y1 - y0)
            if length < 1.0:
                continue
            dx, dy = (x1 - x0) / length, (y1 - y0) / length
            nx, ny = -dy, dx
            segments.append(RoadSegment(
                line=LineString([(x0, y0), (x1, y1)]),
                start=(x0, y0),
                end=(x1, y1),
                length_ft=length,
                dx=dx, dy=dy,
                nx=nx, ny=ny,
                edge_id=edge_id,
            ))
    return segments


# ---------------------------------------------------------------------------
# Buildable strip computation
# ---------------------------------------------------------------------------

@dataclass
class BuildableStrip:
    polygon:            Polygon
    segment:            RoadSegment
    side:               int     # +1 = left normal, -1 = right normal
    road_edge_length_ft: float
    depth_ft:           float


def _compute_road_union(segments: List[RoadSegment], half_road_width: float) -> Polygon:
    buffers = [seg.line.buffer(half_road_width, cap_style=2) for seg in segments]
    if not buffers:
        return Polygon()
    union = unary_union(buffers)
    try:
        union = union.buffer(0)
    except Exception:
        pass
    return union


def _build_strip_polygon(
    seg: RoadSegment,
    side: int,
    half_road_width: float,
    lot_depth: float,
    slab_extension: float = 2.0,
) -> Polygon:
    """Build a rectangular strip polygon on one side of a road segment."""
    x0, y0 = seg.start
    x1, y1 = seg.end
    nx, ny = seg.nx * side, seg.ny * side

    # Extend slightly beyond segment ends to avoid gaps at intersections
    ex, ey = seg.dx * slab_extension, seg.dy * slab_extension

    # Four corners: road edge → lot back
    r0x = x0 - ex + nx * half_road_width
    r0y = y0 - ey + ny * half_road_width
    r1x = x1 + ex + nx * half_road_width
    r1y = y1 + ey + ny * half_road_width
    b1x = x1 + ex + nx * (half_road_width + lot_depth)
    b1y = y1 + ey + ny * (half_road_width + lot_depth)
    b0x = x0 - ex + nx * (half_road_width + lot_depth)
    b0y = y0 - ey + ny * (half_road_width + lot_depth)

    return Polygon([(r0x, r0y), (r1x, r1y), (b1x, b1y), (b0x, b0y)])


def _compute_buildable_strips(
    segments: List[RoadSegment],
    parcel_polygon: Polygon,
    road_union: Polygon,
    half_road_width: float = 20.0,
    lot_depth: float = 110.0,
    min_strip_area: float = 500.0,
) -> List[BuildableStrip]:
    strips = []
    for seg in segments:
        for side in (+1, -1):
            raw = _build_strip_polygon(seg, side, half_road_width, lot_depth)
            try:
                clipped = raw.intersection(parcel_polygon)
                clipped = clipped.difference(road_union)
            except Exception:
                continue

            if clipped.is_empty or clipped.area < min_strip_area:
                continue

            # Normalize to Polygon (take largest if MultiPolygon)
            if clipped.geom_type == "MultiPolygon":
                clipped = max(clipped.geoms, key=lambda g: g.area)
            try:
                clipped = clipped.buffer(0)
            except Exception:
                continue
            if clipped.geom_type != "Polygon":
                continue

            strips.append(BuildableStrip(
                polygon=clipped,
                segment=seg,
                side=side,
                road_edge_length_ft=seg.length_ft,
                depth_ft=lot_depth,
            ))
    return strips


# ---------------------------------------------------------------------------
# Lot slicing
# ---------------------------------------------------------------------------

@dataclass
class LotPolygon:
    polygon:     Polygon
    strip:       BuildableStrip
    slot_index:  int
    frontage_ft: float
    depth_ft:    float
    area_sqft:   float


def _slice_strip(
    strip: BuildableStrip,
    min_frontage_ft: float = 50.0,
    max_frontage_ft: float = 100.0,
    min_lot_area_sqft: float = 4000.0,
    side_setback_ft: float = 0.0,
    min_buildable_width_ft: float = 0.0,
    slab_extension: float = 2.0,
) -> List[LotPolygon]:
    seg = strip.segment
    road_len = seg.length_ft
    required_frontage = max(
        min_frontage_ft,
        (min_lot_area_sqft / max(strip.depth_ft, 1.0)) + (2.0 * side_setback_ft),
        min_buildable_width_ft + (2.0 * side_setback_ft),
    )
    if road_len < required_frontage:
        return []

    target_frontage = max(required_frontage, min(max_frontage_ft, required_frontage * 1.15))
    n_slots = max(1, int(road_len / max(target_frontage, 1.0)))
    slot_width = road_len / n_slots
    while n_slots > 1 and slot_width < required_frontage:
        n_slots -= 1
        slot_width = road_len / n_slots

    lots = []
    for i in range(n_slots):
        t0 = i / n_slots
        t1 = (i + 1) / n_slots

        # Slab cutting plane — perpendicular to road segment, extending ±(depth+ext)
        depth_ext = strip.depth_ft + slab_extension * 4
        nx_road, ny_road = seg.nx, seg.ny

        # Road-direction vector
        dx, dy = seg.dx, seg.dy
        x0, y0 = seg.start
        x1, y1 = seg.end

        # Cut positions along segment
        cx0 = x0 + dx * t0 * road_len
        cy0 = y0 + dy * t0 * road_len
        cx1 = x0 + dx * t1 * road_len
        cy1 = y0 + dy * t1 * road_len

        # Build a slab between the two cut planes
        slab = Polygon([
            (cx0 - nx_road * depth_ext, cy0 - ny_road * depth_ext),
            (cx0 + nx_road * depth_ext, cy0 + ny_road * depth_ext),
            (cx1 + nx_road * depth_ext, cy1 + ny_road * depth_ext),
            (cx1 - nx_road * depth_ext, cy1 - ny_road * depth_ext),
        ])

        try:
            lot_poly = strip.polygon.intersection(slab)
        except Exception:
            continue

        if lot_poly.is_empty or lot_poly.area < 100.0:
            continue

        if lot_poly.geom_type == "MultiPolygon":
            lot_poly = max(lot_poly.geoms, key=lambda g: g.area)
        if lot_poly.geom_type != "Polygon":
            continue

        frontage = slot_width
        depth = lot_poly.area / max(frontage, 1.0)

        lots.append(LotPolygon(
            polygon=lot_poly,
            strip=strip,
            slot_index=i,
            frontage_ft=frontage,
            depth_ft=depth,
            area_sqft=lot_poly.area,
        ))

    return lots


def _slice_all_strips(
    strips: List[BuildableStrip],
    min_frontage_ft: float = 50.0,
    max_frontage_ft: float = 100.0,
    min_lot_area_sqft: float = 4000.0,
    side_setback_ft: float = 0.0,
    min_buildable_width_ft: float = 0.0,
    max_total_lots: Optional[int] = None,
) -> List[LotPolygon]:
    lots = []
    for strip in sorted(strips, key=lambda item: item.road_edge_length_ft, reverse=True):
        if max_total_lots is not None and len(lots) >= max_total_lots:
            break
        strip_lots = _slice_strip(
            strip,
            min_frontage_ft=min_frontage_ft,
            max_frontage_ft=max_frontage_ft,
            min_lot_area_sqft=min_lot_area_sqft,
            side_setback_ft=side_setback_ft,
            min_buildable_width_ft=min_buildable_width_ft,
        )
        if max_total_lots is not None:
            remaining = max_total_lots - len(lots)
            strip_lots = strip_lots[:max(0, remaining)]
        lots.extend(strip_lots)
    return lots


# ---------------------------------------------------------------------------
# Lot deduplication
# ---------------------------------------------------------------------------

def _deduplicate_lots(
    lots: List[LotPolygon],
    max_overlap_ratio: float = 0.25,
) -> List[LotPolygon]:
    """Greedy deduplication: keep a lot only if <25% overlaps accepted lots."""
    if not lots:
        return []

    # Sort by area descending — prefer larger lots
    sorted_lots = sorted(lots, key=lambda l: l.area_sqft, reverse=True)
    accepted: List[LotPolygon] = []
    accepted_union = None

    for lot in sorted_lots:
        if accepted_union is None:
            accepted.append(lot)
            accepted_union = lot.polygon
            continue

        try:
            overlap = lot.polygon.intersection(accepted_union).area
        except Exception:
            overlap = 0.0

        if overlap / max(lot.area_sqft, 1.0) < max_overlap_ratio:
            accepted.append(lot)
            try:
                accepted_union = accepted_union.union(lot.polygon)
            except Exception:
                pass

    return accepted


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

@dataclass
class ValidationSummary:
    total_before:   int
    total_after:    int
    rejected_small: int
    rejected_shape: int
    rejected_compactness: int
    rejected_outside: int


def _validate_lots(
    lots: List[LotPolygon],
    parcel_polygon: Polygon,
    min_area_sqft: float = 4000.0,
    min_frontage_ft: float = 40.0,
    side_setback_ft: float = 0.0,
    min_buildable_width_ft: float = 0.0,
    max_depth_ft: Optional[float] = None,
    max_depth_width_ratio: float = 4.0,
    min_compactness: float = 0.08,
    max_outside_ratio: float = 0.02,
) -> Tuple[List[LotPolygon], ValidationSummary]:
    total_before = len(lots)
    rejected_small = 0
    rejected_shape = 0
    rejected_compactness = 0
    rejected_outside = 0
    valid = []

    for lot in lots:
        if lot.area_sqft < min_area_sqft:
            rejected_small += 1
            continue
        if lot.frontage_ft < min_frontage_ft:
            rejected_shape += 1
            continue
        # Enforce bilateral side setbacks on the gross lot width used by slicing.
        if min_buildable_width_ft and lot.frontage_ft + 1e-6 < min_buildable_width_ft + (2.0 * side_setback_ft):
            rejected_shape += 1
            continue
        if max_depth_ft is not None and lot.depth_ft > max_depth_ft * 1.02:
            rejected_shape += 1
            continue
        min_x, min_y, max_x, max_y = lot.polygon.bounds
        if lot.depth_ft > 0 and lot.frontage_ft > 0:
            ratio = lot.depth_ft / lot.frontage_ft
            if ratio > max_depth_width_ratio:
                rejected_shape += 1
                continue
        try:
            perimeter = lot.polygon.length
            compactness = 4.0 * math.pi * lot.area_sqft / max(perimeter * perimeter, 1.0)
        except Exception:
            compactness = 0.0
        if compactness < min_compactness:
            rejected_compactness += 1
            continue
        try:
            outside_ratio = lot.polygon.difference(parcel_polygon).area / max(lot.area_sqft, 1.0)
        except Exception:
            outside_ratio = 1.0
        if outside_ratio > max_outside_ratio:
            rejected_outside += 1
            continue
        valid.append(lot)

    return valid, ValidationSummary(
        total_before=total_before,
        total_after=len(valid),
        rejected_small=rejected_small,
        rejected_shape=rejected_shape,
        rejected_compactness=rejected_compactness,
        rejected_outside=rejected_outside,
    )


# ---------------------------------------------------------------------------
# Main result type + orchestrator
# ---------------------------------------------------------------------------

@dataclass
class SubdivisionResult:
    lots:           List[LotPolygon]
    segments:       List[RoadSegment]
    strips:         List[BuildableStrip]
    validation:     ValidationSummary
    metrics:        dict = field(default_factory=dict)


def run_subdivision(
    centerlines: List[LineString],
    parcel_polygon: Polygon,
    road_width_ft: float = 32.0,
    lot_depth: float = 110.0,
    min_frontage_ft: float = 50.0,
    max_frontage_ft: float = 100.0,
    min_area_sqft: float = 4000.0,
    solver_constraints: Optional[Dict[str, Any]] = None,
    max_total_lots: Optional[int] = None,
) -> Optional[SubdivisionResult]:
    """
    Run the full topology-agnostic subdivision pipeline.

    Args:
        centerlines:     Shapely LineStrings in local feet
        parcel_polygon:  Shapely Polygon in local feet
        road_width_ft:   Total road width (each side = half)
        lot_depth:       Target lot depth in feet
        min_frontage_ft: Minimum lot frontage
        max_frontage_ft: Maximum lot frontage
        min_area_sqft:   Minimum lot area for validation

    Returns:
        SubdivisionResult or None if pipeline produces no lots.
    """
    if not centerlines:
        return None

    half_road = road_width_ft / 2.0

    # 1. Extract segments
    segments = _extract_segments(centerlines)
    if not segments:
        return None

    # 2. Compute road union (for setback subtraction)
    road_union = _compute_road_union(segments, half_road)

    # 3. Compute buildable strips
    strips = _compute_buildable_strips(
        segments, parcel_polygon, road_union,
        half_road_width=half_road,
        lot_depth=lot_depth,
    )
    if not strips:
        return None

    solver_constraints = solver_constraints or {}
    validation_min_area_sqft = float(solver_constraints.get("min_lot_area_sqft", min_area_sqft) or min_area_sqft)
    validation_min_frontage_ft = float(solver_constraints.get("min_frontage_ft", min_frontage_ft) or min_frontage_ft)
    side_setback_ft = float(solver_constraints.get("side_setback_ft", 0.0) or 0.0)
    required_buildable_width_ft = float(solver_constraints.get("required_buildable_width_ft", 0.0) or 0.0)
    max_buildable_depth_ft = float(solver_constraints.get("max_buildable_depth_ft", lot_depth) or lot_depth)
    if solver_constraints.get("max_units") is not None and max_total_lots is None:
        max_total_lots = int(solver_constraints["max_units"])

    # 4. Slice into lots
    raw_lots = _slice_all_strips(
        strips,
        min_frontage_ft=min_frontage_ft,
        max_frontage_ft=max_frontage_ft,
        min_lot_area_sqft=validation_min_area_sqft,
        side_setback_ft=side_setback_ft,
        min_buildable_width_ft=required_buildable_width_ft,
        max_total_lots=max_total_lots,
    )

    # 5. Deduplicate (prevent double-counting from adjacent strips)
    deduped = _deduplicate_lots(raw_lots)
    if max_total_lots is not None:
        deduped = deduped[:max_total_lots]

    # 6. Validate
    valid_lots, summary = _validate_lots(
        deduped,
        parcel_polygon,
        min_area_sqft=validation_min_area_sqft,
        min_frontage_ft=validation_min_frontage_ft,
        side_setback_ft=side_setback_ft,
        min_buildable_width_ft=required_buildable_width_ft,
        max_depth_ft=max_buildable_depth_ft,
    )

    if not valid_lots:
        return None

    # 7. Compute metrics
    total_road_len = sum(seg.length_ft for seg in segments)
    total_lot_area = sum(l.area_sqft for l in valid_lots)
    parcel_area = parcel_polygon.area
    dev_ratio = total_lot_area / max(parcel_area, 1.0)
    avg_compactness = 0.0
    if valid_lots:
        compactness_values = []
        for lot in valid_lots:
            perimeter = lot.polygon.length
            compactness_values.append(4.0 * math.pi * lot.area_sqft / max(perimeter * perimeter, 1.0))
        avg_compactness = sum(compactness_values) / len(compactness_values)
    compliance_rate = len(valid_lots) / max(len(deduped), 1)
    road_density = total_road_len / max(parcel_area / 43560.0, 0.01)

    metrics = {
        "lot_count":         len(valid_lots),
        "total_road_ft":     round(total_road_len, 1),
        "total_lot_area_sqft": round(total_lot_area, 1),
        "parcel_area_sqft":  round(parcel_area, 1),
        "dev_area_ratio":    round(dev_ratio, 4),
        "avg_lot_area_sqft": round(total_lot_area / len(valid_lots), 1),
        "avg_frontage_ft":   round(sum(l.frontage_ft for l in valid_lots) / len(valid_lots), 1),
        "avg_lot_compactness": round(avg_compactness, 4),
        "compliance_rate":   round(compliance_rate, 4),
        "road_density_ft_per_acre": round(road_density, 1),
        "rejected_small": summary.rejected_small,
        "rejected_shape": summary.rejected_shape,
        "rejected_compactness": summary.rejected_compactness,
        "rejected_outside": summary.rejected_outside,
    }

    return SubdivisionResult(
        lots=valid_lots,
        segments=segments,
        strips=strips,
        validation=summary,
        metrics=metrics,
    )


def score_subdivision(result: SubdivisionResult) -> float:
    """
    Compute a scalar score for a subdivision result.

    Score = 0.6 * (lot_count / 40) + 0.4 * (dev_area_ratio / road_density_norm)
    Clamped to [0, 1.5].
    """
    lot_count = float(result.metrics.get("lot_count", 0))
    road_ft = float(result.metrics.get("total_road_ft", 1.0))
    dev_ratio = float(result.metrics.get("dev_area_ratio", 0.0))
    avg_lot_area = float(result.metrics.get("avg_lot_area_sqft", 0.0))
    avg_compactness = float(result.metrics.get("avg_lot_compactness", 0.0))
    compliance_rate = float(result.metrics.get("compliance_rate", 0.0))

    yield_score = min(1.0, lot_count / 32.0)
    efficiency_score = min(1.0, dev_ratio / max(road_ft / 6000.0, 0.08))
    regularity_score = min(1.0, (avg_compactness / 0.35))
    compliance_score = min(1.0, compliance_rate)
    area_score = min(1.0, avg_lot_area / 9000.0) if avg_lot_area > 0 else 0.0

    score = (
        0.34 * yield_score
        + 0.22 * efficiency_score
        + 0.18 * regularity_score
        + 0.18 * compliance_score
        + 0.08 * area_score
    )
    return max(0.0, min(2.0, score))
