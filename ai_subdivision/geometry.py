from __future__ import annotations

from dataclasses import dataclass
from math import floor, sqrt
from typing import Iterable, List, Tuple

import numpy as np

from .constraints import SubdivisionConstraints
from .zoning import ZoningRules

try:
    from shapely.geometry import (
        GeometryCollection,
        LineString,
        MultiLineString,
        Point as ShapelyPoint,
        Polygon as ShapelyPolygon,
    )
    from shapely.ops import linemerge, substring, unary_union
except ImportError:  # pragma: no cover - optional dependency
    GeometryCollection = None
    LineString = None
    MultiLineString = None
    ShapelyPoint = None
    ShapelyPolygon = None
    linemerge = None
    substring = None
    unary_union = None

try:
    import cadquery as cq
except ImportError:  # pragma: no cover - optional dependency
    cq = None


Point = Tuple[float, float]


@dataclass(frozen=True)
class Polygon2D:
    points: Tuple[Point, ...]

    def closed_points(self) -> List[Point]:
        pts = list(self.points)
        if pts and pts[0] != pts[-1]:
            pts.append(pts[0])
        return pts

    def as_shapely(self):
        if ShapelyPolygon is None:
            return None
        return ShapelyPolygon(self.points)

    def label_point(self) -> Point:
        polygon = self.as_shapely()
        if polygon is None:
            xs = [point[0] for point in self.points]
            ys = [point[1] for point in self.points]
            return (sum(xs) / len(xs), sum(ys) / len(ys))
        point = polygon.representative_point()
        return (float(point.x), float(point.y))


@dataclass(frozen=True)
class Rect:
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y

    def to_polygon(self) -> Polygon2D:
        return Polygon2D(
            (
                (self.min_x, self.min_y),
                (self.max_x, self.min_y),
                (self.max_x, self.max_y),
                (self.min_x, self.max_y),
            )
        )


@dataclass(frozen=True)
class RoadPlan:
    orientation: str
    offset_ft: float = 0.0
    road_count: int = 1
    spacing_ft: float = 300.0


def default_road_plan(constraints: SubdivisionConstraints) -> RoadPlan:
    return RoadPlan(orientation=constraints.road.orientation)


def create_parcel_polygon(constraints: SubdivisionConstraints) -> Polygon2D:
    return polygon_to_polygon2d(parcel_shapely_from_constraints(constraints))


def parcel_rect_from_constraints(constraints: SubdivisionConstraints) -> Rect:
    area_sqft = constraints.parcel.area_acres * 43560.0
    aspect = constraints.parcel.aspect_ratio
    width = sqrt(area_sqft * aspect)
    height = area_sqft / width
    half_width = width / 2.0
    half_height = height / 2.0
    return Rect(-half_width, -half_height, half_width, half_height)


def parcel_shapely_from_constraints(constraints: SubdivisionConstraints):
    if ShapelyPolygon is None:
        raise RuntimeError("shapely is required for parcel and frontage operations.")

    if constraints.parcel.shape == "polygon" and constraints.parcel.boundary:
        polygon = ShapelyPolygon(constraints.parcel.boundary)
    else:
        polygon = ShapelyPolygon(parcel_rect_from_constraints(constraints).to_polygon().points)
    return _clean_polygon(polygon)


def create_road_polygons(parcel_polygon, road_plan: RoadPlan, width_ft: float) -> List[Polygon2D]:
    return create_road_polygons_from_centerlines(
        parcel_polygon=parcel_polygon,
        centerlines=road_centerlines(parcel_polygon, road_plan),
        width_ft=width_ft,
    )


def create_road_geometry(parcel_polygon, road_plan: RoadPlan, width_ft: float):
    return road_geometry_from_centerlines(
        parcel_polygon=parcel_polygon,
        centerlines=road_centerlines(parcel_polygon, road_plan),
        width_ft=width_ft,
    )


def create_easement_buffers(
    parcel_polygon, road_plan: RoadPlan, road_width_ft: float, easement_width_ft: float
) -> List[Polygon2D]:
    return create_easement_buffers_from_centerlines(
        parcel_polygon=parcel_polygon,
        centerlines=road_centerlines(parcel_polygon, road_plan),
        road_width_ft=road_width_ft,
        easement_width_ft=easement_width_ft,
    )


