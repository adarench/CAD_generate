from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from shapely.geometry import Polygon, mapping, shape


FEET_PER_DEGREE_LAT = 364000.0


@dataclass(frozen=True)
class ParcelProjection:
    origin_lng: float
    origin_lat: float
    feet_per_degree_lng: float
    feet_per_degree_lat: float = FEET_PER_DEGREE_LAT


@dataclass(frozen=True)
class AdaptedParcel:
    parcel_polygon: Polygon
    projection: ParcelProjection


def adapt_parcel_geometry(geometry_geojson: dict[str, Any]) -> AdaptedParcel:
    geom = shape(geometry_geojson)
    if geom.geom_type == "MultiPolygon":
        geom = max(geom.geoms, key=lambda item: item.area)
    if geom.geom_type != "Polygon":
      raise ValueError("Only Polygon and MultiPolygon parcels are supported.")

    centroid = geom.centroid
    feet_per_degree_lng = FEET_PER_DEGREE_LAT * math.cos(math.radians(centroid.y))
    projection = ParcelProjection(
        origin_lng=centroid.x,
        origin_lat=centroid.y,
        feet_per_degree_lng=max(feet_per_degree_lng, 1.0),
    )
    local = Polygon([to_local_feet(point[0], point[1], projection) for point in geom.exterior.coords])
    return AdaptedParcel(parcel_polygon=local, projection=projection)


def geometry_area_sqft(geometry_geojson: dict[str, Any]) -> float:
    adapted = adapt_parcel_geometry(geometry_geojson)
    return float(adapted.parcel_polygon.area)


def to_local_feet(lng: float, lat: float, projection: ParcelProjection) -> tuple[float, float]:
    return (
        (lng - projection.origin_lng) * projection.feet_per_degree_lng,
        (lat - projection.origin_lat) * projection.feet_per_degree_lat,
    )


def to_lnglat(x_ft: float, y_ft: float, projection: ParcelProjection) -> tuple[float, float]:
    return (
        projection.origin_lng + (x_ft / projection.feet_per_degree_lng),
        projection.origin_lat + (y_ft / projection.feet_per_degree_lat),
    )


def polygon2d_to_geojson(polygon, projection: ParcelProjection) -> dict[str, Any]:
    coords = [to_lnglat(x, y, projection) for x, y in polygon.closed_points()]
    return {"type": "Polygon", "coordinates": [[list(point) for point in coords]]}


def lot_label_to_geojson(label, projection: ParcelProjection) -> dict[str, Any]:
    lng, lat = to_lnglat(label.position[0], label.position[1], projection)
    return {"type": "Point", "coordinates": [lng, lat]}


def parcel_geometry_geojson(parcel_polygon: Polygon, projection: ParcelProjection) -> dict[str, Any]:
    lng_lat_coords = [to_lnglat(x, y, projection) for x, y in parcel_polygon.exterior.coords]
    return mapping(Polygon(lng_lat_coords))
