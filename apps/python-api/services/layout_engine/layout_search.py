"""
Production Layout Search

Main pipeline: parcel polygon → candidate road networks → guided/deterministic selection
→ subdivision simulation → ranked results with GeoJSON output.

No model_lab imports — self-contained production implementation.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from shapely.geometry import LineString, Polygon, mapping

from .graph_generator import RoadNetwork, generate_candidates, generate_candidates_multi_strategy
from .graph_prior_inference import GraphPriorInference, get_prior
from .lot_subdivision import SubdivisionResult, run_subdivision, score_subdivision

MAX_CANDIDATE_CAP = 48
MAX_STAGNANT_EVALUATIONS = 24

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class LayoutCandidate:
    """A single evaluated layout candidate."""
    network:     RoadNetwork
    result:      SubdivisionResult
    score:       float
    rank:        int
    geojson:     Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# GeoJSON serialization
# ---------------------------------------------------------------------------

def _network_to_features(network: RoadNetwork) -> List[Dict]:
    features = []
    for line in network.centerlines:
        features.append({
            "type": "Feature",
            "geometry": mapping(line),
            "properties": {
                "layer":          "road",
                "generator_type": network.generator_type,
            },
        })
    return features


def _result_to_features(
    result: SubdivisionResult,
    to_lnglat,       # callable: (x_ft, y_ft) -> (lng, lat)
    local: bool = False,
) -> List[Dict]:
    """Convert lots and roads to GeoJSON features.

    Args:
        result:     SubdivisionResult in local feet
        to_lnglat:  coordinate conversion function
        local:      if True, skip coordinate conversion (for testing)
    """
    features = []

    # Road centerlines
    for seg in result.segments:
        if local:
            coords = list(seg.line.coords)
        else:
            coords = [to_lnglat(x, y) for x, y in seg.line.coords]
        features.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {"layer": "road"},
        })

    # Lot polygons
    for lot in result.lots:
        if local:
            raw_coords = list(lot.polygon.exterior.coords)
        else:
            raw_coords = [to_lnglat(x, y) for x, y in lot.polygon.exterior.coords]
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [raw_coords]},
            "properties": {
                "layer":        "lots",
                "area_sqft":    round(lot.area_sqft, 0),
                "frontage_ft":  round(lot.frontage_ft, 1),
                "depth_ft":     round(lot.depth_ft, 1),
                "slot_index":   lot.slot_index,
            },
        })

    return features


# ---------------------------------------------------------------------------
# Main search function
# ---------------------------------------------------------------------------


def _prepare_parcel_polygon(parcel_polygon: Polygon) -> Polygon:
    prepared = parcel_polygon
    if prepared.is_empty:
        raise ValueError("Layout search requires a non-empty parcel geometry")
    if prepared.geom_type == "Polygon":
        prepared = _sanitize_polygon(prepared)
    try:
        if not prepared.is_valid:
            prepared = prepared.buffer(0)
    except Exception:
        pass
    if prepared.geom_type == "MultiPolygon":
        prepared = max(prepared.geoms, key=lambda geom: geom.area)
    if prepared.geom_type != "Polygon":
        raise ValueError("Layout search requires a polygon parcel geometry")
    try:
        simplified = prepared.simplify(1.5, preserve_topology=True)
        if simplified.geom_type == "Polygon" and simplified.area >= prepared.area * 0.97:
            prepared = simplified
    except Exception:
        pass
    if prepared.is_empty or prepared.area < 100.0:
        raise ValueError("Parcel geometry is too small or degenerate for layout search")
    return prepared


def _sanitize_polygon(polygon: Polygon) -> Polygon:
    def _distance(a: Tuple[float, float], b: Tuple[float, float]) -> float:
        return math.hypot(a[0] - b[0], a[1] - b[1])

    def _sanitize_ring(coords: List[Tuple[float, float]], *, min_edge_ft: float = 0.25) -> List[Tuple[float, float]]:
        if not coords:
            return []
        points = [(float(x), float(y)) for x, y in coords]
        if len(points) > 1 and _distance(points[0], points[-1]) <= 1e-6:
            points = points[:-1]
        deduped: List[Tuple[float, float]] = []
        for point in points:
            if not deduped or _distance(deduped[-1], point) > 1e-6:
                deduped.append(point)
        if len(deduped) < 3:
            return []
        filtered = [deduped[0]]
        for point in deduped[1:]:
            if _distance(filtered[-1], point) >= min_edge_ft:
                filtered.append(point)
        if len(filtered) < 3:
            return []
        if _distance(filtered[0], filtered[-1]) > 1e-6:
            filtered.append(filtered[0])
        return filtered

    try:
        exterior = _sanitize_ring(list(polygon.exterior.coords))
        if len(exterior) < 4:
            return polygon
        holes: List[List[Tuple[float, float]]] = []
        for ring in polygon.interiors:
            cleaned = _sanitize_ring(list(ring.coords))
            if len(cleaned) >= 4:
                holes.append(cleaned)
        cleaned = Polygon(exterior, holes=holes)
        if cleaned.is_empty:
            return polygon
        if not cleaned.is_valid:
            cleaned = cleaned.buffer(0)
        if cleaned.geom_type == "MultiPolygon":
            cleaned = max(cleaned.geoms, key=lambda geom: geom.area)
        return cleaned if cleaned.geom_type == "Polygon" else polygon
    except Exception:
        return polygon


def _parcel_variants(parcel_polygon: Polygon) -> List[Polygon]:
    variants = [parcel_polygon]
    try:
        smoothed = parcel_polygon.buffer(1.0, join_style=2).buffer(-1.0, join_style=2)
        if smoothed.geom_type == "Polygon" and smoothed.area >= parcel_polygon.area * 0.92:
            variants.append(smoothed)
    except Exception:
        pass
    try:
        simplified = parcel_polygon.simplify(3.0, preserve_topology=True)
        if simplified.geom_type == "Polygon" and simplified.area >= parcel_polygon.area * 0.90:
            variants.append(simplified)
    except Exception:
        pass
    unique: List[Polygon] = []
    seen = set()
    for variant in variants:
        key = tuple(round(value, 3) for value in variant.bounds)
        if key in seen:
            continue
        seen.add(key)
        unique.append(variant)
    return unique


def _candidate_satisfies_constraints(
    result: SubdivisionResult,
    *,
    min_lot_area_sqft: float = 0.0,
    max_lot_depth_ft: Optional[float] = None,
    side_setback_ft: float = 0.0,
    min_buildable_width_ft: float = 0.0,
    solver_constraints: Optional[Dict[str, Any]],
    max_units: Optional[int],
) -> bool:
    solver_constraints = solver_constraints or {}
    min_lot_area_sqft = max(min_lot_area_sqft, float(solver_constraints.get("min_lot_area_sqft", 0.0) or 0.0))
    min_frontage_ft = solver_constraints.get("min_frontage_ft")
    if max_units is not None and result.metrics.get("lot_count", 0) > max_units:
        return False
    for lot in result.lots:
        if min_lot_area_sqft and lot.area_sqft + 1e-6 < min_lot_area_sqft:
            return False
        if max_lot_depth_ft is not None and lot.depth_ft - 1e-6 > max_lot_depth_ft * 1.02:
            return False
        if min_frontage_ft is not None and lot.frontage_ft + 1e-6 < float(min_frontage_ft):
            return False
        # Keep width checks aligned with subdivision slicing logic.
        if min_buildable_width_ft and lot.frontage_ft + 1e-6 < min_buildable_width_ft + (2.0 * side_setback_ft):
            return False
    return True


def _constraint_alignment_score(
    result: SubdivisionResult,
    *,
    target_lot_depth_ft: float,
    target_frontage_ft: float,
    max_units: Optional[int],
) -> float:
    metrics = result.metrics
    lot_count = float(metrics.get("lot_count", 0.0) or 0.0)
    avg_frontage_ft = float(metrics.get("avg_frontage_ft", 0.0) or 0.0)
    avg_depth_ft = float(metrics.get("avg_depth_ft", 0.0) or 0.0)
    compliance_rate = float(metrics.get("compliance_rate", 0.0) or 0.0)

    density_alignment = 0.0
    if max_units is not None and max_units > 0:
        density_alignment = max(0.0, 1.0 - (abs(lot_count - max_units) / max(float(max_units), 1.0)))

    frontage_alignment = 0.0
    if target_frontage_ft > 0.0 and avg_frontage_ft > 0.0:
        frontage_alignment = max(
            0.0,
            1.0 - (abs(avg_frontage_ft - target_frontage_ft) / max(target_frontage_ft, 1.0)),
        )

    depth_alignment = 0.0
    if target_lot_depth_ft > 0.0 and avg_depth_ft > 0.0:
        depth_alignment = max(
            0.0,
            1.0 - (abs(avg_depth_ft - target_lot_depth_ft) / max(target_lot_depth_ft, 1.0)),
        )

    return (
        0.24 * density_alignment
        + 0.16 * frontage_alignment
        + 0.16 * depth_alignment
        + 0.04 * min(1.0, compliance_rate)
    )


def _network_sort_key(network: RoadNetwork) -> tuple:
    line_keys = []
    for line in network.centerlines:
        coords = tuple((round(float(x), 3), round(float(y), 3)) for x, y in line.coords)
        line_keys.append(coords)
    return (
        str(network.generator_type),
        len(network.centerlines),
        round(sum(line.length for line in network.centerlines), 3),
        tuple(sorted(line_keys)),
    )


def _evaluated_candidate_sort_key(item: Tuple[float, RoadNetwork, SubdivisionResult]) -> tuple:
    score, network, result = item
    metrics = result.metrics
    return (
        -round(float(score), 8),
        -int(metrics.get("lot_count", 0) or 0),
        round(float(metrics.get("total_road_ft", 0.0) or 0.0), 3),
        _network_sort_key(network),
    )

def run_layout_search(
    parcel_polygon:   Polygon,
    area_sqft:        float,
    to_lnglat,
    n_candidates:     int = 24,
    n_top:            int = 3,
    seed:             int = 0,
    road_width_ft:    float = 32.0,
    lot_depth:        float = 110.0,
    min_frontage_ft:  float = 50.0,
    min_lot_area_sqft: float = 4000.0,
    side_setback_ft: float = 0.0,
    min_buildable_width_ft: float = 0.0,
    zoning_rules: Optional[Dict[str, Any]] = None,
    solver_constraints: Optional[Dict[str, Any]] = None,
    search_heuristics: Optional[Dict[str, Any]] = None,
    max_units: Optional[int] = None,
    use_prior:        bool = True,
    max_runtime_seconds: float = 55.0,
) -> List[LayoutCandidate]:
    """
    Generate and evaluate road network layouts for a parcel.

    Strategy:
      1. Generate a pool of candidate road networks (6 topology types)
      2. If prior available: score all candidates, simulate top n_candidates
         from a 2× oversampled pool (mutation-filtering guided search)
      3. If no prior: simulate all n_candidates directly
      4. Return top n_top results by score, with GeoJSON

    Args:
        parcel_polygon:  Shapely Polygon in local feet
        area_sqft:       Parcel area in sqft
        to_lnglat:       Coordinate conversion fn (x_ft, y_ft) -> [lng, lat]
        n_candidates:    Number of networks to simulate
        n_top:           Number of top results to return
        seed:            Deterministic variant offset for reproducibility
        road_width_ft:   Total road width
        lot_depth:       Target lot depth in feet
        min_frontage_ft: Minimum lot frontage in feet
        use_prior:       Whether to use graph prior for guided selection

    Returns:
        List of up to n_top LayoutCandidate objects, ranked by score descending.
    """
    started = time.perf_counter()
    n_candidates = max(1, min(int(n_candidates), MAX_CANDIDATE_CAP))
    parcel_polygon = _prepare_parcel_polygon(parcel_polygon)
    area_sqft = float(area_sqft or parcel_polygon.area)
    prior: Optional[GraphPriorInference] = get_prior() if use_prior else None
    heuristics = search_heuristics or {}
    solver_constraints = solver_constraints or {}
    road_width_ft = float(heuristics.get("road_width_ft", road_width_ft))
    lot_depth = float(heuristics.get("target_lot_depth_ft", lot_depth))
    min_frontage_ft = float(heuristics.get("frontage_hint_ft", min_frontage_ft))
    max_runtime_seconds = float(heuristics.get("max_runtime_seconds", max_runtime_seconds))
    strategies = heuristics.get("strategies") or ["grid", "spine-road", "cul-de-sac"]

    simulation_attempts = [
        {
            "road_width_ft": road_width_ft,
            "lot_depth": lot_depth,
            "min_frontage_ft": min_frontage_ft,
            "max_frontage_ft": max(min_frontage_ft, min(min_frontage_ft * 1.15, lot_depth * 1.05)),
            "min_area_sqft": min_lot_area_sqft,
        },
        {
            "road_width_ft": road_width_ft,
            "lot_depth": lot_depth,
            "min_frontage_ft": min_frontage_ft,
            "max_frontage_ft": max(min_frontage_ft, min(min_frontage_ft * 1.05, lot_depth)),
            "min_area_sqft": min_lot_area_sqft,
        },
        {
            "road_width_ft": max(24.0, road_width_ft * 0.92),
            "lot_depth": max(80.0, lot_depth * 0.94),
            "min_frontage_ft": max(35.0, min_frontage_ft * 0.95),
            "max_frontage_ft": max(40.0, min_frontage_ft * 1.10),
            "min_area_sqft": min_lot_area_sqft,
        },
        {
            "road_width_ft": min(40.0, road_width_ft * 1.05),
            "lot_depth": min(130.0, lot_depth * 1.04),
            "min_frontage_ft": max(35.0, min_frontage_ft * 0.90),
            "max_frontage_ft": max(40.0, lot_depth * 1.20),
            "min_area_sqft": min_lot_area_sqft,
        },
        {
            "road_width_ft": max(22.0, road_width_ft * 0.84),
            "lot_depth": max(75.0, lot_depth * 0.82),
            "min_frontage_ft": max(30.0, min_frontage_ft * 0.85),
            "max_frontage_ft": max(38.0, min_frontage_ft * 1.05),
            "min_area_sqft": min_lot_area_sqft,
        },
        {
            "road_width_ft": max(24.0, road_width_ft * 0.88),
            "lot_depth": min(180.0, lot_depth * 1.18),
            "min_frontage_ft": max(32.0, min_frontage_ft * 0.88),
            "max_frontage_ft": max(42.0, min(min_frontage_ft * 1.18, lot_depth * 1.25)),
            "min_area_sqft": min_lot_area_sqft,
        },
        {
            "road_width_ft": min(44.0, road_width_ft * 1.12),
            "lot_depth": max(85.0, lot_depth * 0.9),
            "min_frontage_ft": max(35.0, min_frontage_ft * 0.92),
            "max_frontage_ft": max(42.0, min_frontage_ft * 1.08),
            "min_area_sqft": min_lot_area_sqft,
        },
        {
            "road_width_ft": max(20.0, road_width_ft * 0.8),
            "lot_depth": min(220.0, lot_depth * 1.28),
            "min_frontage_ft": max(28.0, min_frontage_ft * 0.82),
            "max_frontage_ft": max(45.0, min(min_frontage_ft * 1.2, lot_depth * 1.3)),
            "min_area_sqft": min_lot_area_sqft,
        },
        {
            "road_width_ft": max(26.0, road_width_ft * 0.96),
            "lot_depth": min(240.0, lot_depth * 1.36),
            "min_frontage_ft": max(30.0, min_frontage_ft * 0.86),
            "max_frontage_ft": max(48.0, min(lot_depth * 1.32, min_frontage_ft * 1.25)),
            "min_area_sqft": min_lot_area_sqft,
        },
        {
            "road_width_ft": min(42.0, road_width_ft * 1.08),
            "lot_depth": max(90.0, lot_depth * 0.96),
            "min_frontage_ft": max(34.0, min_frontage_ft * 0.8),
            "max_frontage_ft": max(50.0, min_frontage_ft * 1.3),
            "min_area_sqft": min_lot_area_sqft,
        },
    ]

    evaluated: List[Tuple[float, RoadNetwork, SubdivisionResult]] = []
    best_score: float | None = None
    stagnant_evaluations = 0
    parcel_variants = _parcel_variants(parcel_polygon)
    for variant_index, parcel_variant in enumerate(parcel_variants):
        if (time.perf_counter() - started) > max_runtime_seconds:
            break
        selected: List[RoadNetwork] = []
        try:
            if prior is not None:
                pool_size = n_candidates * 2
                pool = generate_candidates_multi_strategy(
                    parcel_variant,
                    area_sqft,
                    n=pool_size,
                    seed=seed + variant_index,
                    strategies=strategies,
                    design_targets={
                        "lot_depth_ft": lot_depth,
                        "min_frontage_ft": min_frontage_ft,
                    },
                )
                pool = sorted(pool, key=_network_sort_key)
                scored = prior.rank_networks(pool, parcel_variant, area_sqft)
                selected = [item.network for item in scored[:n_candidates]]
            else:
                selected = generate_candidates_multi_strategy(
                    parcel_variant,
                    area_sqft,
                    n=n_candidates,
                    seed=seed + variant_index,
                    strategies=strategies,
                    design_targets={
                        "lot_depth_ft": lot_depth,
                        "min_frontage_ft": min_frontage_ft,
                    },
                )
        except Exception:
            selected = []
        if not selected:
            try:
                selected = generate_candidates_multi_strategy(
                    parcel_variant,
                    area_sqft,
                    n=max(8, n_candidates),
                    seed=seed + 101 + variant_index,
                    strategies=strategies,
                    design_targets={
                        "lot_depth_ft": lot_depth,
                        "min_frontage_ft": min_frontage_ft,
                    },
                )
            except Exception:
                selected = []
        if not selected:
            continue
        selected = sorted(selected, key=_network_sort_key)

        for params in simulation_attempts:
            if (time.perf_counter() - started) > max_runtime_seconds:
                break
            for network in selected:
                if (time.perf_counter() - started) > max_runtime_seconds:
                    break
                try:
                    result = run_subdivision(
                        centerlines=network.centerlines,
                        parcel_polygon=parcel_variant,
                        road_width_ft=params["road_width_ft"],
                        lot_depth=params["lot_depth"],
                        min_frontage_ft=params["min_frontage_ft"],
                        max_frontage_ft=params["max_frontage_ft"],
                        min_area_sqft=params["min_area_sqft"],
                        solver_constraints=solver_constraints,
                        max_total_lots=max_units,
                    )
                except Exception:
                    result = None
                if result is None:
                    continue
                if not _candidate_satisfies_constraints(
                    result,
                    min_lot_area_sqft=min_lot_area_sqft,
                    max_lot_depth_ft=lot_depth,
                    side_setback_ft=side_setback_ft,
                    min_buildable_width_ft=min_buildable_width_ft,
                    solver_constraints=solver_constraints,
                    max_units=max_units,
                ):
                    continue
                try:
                    score = score_subdivision(result) + _constraint_alignment_score(
                        result,
                        target_lot_depth_ft=params["lot_depth"],
                        target_frontage_ft=params["min_frontage_ft"],
                        max_units=max_units,
                    )
                except Exception:
                    continue
                evaluated.append((score, network, result))
                canonical_score = round(float(score), 8)
                if best_score is None or canonical_score > best_score + 1e-8:
                    best_score = canonical_score
                    stagnant_evaluations = 0
                else:
                    stagnant_evaluations += 1
                if stagnant_evaluations >= MAX_STAGNANT_EVALUATIONS:
                    break
            if stagnant_evaluations >= MAX_STAGNANT_EVALUATIONS:
                break
        if stagnant_evaluations >= MAX_STAGNANT_EVALUATIONS:
            break

    if not evaluated:
        return []

    # -------------------------------------------------------------------
    # Rank and return top results
    # -------------------------------------------------------------------
    evaluated.sort(key=_evaluated_candidate_sort_key)
    top = evaluated[:n_top]

    candidates = []
    for rank, (score, network, result) in enumerate(top, start=1):
        try:
            features = _result_to_features(result, to_lnglat)
        except Exception:
            continue
        geojson = {
            "type": "FeatureCollection",
            "features": features,
        }
        candidates.append(LayoutCandidate(
            network=network,
            result=result,
            score=score,
            rank=rank,
            geojson=geojson,
        ))

    return candidates