def create_easement_geometries(
    parcel_polygon, road_plan: RoadPlan, road_width_ft: float, easement_width_ft: float
):
    return easement_geometries_from_centerlines(
        parcel_polygon=parcel_polygon,
        centerlines=road_centerlines(parcel_polygon, road_plan),
        road_width_ft=road_width_ft,
        easement_width_ft=easement_width_ft,
    )


def create_road_polygons_from_centerlines(
    parcel_polygon, centerlines: List, width_ft: float
) -> List[Polygon2D]:
    road_geometry = road_geometry_from_centerlines(parcel_polygon, centerlines, width_ft)
    return [polygon_to_polygon2d(polygon) for polygon in geometry_to_polygon_list(road_geometry)]


def road_geometry_from_centerlines(parcel_polygon, centerlines: List, width_ft: float):
    road_pieces = [
        centerline.buffer(width_ft / 2.0, cap_style=2, join_style=2)
        for centerline in centerlines
    ]
    return _clean_polygon(unary_union(road_pieces).intersection(parcel_polygon))


def create_easement_buffers_from_centerlines(
    parcel_polygon, centerlines: List, road_width_ft: float, easement_width_ft: float
) -> List[Polygon2D]:
    return [
        polygon_to_polygon2d(geom)
        for geom in easement_geometries_from_centerlines(
            parcel_polygon=parcel_polygon,
            centerlines=centerlines,
            road_width_ft=road_width_ft,
            easement_width_ft=easement_width_ft,
        )
    ]


def easement_geometries_from_centerlines(
    parcel_polygon, centerlines: List, road_width_ft: float, easement_width_ft: float
):
    if easement_width_ft <= 0:
        return []

    bands = []
    for centerline in centerlines:
        inner = centerline.buffer(road_width_ft / 2.0, cap_style=2, join_style=2)
        outer = centerline.buffer(
            road_width_ft / 2.0 + easement_width_ft, cap_style=2, join_style=2
        )
        bands.append(outer.difference(inner))
    easement_band = unary_union(bands).intersection(parcel_polygon)
    return geometry_to_polygon_list(easement_band, min_area=5.0)


def compute_developable_polygon(parcel_polygon, road_polygon):
    return _clean_polygon(parcel_polygon.difference(road_polygon))


def get_frontage_edges(developable_polygon, road_polygon) -> List:
    shared = developable_polygon.boundary.intersection(road_polygon.boundary)
    return _extract_line_strings(shared)


def segment_frontage_edges(
    frontage_edges: List, target_count: int, min_frontage_ft: float
) -> List:
    capacities = [max(0, int(floor(edge.length / min_frontage_ft))) for edge in frontage_edges]
    total_capacity = sum(capacities)
    if total_capacity == 0:
        return []

    desired = min(target_count, total_capacity)
    lengths = np.array([edge.length for edge in frontage_edges], dtype=float)
    raw = desired * lengths / lengths.sum()
    counts = [min(cap, int(np.floor(value))) for cap, value in zip(capacities, raw)]
    assigned = sum(counts)

    for index, capacity in enumerate(capacities):
        if assigned >= desired:
            break
        if counts[index] == 0 and capacity > 0:
            counts[index] = 1
            assigned += 1

    while assigned < desired:
        fractions = []
        for index, (value, count, capacity) in enumerate(zip(raw, counts, capacities)):
            if count >= capacity:
                fractions.append((-1.0, index))
            else:
                fractions.append((value - count, index))
        _, pick = max(fractions)
        if counts[pick] >= capacities[pick]:
            break
        counts[pick] += 1
        assigned += 1

    while assigned > desired:
        for index, count in enumerate(counts):
            if count > 1:
                counts[index] -= 1
                assigned -= 1
                if assigned == desired:
                    break

    segments: List = []
    for edge, count in zip(frontage_edges, counts):
        if count <= 0:
            continue
        segment_length = edge.length / count
        for index in range(count):
            start = index * segment_length
            end = edge.length if index == count - 1 else (index + 1) * segment_length
            segment = substring(edge, start, end)
            if segment.geom_type == "LineString" and segment.length >= min_frontage_ft * 0.95:
                segments.append(segment)
    return segments


