from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from shapely.geometry import LineString, Polygon, Point

from .geometry import RoadPlan, geometry_to_polygon_list, road_centerlines, road_geometry_from_centerlines


@dataclass(frozen=True)
class StreetNetworkCandidate:
    topology: str
    centerlines: List[LineString]
    corridors: List[Polygon]
    orientation: str
    metadata: Dict[str, float] = field(default_factory=dict)

    @property
    def road_length_ft(self) -> float:
        return float(sum(line.length for line in self.centerlines))


def generate_candidate_street_networks(
    parcel_polygon, road_width_ft: float, max_candidates: int = 72
) -> List[StreetNetworkCandidate]:
    candidates: List[StreetNetworkCandidate] = []
    candidates.extend(_generate_spine_layouts(parcel_polygon, road_width_ft))
    candidates.extend(_generate_parallel_layouts(parcel_polygon, road_width_ft))
    candidates.extend(_generate_loop_layouts(parcel_polygon, road_width_ft))
    candidates.extend(_generate_culdesac_layouts(parcel_polygon, road_width_ft))
    # slicing here causes loop/culdesac to drop if the other families already filled max_candidates,
    # so we should include more than enough non-parallel variants up front when necessary.
    # The original implementation heavily favored the first (parallel) families because the
    # list was sliced after concatenating spine/parallel before loops/culdesacs, so less
    # varied topologies never even made it into the optimizer. Trimming at the end still
    # keeps a balanced pool.
    return candidates[:max_candidates]


def street_network_from_road_plan(parcel_polygon, road_plan: RoadPlan, road_width_ft: float) -> StreetNetworkCandidate:
    centerlines = road_centerlines(parcel_polygon, road_plan)
    return _network_candidate(
        parcel_polygon=parcel_polygon,
        centerlines=centerlines,
        topology="collector",
        orientation=road_plan.orientation,
        road_width_ft=road_width_ft,
        metadata={
            "offset_ft": road_plan.offset_ft,
            "road_count": float(road_plan.road_count),
            "spacing_ft": road_plan.spacing_ft,
        },
    )


def _generate_spine_layouts(parcel_polygon, road_width_ft: float) -> List[StreetNetworkCandidate]:
    networks: List[StreetNetworkCandidate] = []
    side_offsets = [-160.0, -90.0, 90.0, 160.0]
    for orientation in ("north_south", "east_west"):
        for offset in (-120.0, -60.0, 0.0, 60.0, 120.0):
            plan = RoadPlan(orientation=orientation, offset_ft=offset, road_count=1)
            collector = road_centerlines(parcel_polygon, plan)[0]
            branches = _perpendicular_branches(parcel_polygon, collector, orientation, side_offsets)
            centerlines = [collector, *branches]
            networks.append(
                _network_candidate(
                    parcel_polygon=parcel_polygon,
                    centerlines=centerlines,
                    topology="spine",
                    orientation=orientation,
                    road_width_ft=road_width_ft,
                    metadata={"offset_ft": offset},
                )
            )
    return networks


def _generate_parallel_layouts(parcel_polygon, road_width_ft: float) -> List[StreetNetworkCandidate]:
    networks: List[StreetNetworkCandidate] = []
    for orientation in ("north_south", "east_west"):
        for offset in (-120.0, -40.0, 40.0, 120.0):
            for road_count, spacing in ((2, 220.0), (2, 300.0), (3, 240.0)):
                centerlines = _parallel_centerlines(
                    parcel_polygon,
                    orientation=orientation,
                    offset_ft=offset,
                    road_count=road_count,
                    spacing_ft=spacing,
                )
                networks.append(
                    _network_candidate(
                        parcel_polygon=parcel_polygon,
                        centerlines=centerlines,
                        topology="parallel",
                        orientation=orientation,
                        road_width_ft=road_width_ft,
                        metadata={
                            "offset_ft": offset,
                            "road_count": float(road_count),
                            "spacing_ft": spacing,
                        },
                    )
                )
    return networks


def _generate_loop_layouts(parcel_polygon, road_width_ft: float) -> List[StreetNetworkCandidate]:
    networks: List[StreetNetworkCandidate] = []
    min_x, min_y, max_x, max_y = parcel_polygon.bounds
    centroid = parcel_polygon.centroid
    widths = [0.35, 0.45, 0.55]
    heights = [0.35, 0.5]
    for orientation in ("north_south", "east_west"):
        for width_ratio in widths:
            for height_ratio in heights:
                loop = _rectangular_loop(parcel_polygon, width_ratio, height_ratio)
                if orientation == "north_south":
                    connector = LineString([(centroid.x, min_y - 80.0), (centroid.x, loop.centroid.y)])
                else:
                    connector = LineString([(min_x - 80.0, centroid.y), (loop.centroid.x, centroid.y)])
                centerlines = [loop.intersection(parcel_polygon), connector.intersection(parcel_polygon)]
                networks.append(
                    _network_candidate(
                        parcel_polygon=parcel_polygon,
                        centerlines=centerlines,
                        topology="loop",
                        orientation=orientation,
                        road_width_ft=road_width_ft,
                        metadata={
                            "loop_width_ratio": width_ratio,
                            "loop_height_ratio": height_ratio,
                        },
                    )
                )
    return networks


