"""
Topology-Agnostic Subdivision Engine — model_lab

Orchestrates the full pipeline from a ProposedGraph (or centerlines) to a
LayoutResult-compatible metrics dict, without relying on the production
engine's template-specific lot-placement logic.

Pipeline
--------
1. Extract RoadSegments from graph
2. Compute road union polygon
3. Compute buildable strips (both sides of each road segment)
4. Slice strips into lot polygons
5. Validate lots against zoning constraints
6. Compute layout metrics

The output metrics dict matches the schema returned by
model_lab.training.layout_runner.LayoutResult.metrics so that existing
scoring functions (score_layout) work unchanged.

No production code is modified.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from shapely.geometry import LineString, MultiPolygon, Polygon
from shapely.ops import unary_union

from model_lab.subdivision.buildable_strip import (
    BuildableStrip,
    compute_buildable_strips,
    compute_road_union,
)
from model_lab.subdivision.lot_slicer import LotPolygon, slice_all_strips
from model_lab.subdivision.lot_validator import validate_lots
from model_lab.subdivision.road_edge_extractor import (
    RoadSegment,
    extract_segments_from_centerlines,
    extract_segments_from_proposed_graph,
)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class SubdivisionResult:
    """Full output of the topology-agnostic subdivision engine."""

    lots:               List[LotPolygon]    # valid lots
    segments:           List[RoadSegment]   # road segments used
    strips:             List[BuildableStrip] # buildable strips
    road_union:         Polygon             # combined road polygon
    metrics:            Dict                # matches LayoutResult.metrics schema
    lot_count:          int
    road_length_ft:     float
    developable_area_sqft: float


# ---------------------------------------------------------------------------
# Metrics computation
# ---------------------------------------------------------------------------

def _compute_metrics(
    lots:              List[LotPolygon],
    segments:          List[RoadSegment],
    parcel_polygon:    Polygon,
    road_union:        Polygon,
) -> Dict:
    """
    Compute layout metrics in the same schema as LayoutResult.metrics.

    Keys (matching layout_runner.LayoutResult.metrics):
        generated_lot_count, road_length_ft, developable_area_sqft,
        avg_lot_area_sqft, avg_lot_frontage_ft, avg_lot_depth_ft,
        min_lot_area_sqft, max_lot_area_sqft,
        parcel_area_sqft, road_coverage_ratio, lot_coverage_ratio
    """
    lot_count    = len(lots)
    road_len     = sum(s.length_ft for s in segments)
    dev_area     = sum(lot.area_sqft for lot in lots)
    parcel_area  = parcel_polygon.area
    road_area    = road_union.area

    areas     = [lot.area_sqft for lot in lots]
    frontages = [lot.frontage_ft for lot in lots]
    depths    = [lot.depth_ft for lot in lots]

    def avg(xs): return sum(xs) / len(xs) if xs else 0.0

    return {
        "generated_lot_count":    lot_count,
        "road_length_ft":         road_len,
        "developable_area_sqft":  dev_area,
        "avg_lot_area_sqft":      avg(areas),
        "avg_lot_frontage_ft":    avg(frontages),
        "avg_lot_depth_ft":       avg(depths),
        "min_lot_area_sqft":      min(areas) if areas else 0.0,
        "max_lot_area_sqft":      max(areas) if areas else 0.0,
        "parcel_area_sqft":       parcel_area,
        "road_coverage_ratio":    road_area / max(parcel_area, 1.0),
        "lot_coverage_ratio":     dev_area / max(parcel_area, 1.0),
    }


# ---------------------------------------------------------------------------
# Main engine function
# ---------------------------------------------------------------------------

def run_subdivision(
    graph_or_centerlines,           # ProposedGraph OR List[LineString]
    parcel_polygon:    Polygon,
    road_width_ft:     float = 32.0,
    lot_depth:         float = 110.0,
    min_frontage_ft:   float = 50.0,
    min_lot_area_sqft: float = 4000.0,
    min_depth_ft:      float = 80.0,
    min_strip_area:    float = 500.0,
) -> Optional[SubdivisionResult]:
    """
    Run the full topology-agnostic subdivision pipeline.

    Args:
        graph_or_centerlines: ProposedGraph or list of shapely LineStrings
        parcel_polygon:       shapely Polygon for the parcel boundary
        road_width_ft:        full road width (half used for offsets)
        lot_depth:            nominal lot depth from road edge
        min_frontage_ft:      minimum lot frontage
        min_lot_area_sqft:    minimum lot area
        min_depth_ft:         minimum lot depth
        min_strip_area:       minimum buildable strip area (pre-filter slivers)

    Returns:
        SubdivisionResult or None if no lots could be generated.
    """
    half_road = road_width_ft / 2.0

    # 1. Extract road segments
    try:
        from model_lab.graph_models.road_graph import ProposedGraph
        if isinstance(graph_or_centerlines, ProposedGraph):
            segments = extract_segments_from_proposed_graph(graph_or_centerlines)
        else:
            segments = extract_segments_from_centerlines(graph_or_centerlines)
    except Exception:
        segments = extract_segments_from_centerlines(graph_or_centerlines)

    if not segments:
        return None

    # 2. Road union (for corner subtraction)
    road_union = compute_road_union(segments, half_road_width=half_road)

    # 3. Buildable strips
    strips = compute_buildable_strips(
        segments=segments,
        parcel_polygon=parcel_polygon,
        road_union=road_union,
        half_road_width=half_road,
        lot_depth=lot_depth,
        min_strip_area=min_strip_area,
    )
    if not strips:
        return None

    # 4. Slice strips into lots
    raw_lots = slice_all_strips(
        strips=strips,
        min_frontage_ft=min_frontage_ft,
        min_area_sqft=min_lot_area_sqft,
        min_depth_ft=min_depth_ft,
        half_road_width=half_road,
        lot_depth=lot_depth,
    )

    # 5. Validate
    valid_lots, _ = validate_lots(
        lots=raw_lots,
        parcel_polygon=parcel_polygon,
        min_area_sqft=min_lot_area_sqft,
        min_frontage_ft=min_frontage_ft,
        min_depth_ft=min_depth_ft,
    )

    if not valid_lots:
        return None

    # 6. Deduplicate overlapping lots from adjacent strips
    valid_lots = _deduplicate_lots(valid_lots)
    if not valid_lots:
        return None

    # 7. Metrics
    metrics = _compute_metrics(valid_lots, segments, parcel_polygon, road_union)

    return SubdivisionResult(
        lots=valid_lots,
        segments=segments,
        strips=strips,
        road_union=road_union,
        metrics=metrics,
        lot_count=len(valid_lots),
        road_length_ft=metrics["road_length_ft"],
        developable_area_sqft=metrics["developable_area_sqft"],
    )


# ---------------------------------------------------------------------------
# Overlap deduplication
# ---------------------------------------------------------------------------

def _deduplicate_lots(
    lots:            List[LotPolygon],
    max_overlap_ratio: float = 0.25,   # reject lot if >25% overlaps an accepted lot
) -> List[LotPolygon]:
    """
    Greedy deduplication: sort by area descending, accept each lot only if
    it doesn't significantly overlap any already-accepted lot.
    """
    if not lots:
        return lots

    # Sort by area descending so larger lots take priority
    sorted_lots = sorted(lots, key=lambda l: l.area_sqft, reverse=True)
    accepted: List[LotPolygon] = []

    for candidate in sorted_lots:
        cp = candidate.polygon
        skip = False
        for existing in accepted:
            ep = existing.polygon
            try:
                inter = cp.intersection(ep)
                if inter.is_empty:
                    continue
                overlap_fraction = inter.area / max(cp.area, 1.0)
                if overlap_fraction > max_overlap_ratio:
                    skip = True
                    break
            except Exception:
                continue
        if not skip:
            accepted.append(candidate)

    return accepted


# ---------------------------------------------------------------------------
# Score helper  (mirrors graph_search.py inline scoring)
# ---------------------------------------------------------------------------

def score_subdivision_result(result: SubdivisionResult) -> float:
    """
    Score a SubdivisionResult using the same formula as graph_search.py.

    overall = 0.6 * yield_score + 0.4 * efficiency_score
    """
    lot_count = result.lot_count
    road_len  = max(result.road_length_ft, 1.0)
    dev_area  = result.developable_area_sqft

    yield_sc = lot_count / 40.0
    eff_sc   = (dev_area / road_len) / 200.0
    return 0.6 * yield_sc + 0.4 * eff_sc