def generate_frontage_lots(
    developable_polygon, road_polygon, target_count: int, zoning_rules: ZoningRules
) -> List[Polygon2D]:
    frontage_edges = get_frontage_edges(developable_polygon, road_polygon)
    frontage_segments = segment_frontage_edges(
        frontage_edges=frontage_edges,
        target_count=target_count,
        min_frontage_ft=zoning_rules.min_frontage_ft,
    )
    accepted: List = []
    used_area = None
    for segment in frontage_segments:
        if used_area is None:
            available_land = developable_polygon
        else:
            remaining = developable_polygon.difference(used_area)
            if remaining.is_empty:
                break
            available_land = _clean_polygon(remaining)
        candidate = _lot_from_frontage_segment(
            frontage_segment=segment,
            available_land=available_land,
            min_depth_ft=zoning_rules.min_depth_ft,
        )
        if candidate is None:
            continue
        if not _lot_meets_rules(candidate, road_polygon, zoning_rules):
            continue
        accepted.append(candidate)
        used_area = candidate if used_area is None else unary_union([used_area, candidate])
        if len(accepted) >= target_count:
            break
    return [polygon_to_polygon2d(polygon) for polygon in accepted]


def estimate_max_target_lots(parcel_polygon, zoning_rules: ZoningRules) -> int:
    area_based = int(parcel_polygon.area / zoning_rules.min_area_sqft) + 8
    return max(area_based, 24)


def layout_metadata(constraints: SubdivisionConstraints) -> dict[str, float]:
    parcel_polygon = parcel_shapely_from_constraints(constraints)
    min_x, min_y, max_x, max_y = parcel_polygon.bounds
    return {
        "parcel_width_ft": round(max_x - min_x, 2),
        "parcel_height_ft": round(max_y - min_y, 2),
        "parcel_area_sqft": round(parcel_polygon.area, 2),
    }


def road_centerlines(parcel_polygon, road_plan: RoadPlan) -> List:
    min_x, min_y, max_x, max_y = parcel_polygon.bounds
    centroid = parcel_polygon.centroid
    pad = max(max_x - min_x, max_y - min_y) * 0.25 + 50.0
    offsets = _road_offsets(road_plan)

    centerlines = []
    for offset in offsets:
        if road_plan.orientation == "north_south":
            x = centroid.x + road_plan.offset_ft + offset
            centerlines.append(LineString([(x, min_y - pad), (x, max_y + pad)]))
        else:
            y = centroid.y + road_plan.offset_ft + offset
            centerlines.append(LineString([(min_x - pad, y), (max_x + pad, y)]))
    return centerlines


def export_layout_to_cadquery_step(layout, path: str) -> str:
    if cq is None:
        raise RuntimeError("cadquery is not installed.")

    assembly = cq.Assembly(name="site_layout")
    for group_name, polygons in layout.polygon_groups().items():
        thickness = 1.0 if group_name != "road" else 2.0
        for index, polygon in enumerate(polygons):
            solid = _polygon_to_solid(polygon, thickness=thickness)
            assembly.add(solid, name=f"{group_name}_{index}")

    assembly.save(path)
    return path


def polygon_to_polygon2d(polygon) -> Polygon2D:
    pts = tuple((float(x), float(y)) for x, y in list(polygon.exterior.coords)[:-1])
    return Polygon2D(pts)


def geometry_to_polygon_list(geometry, min_area: float = 1.0) -> List:
    if geometry.is_empty:
        return []
    if geometry.geom_type == "Polygon":
        cleaned = _clean_polygon(geometry)
        return [cleaned] if cleaned.area >= min_area else []
    if geometry.geom_type == "MultiPolygon":
        polygons: List = []
        for polygon in geometry.geoms:
            polygons.extend(geometry_to_polygon_list(polygon, min_area=min_area))
        return sorted(polygons, key=lambda poly: poly.area, reverse=True)
    if geometry.geom_type == "GeometryCollection":
        polygons: List = []
        for part in geometry.geoms:
            polygons.extend(geometry_to_polygon_list(part, min_area=min_area))
        return sorted(polygons, key=lambda poly: poly.area, reverse=True)
    return []


def _road_offsets(road_plan: RoadPlan) -> List[float]:
    if road_plan.road_count <= 1:
        return [0.0]
    half_spacing = road_plan.spacing_ft / 2.0
    return [-half_spacing, half_spacing]


