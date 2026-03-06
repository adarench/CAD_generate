from __future__ import annotations

import json
from pathlib import Path


def load_parcel_boundary(path: str) -> list[tuple[float, float]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    geometry = _extract_geometry(payload)
    if geometry.get("type") != "Polygon":
        raise ValueError("Only GeoJSON Polygon parcels are supported in this prototype.")
    rings = geometry.get("coordinates", [])
    if not rings or len(rings[0]) < 4:
        raise ValueError("GeoJSON polygon must contain an exterior ring.")

    exterior = rings[0]
    points = [(float(x), float(y)) for x, y in exterior]
    if points[0] == points[-1]:
        points = points[:-1]
    return points


def _extract_geometry(payload: dict) -> dict:
    payload_type = payload.get("type")
    if payload_type == "FeatureCollection":
        features = payload.get("features", [])
        if not features:
            raise ValueError("GeoJSON FeatureCollection is empty.")
        return _extract_geometry(features[0])
    if payload_type == "Feature":
        geometry = payload.get("geometry")
        if not geometry:
            raise ValueError("GeoJSON Feature is missing geometry.")
        return geometry
    if payload_type == "Polygon":
        return payload
    raise ValueError(f"Unsupported GeoJSON type: {payload_type}")
