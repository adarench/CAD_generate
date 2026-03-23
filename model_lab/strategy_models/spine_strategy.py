"""Phase 2 spine-road subdivision strategy (research-only)."""

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
        return build_layout_result(strategy_name="spine-road", parcel=parcel, lots=[], roads=[], buildable_area_sqft=0.0)

    minx, miny, maxx, maxy = buildable.bounds
    width = maxx - minx
    height = maxy - miny
    major_ns = height >= width

    rows = max(2, int(math.ceil(max_units / 2)))
    cols = 2
    lots = lots_from_grid(
        buildable=buildable,
        min_lot_size_sqft=min_lot,
        max_units=max_units,
        cols=cols if major_ns else rows,
        rows=rows if major_ns else cols,
    )

    roads = []
    if major_ns:
        x_mid = (minx + maxx) / 2.0
        roads.append(LineString([(x_mid, miny), (x_mid, maxy)]))
        branch_count = max(2, min(8, rows // 2))
        spacing = height / (branch_count + 1)
        branch_len = width * 0.34
        for idx in range(1, branch_count + 1):
            y = miny + idx * spacing
            roads.append(LineString([(x_mid - branch_len, y), (x_mid + branch_len, y)]))
    else:
        y_mid = (miny + maxy) / 2.0
        roads.append(LineString([(minx, y_mid), (maxx, y_mid)]))
        branch_count = max(2, min(8, rows // 2))
        spacing = width / (branch_count + 1)
        branch_len = height * 0.34
        for idx in range(1, branch_count + 1):
            x = minx + idx * spacing
            roads.append(LineString([(x, y_mid - branch_len), (x, y_mid + branch_len)]))

    clipped_roads = clip_lines_to_polygon(roads, buildable)
    return build_layout_result(
        strategy_name="spine-road",
        parcel=parcel,
        lots=lots,
        roads=clipped_roads,
        buildable_area_sqft=float(buildable.area),
    )

