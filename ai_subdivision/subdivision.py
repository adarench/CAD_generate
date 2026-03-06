from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from .constraints import SubdivisionConstraints
from .geometry import (
    Polygon2D,
    RoadPlan,
    compute_developable_polygon,
    create_easement_buffers,
    create_easement_buffers_from_centerlines,
    create_road_geometry,
    create_road_polygons,
    create_road_polygons_from_centerlines,
    default_road_plan,
    estimate_max_target_lots,
    generate_frontage_lots,
    layout_metadata,
    parcel_shapely_from_constraints,
    road_centerlines,
    road_geometry_from_centerlines,
)
from .street_network import StreetNetworkCandidate, street_network_from_road_plan
from .zoning import ZoningRules


@dataclass(frozen=True)
class LotLabel:
    text: str
    position: Tuple[float, float]


@dataclass(frozen=True)
class LayoutData:
    parcel: List[Polygon2D]
    road: List[Polygon2D]
    lots: List[Polygon2D]
    easements: List[Polygon2D]
    lot_labels: List[LotLabel]
    road_plan: RoadPlan
    street_network: StreetNetworkCandidate
    optimized: bool = False

    def polygon_groups(self) -> Dict[str, List[Polygon2D]]:
        return {
            "parcel": self.parcel,
            "road": self.road,
            "lots": self.lots,
            "easements": self.easements,
        }


def generate_subdivision(
    constraints: SubdivisionConstraints,
    zoning_rules: ZoningRules,
    road_plan: RoadPlan | None = None,
    street_network: StreetNetwork | None = None,
    target_lot_count: int | None = None,
    optimized: bool = False,
) -> LayoutData:
    if street_network is not None and road_plan is None:
        active_road_plan = RoadPlan(
            orientation=street_network.orientation,
            offset_ft=float(street_network.metadata.get("offset_ft", 0.0)),
            road_count=len(street_network.centerlines),
            spacing_ft=float(street_network.metadata.get("spacing_ft", 300.0)),
        )
    else:
        active_road_plan = road_plan or default_road_plan(constraints)
    parcel_polygon = parcel_shapely_from_constraints(constraints)
    active_network = street_network or street_network_from_road_plan(
        parcel_polygon=parcel_polygon,
        road_plan=active_road_plan,
        road_width_ft=constraints.road.width_ft,
    )
    road_geometry = road_geometry_from_centerlines(
        parcel_polygon=parcel_polygon,
        centerlines=active_network.centerlines,
        width_ft=constraints.road.width_ft,
    )
    developable_polygon = compute_developable_polygon(parcel_polygon, road_geometry)

    lot_target = (
        target_lot_count
        if target_lot_count is not None
        else constraints.lots.count
    )
    lot_geometries = generate_frontage_lots(
        developable_polygon=developable_polygon,
        road_polygon=road_geometry,
        target_count=lot_target,
        zoning_rules=zoning_rules,
    )

    parcel = [Polygon2D(tuple(point for point in parcel_polygon.exterior.coords[:-1]))]
    road = create_road_polygons_from_centerlines(
        parcel_polygon=parcel_polygon,
        centerlines=active_network.centerlines,
        width_ft=constraints.road.width_ft,
    )
    easements = create_easement_buffers_from_centerlines(
        parcel_polygon=parcel_polygon,
        centerlines=active_network.centerlines,
        road_width_ft=constraints.road.width_ft,
        easement_width_ft=constraints.easement.width_ft,
    )
    lot_labels = [
        LotLabel(text=f"LOT_{index}", position=polygon.label_point())
        for index, polygon in enumerate(lot_geometries, start=1)
    ]

    return LayoutData(
        parcel=parcel,
        road=road,
        lots=lot_geometries,
        easements=easements,
        lot_labels=lot_labels,
        road_plan=active_road_plan,
        street_network=active_network,
        optimized=optimized,
    )


def generate_optimization_target(
    constraints: SubdivisionConstraints, zoning_rules: ZoningRules
) -> int:
    parcel_polygon = parcel_shapely_from_constraints(constraints)
    return estimate_max_target_lots(parcel_polygon, zoning_rules)


def summarize_layout(
    constraints: SubdivisionConstraints, zoning_rules: ZoningRules, layout: LayoutData
) -> Dict[str, float]:
    summary = layout_metadata(constraints)
    parcel_area = layout.parcel[0].as_shapely().area if layout.parcel else 0.0
    road_area = sum(polygon.as_shapely().area for polygon in layout.road)
    summary["requested_lot_count"] = constraints.lots.count
    summary["generated_lot_count"] = len(layout.lots)
    summary["road_width_ft"] = constraints.road.width_ft
    summary["easement_width_ft"] = constraints.easement.width_ft
    summary["min_frontage_ft"] = zoning_rules.min_frontage_ft
    summary["min_depth_ft"] = zoning_rules.min_depth_ft
    summary["min_area_sqft"] = zoning_rules.min_area_sqft
    summary["road_offset_ft"] = layout.road_plan.offset_ft
    summary["road_count"] = layout.road_plan.road_count
    summary["road_length_ft"] = round(layout.street_network.road_length_ft, 2)
    summary["network_type"] = layout.street_network.topology
    summary["developable_area_sqft"] = round(parcel_area - road_area, 2)
    summary["average_lot_area_sqft"] = round(
        sum(polygon.as_shapely().area for polygon in layout.lots) / max(1, len(layout.lots)),
        2,
    )
    return summary
