"""
Shared deterministic helpers for Phase 2 layout strategy experiments.

This module is research-only and lives in model_lab.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, List

from shapely.geometry import LineString, MultiLineString, Polygon, box, mapping, shape

from bedrock.contracts.layout_result import LayoutResult
from bedrock.contracts.parcel import Parcel
from bedrock.contracts.zoning_rules import ZoningRules


ROAD_WIDTH_FT = 30.0


@dataclass(frozen=True)
class StrategyGeometry:
    lots: List[Polygon]
    roads: List[LineString]
    buildable_area_sqft: float


def parcel_polygon(parcel: Parcel) -> Polygon:
    geom = shape(parcel.geometry)
    if geom.geom_type == "MultiPolygon":
        geom = max(geom.geoms, key=lambda g: g.area)
    if geom.geom_type != "Polygon":
        raise ValueError(f"Unsupported parcel geometry type: {geom.geom_type}")
    return geom


def max_units_allowed(parcel: Parcel, zoning: ZoningRules) -> int:
    min_lot = float(zoning.min_lot_size_sqft or 0.0)
    density = float(zoning.max_units_per_acre or 0.0)
    if min_lot <= 0.0 or density <= 0.0:
        return 0
    by_lot_size = int(float(parcel.area_sqft) // min_lot)
    by_density = int((float(parcel.area_sqft) / 43560.0) * density)
    return max(0, min(by_lot_size, by_density))


def conservative_setback_ft(zoning: ZoningRules) -> float:
    setbacks = zoning.setbacks
    vals = [float(v) for v in (setbacks.front, setbacks.side, setbacks.rear) if v is not None]
    return max(vals) if vals else 0.0


def buildable_polygon(parcel_poly: Polygon, zoning: ZoningRules) -> Polygon:
    setback = conservative_setback_ft(zoning)
    if setback <= 0:
        return parcel_poly
    shrunk = parcel_poly.buffer(-setback)
    if shrunk.is_empty:
        return Polygon()
    if shrunk.geom_type == "MultiPolygon":
        return max(shrunk.geoms, key=lambda g: g.area)
    return shrunk


def _grid_cells(buildable: Polygon, cols: int, rows: int) -> Iterable[Polygon]:
    minx, miny, maxx, maxy = buildable.bounds
    if cols <= 0 or rows <= 0:
        return []
    dx = (maxx - minx) / cols
    dy = (maxy - miny) / rows
    cells: list[Polygon] = []
    for ix in range(cols):
        for iy in range(rows):
            cell = box(minx + ix * dx, miny + iy * dy, minx + (ix + 1) * dx, miny + (iy + 1) * dy)
            clipped = cell.intersection(buildable)
            if clipped.is_empty:
                continue
            if clipped.geom_type == "Polygon":
                cells.append(clipped)
            elif clipped.geom_type == "MultiPolygon":
                cells.extend(list(clipped.geoms))
    return cells


def lots_from_grid(
    buildable: Polygon,
    min_lot_size_sqft: float,
    max_units: int,
    cols: int,
    rows: int,
) -> List[Polygon]:
    if buildable.is_empty or max_units <= 0:
        return []
    candidates = [g for g in _grid_cells(buildable, cols=cols, rows=rows) if g.area >= min_lot_size_sqft]
    candidates = sorted(candidates, key=lambda g: (-g.area, g.centroid.x, g.centroid.y))
    return candidates[:max_units]


def clip_lines_to_polygon(lines: Iterable[LineString], polygon: Polygon) -> List[LineString]:
    clipped: list[LineString] = []
    for line in lines:
        inter = line.intersection(polygon)
        if inter.is_empty:
            continue
        if inter.geom_type == "LineString":
            clipped.append(inter)
        elif inter.geom_type == "MultiLineString":
            clipped.extend([seg for seg in inter.geoms if seg.length > 1.0])
    return clipped


def compactness_score(polys: Iterable[Polygon]) -> float:
    values = []
    for poly in polys:
        per = poly.length
        if per <= 0:
            continue
        values.append((4.0 * math.pi * float(poly.area)) / (per * per))
    if not values:
        return 0.0
    return max(0.0, min(1.0, sum(values) / len(values)))


def regularity_score(polys: Iterable[Polygon]) -> float:
    areas = [float(poly.area) for poly in polys if poly.area > 0]
    if not areas:
        return 0.0
    mean = sum(areas) / len(areas)
    if mean <= 0:
        return 0.0
    variance = sum((a - mean) ** 2 for a in areas) / len(areas)
    cv = math.sqrt(variance) / mean
    return max(0.0, min(1.0, 1.0 - cv))


def build_layout_result(
    *,
    strategy_name: str,
    parcel: Parcel,
    lots: List[Polygon],
    roads: List[LineString],
    score: float = 0.0,
    buildable_area_sqft: float | None = None,
) -> LayoutResult:
    road_length = float(sum(r.length for r in roads))
    return LayoutResult(
        layout_id=f"phase2-{strategy_name}-{parcel.parcel_id}",
        parcel_id=parcel.parcel_id,
        unit_count=len(lots),
        road_length_ft=road_length,
        lot_geometries=[dict(mapping(poly)) for poly in lots],
        road_geometries=[dict(mapping(road)) for road in roads],
        open_space_area_sqft=0.0,
        utility_length_ft=0.0,
        score=float(score),
        buildable_area_sqft=float(buildable_area_sqft) if buildable_area_sqft is not None else None,
    )