def _generate_culdesac_layouts(parcel_polygon, road_width_ft: float) -> List[StreetNetworkCandidate]:
    networks: List[StreetNetworkCandidate] = []
    depths = [180.0, 240.0, 300.0]
    radii = [55.0, 70.0]
    offsets = [-100.0, 0.0, 100.0]
    for orientation in ("north_south", "east_west"):
        for offset in offsets:
            for depth in depths:
                for radius in radii:
                    centerlines = _culdesac_centerlines(
                        parcel_polygon,
                        orientation=orientation,
                        offset_ft=offset,
                        depth_ft=depth,
                        radius_ft=radius,
                    )
                    networks.append(
                        _network_candidate(
                            parcel_polygon=parcel_polygon,
                            centerlines=centerlines,
                            topology="culdesac",
                            orientation=orientation,
                            road_width_ft=road_width_ft,
                            metadata={
                                "offset_ft": offset,
                                "depth_ft": depth,
                                "radius_ft": radius,
                            },
                        )
                    )
    return networks


def _parallel_centerlines(parcel_polygon, orientation: str, offset_ft: float, road_count: int, spacing_ft: float) -> List[LineString]:
    plan = RoadPlan(
        orientation=orientation,
        offset_ft=offset_ft,
        road_count=1,
        spacing_ft=spacing_ft,
    )
    base = road_centerlines(parcel_polygon, plan)[0]
    if road_count == 1:
        return [base]
    shifts = (
        [-spacing_ft / 2.0, spacing_ft / 2.0]
        if road_count == 2
        else [-spacing_ft, 0.0, spacing_ft]
    )
    return [
        road_centerlines(parcel_polygon, RoadPlan(orientation=orientation, offset_ft=offset_ft + shift))[0]
        for shift in shifts
    ]


def _perpendicular_branches(parcel_polygon, collector: LineString, orientation: str, offsets: List[float]) -> List[LineString]:
    min_x, min_y, max_x, max_y = parcel_polygon.bounds
    centroid = parcel_polygon.centroid
    branches = []
    if orientation == "north_south":
        for offset in offsets:
            y = centroid.y + offset
            branch = LineString([(min_x - 60.0, y), (max_x + 60.0, y)]).intersection(parcel_polygon.buffer(80.0))
            if branch.length > 40.0:
                branches.append(branch)
    else:
        for offset in offsets:
            x = centroid.x + offset
            branch = LineString([(x, min_y - 60.0), (x, max_y + 60.0)]).intersection(parcel_polygon.buffer(80.0))
            if branch.length > 40.0:
                branches.append(branch)
    return branches


def _rectangular_loop(parcel_polygon, width_ratio: float, height_ratio: float) -> LineString:
    min_x, min_y, max_x, max_y = parcel_polygon.bounds
    centroid = parcel_polygon.centroid
    width = (max_x - min_x) * width_ratio
    height = (max_y - min_y) * height_ratio
    half_w = width / 2.0
    half_h = height / 2.0
    return LineString(
        [
            (centroid.x - half_w, centroid.y - half_h),
            (centroid.x + half_w, centroid.y - half_h),
            (centroid.x + half_w, centroid.y + half_h),
            (centroid.x - half_w, centroid.y + half_h),
            (centroid.x - half_w, centroid.y - half_h),
        ]
    )


def _culdesac_centerlines(parcel_polygon, orientation: str, offset_ft: float, depth_ft: float, radius_ft: float) -> List[LineString]:
    min_x, min_y, max_x, max_y = parcel_polygon.bounds
    centroid = parcel_polygon.centroid
    if orientation == "north_south":
        x = centroid.x + offset_ft
        stem = LineString([(x, min_y - 80.0), (x, min_y + depth_ft)])
        bulb_center = Point(x, min_y + depth_ft)
    else:
        y = centroid.y + offset_ft
        stem = LineString([(min_x - 80.0, y), (min_x + depth_ft, y)])
        bulb_center = Point(min_x + depth_ft, y)
    bulb = bulb_center.buffer(radius_ft).boundary
    return [stem.intersection(parcel_polygon), bulb.intersection(parcel_polygon)]


def _network_candidate(parcel_polygon, centerlines: List[LineString], topology: str, orientation: str, road_width_ft: float, metadata: Dict[str, float]) -> StreetNetworkCandidate:
    centerlines = [line for line in centerlines if not line.is_empty]
    corridors = geometry_to_polygon_list(
        road_geometry_from_centerlines(parcel_polygon, centerlines, road_width_ft)
    )
    return StreetNetworkCandidate(
        centerlines=centerlines,
        corridors=corridors,
        topology=topology,
        orientation=orientation,
        metadata=metadata,
    )
