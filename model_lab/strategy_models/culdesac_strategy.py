"""Phase 2 cul-de-sac subdivision strategy (research-only)."""

from __future__ import annotations

import math

from shapely.geometry import LineString, Point

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
        return build_layout_result(strategy_name="cul-de-sac", parcel=parcel, lots=[], roads=[], buildable_area_sqft=0.0)

    minx, miny, maxx, maxy = buildable.bounds
    width = maxx - minx
    height = maxy - miny
    major_ns = height >= width

    cols = max(2, int(math.ceil(max_units / 2)))
    rows = 2
    lots = lots_from_grid(
        buildable=buildable,
        min_lot_size_sqft=min_lot,
        max_units=max_units,
        cols=cols if not major_ns else rows,
        rows=rows if not major_ns else cols,
    )

    if major_ns:
        x = (minx + maxx) / 2.0
        stem_top = miny + height * 0.70
        stem = LineString([(x, miny), (x, stem_top)])
        bulb_center = Point(x, stem_top)
        radius = min(width * 0.22, height * 0.14)
    else:
        y = (miny + maxy) / 2.0
        stem_top = minx + width * 0.70
        stem = LineString([(minx, y), (stem_top, y)])
        bulb_center = Point(stem_top, y)
        radius = min(height * 0.22, width * 0.14)

    bulb = bulb_center.buffer(radius).boundary
    roads = clip_lines_to_polygon([stem, bulb], buildable)

    return build_layout_result(
        strategy_name="cul-de-sac",
        parcel=parcel,
        lots=lots,
        roads=roads,
        buildable_area_sqft=float(buildable.area),
    )