def _extract_line_strings(geometry) -> List:
    if geometry.is_empty:
        return []
    if geometry.geom_type == "LineString":
        return [geometry]
    if geometry.geom_type == "MultiLineString":
        return [line for line in geometry.geoms if line.length > 1.0]
    if geometry.geom_type == "GeometryCollection":
        lines: List = []
        for part in geometry.geoms:
            lines.extend(_extract_line_strings(part))
        if not lines:
            return []
        merged = linemerge(lines)
        if merged.geom_type == "LineString":
            return [merged]
        return [line for line in merged.geoms if line.length > 1.0]
    return []


def _lot_from_frontage_segment(frontage_segment, available_land, min_depth_ft: float):
    start = frontage_segment.coords[0]
    end = frontage_segment.coords[-1]
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = sqrt(dx * dx + dy * dy)
    if length <= 1e-6:
        return None

    normals = [(-dy / length, dx / length), (dy / length, -dx / length)]
    midpoint = frontage_segment.interpolate(0.5, normalized=True)
    normal = _pick_inward_normal(midpoint, normals, available_land)
    if normal is None:
        return None

    x0, y0 = start
    x1, y1 = end
    nx, ny = normal
    template = ShapelyPolygon(
        [
            (x0, y0),
            (x1, y1),
            (x1 + nx * min_depth_ft, y1 + ny * min_depth_ft),
            (x0 + nx * min_depth_ft, y0 + ny * min_depth_ft),
        ]
    )
    clipped = template.intersection(available_land)
    polygons = geometry_to_polygon_list(clipped, min_area=1.0)
    if not polygons:
        return None
    return max(polygons, key=lambda polygon: polygon.area)


def _pick_inward_normal(midpoint, normals: List[Point], available_land):
    for nx, ny in normals:
        probe = ShapelyPoint(midpoint.x + nx * 2.0, midpoint.y + ny * 2.0)
        if available_land.buffer(0.5).covers(probe):
            return (nx, ny)
    return None


def _lot_meets_rules(lot_polygon, road_polygon, zoning_rules: ZoningRules) -> bool:
    if lot_polygon.area < zoning_rules.min_area_sqft:
        return False
    frontage_length = lot_polygon.boundary.intersection(road_polygon.boundary).length
    if frontage_length < zoning_rules.min_frontage_ft * 0.95:
        return False
    depth = _effective_depth(lot_polygon, road_polygon)
    if depth < zoning_rules.min_depth_ft * 0.95:
        return False
    return True


def _effective_depth(lot_polygon, road_polygon) -> float:
    frontage = lot_polygon.boundary.intersection(road_polygon.boundary)
    frontage_lines = _extract_line_strings(frontage)
    if not frontage_lines:
        return 0.0
    frontage_line = max(frontage_lines, key=lambda line: line.length)
    start = frontage_line.coords[0]
    end = frontage_line.coords[-1]
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = sqrt(dx * dx + dy * dy)
    if length <= 1e-6:
        return 0.0
    normal = (-dy / length, dx / length)
    midpoint = frontage_line.interpolate(0.5, normalized=True)
    probe_a = ShapelyPoint(midpoint.x + normal[0] * 2.0, midpoint.y + normal[1] * 2.0)
    if not lot_polygon.buffer(0.5).covers(probe_a):
        normal = (dy / length, -dx / length)
    projections = [
        point[0] * normal[0] + point[1] * normal[1]
        for point in lot_polygon.exterior.coords
    ]
    return max(projections) - min(projections)


def _clean_polygon(geometry):
    cleaned = geometry.buffer(0)
    if cleaned.is_empty:
        raise ValueError("Generated geometry is empty.")
    return cleaned


def _polygon_to_solid(polygon: Polygon2D, thickness: float):
    if cq is None:
        raise RuntimeError("cadquery is not installed.")

    pts = _sanitize_ring_points(polygon.closed_points()[:-1])
    if len(pts) < 3:
        raise ValueError("Polygon must contain at least 3 unique points for STEP export.")
    return cq.Workplane("XY").polyline(pts).close().extrude(thickness)


def _sanitize_ring_points(points: List[Point]) -> List[Point]:
    sanitized: List[Point] = []
    for point in points:
        if not sanitized or _point_distance(point, sanitized[-1]) > 1e-6:
            sanitized.append(point)
    if len(sanitized) > 1 and _point_distance(sanitized[0], sanitized[-1]) <= 1e-6:
        sanitized.pop()
    return sanitized


def _point_distance(a: Point, b: Point) -> float:
    return sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)
