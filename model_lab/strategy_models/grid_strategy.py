"""Phase 2 grid subdivision strategy (research-only)."""

from __future__ import annotations

import math

from shapely.geometry import LineString

from bedrock.contracts.layout_result import LayoutResult
from bedrock.contracts.parcel import Parcel
from bedrock.contracts.zoning_rules import ZoningRules
from model_lab.strategy_models.layout_generation_utils import (
    build_layout_result,
    buildable_polygon,
    clip_lines_to_polygon,
    lots_from_grid,
    max_units_allowed,
    parcel_polygon,
)


def generate_layout(parcel: Parcel, zoning: ZoningRules) -> LayoutResult:
    poly = parcel_polygon(parcel)
    buildable = buildable_polygon(poly, zoning)
    max_units = max_units_allowed(parcel, zoning)
    min_lot = float(zoning.min_lot_size_sqft or 0.0)
    if buildable.is_empty or max_units <= 0 or min_lot <= 0.0:
        return build_layout_result(strategy_name="grid", parcel=parcel, lots=[], roads=[], buildable_area_sqft=0.0)

    minx, miny, maxx, maxy = buildable.bounds
    aspect = max((maxx - minx) / max(maxy - miny, 1.0), 0.2)
    cols = max(2, int(round(math.sqrt(max_units * aspect))))
    rows = max(2, int(math.ceil(max_units / max(cols, 1))))

    lots = lots_from_grid(
        buildable=buildable,
        min_lot_size_sqft=min_lot,
        max_units=max_units,
        cols=cols,
        rows=rows,
    )

    roads = []
    dx = (maxx - minx) / cols
    dy = (maxy - miny) / rows
    for ix in range(1, cols):
        x = minx + ix * dx
        roads.append(LineString([(x, miny), (x, maxy)]))
    for iy in range(1, rows):
        y = miny + iy * dy
        roads.append(LineString([(minx, y), (maxx, y)]))
    clipped_roads = clip_lines_to_polygon(roads, buildable)

    return build_layout_result(
        strategy_name="grid",
        parcel=parcel,
        lots=lots,
        roads=clipped_roads,
        buildable_area_sqft=float(buildable.area),
    )

