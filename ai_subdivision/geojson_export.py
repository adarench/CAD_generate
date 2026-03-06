from __future__ import annotations

import json
from typing import Any, Dict, List

from .subdivision import LayoutData


def layout_to_geojson(layout: LayoutData) -> Dict[str, Any]:
    features: List[Dict[str, Any]] = []
    for group_name, polygons in layout.polygon_groups().items():
        for index, polygon in enumerate(polygons, start=1):
            features.append(
                {
                    "type": "Feature",
                    "properties": {"layer": group_name, "id": f"{group_name}_{index}"},
                    "geometry": _polygon_geometry(polygon),
                }
            )
    for label in layout.lot_labels:
        features.append(
            {
                "type": "Feature",
                "properties": {"layer": "lot_labels", "text": label.text},
                "geometry": {"type": "Point", "coordinates": [label.position[0], label.position[1]]},
            }
        )
    return {"type": "FeatureCollection", "features": features}


def layout_to_geojson_bytes(layout: LayoutData) -> bytes:
    return (json.dumps(layout_to_geojson(layout), indent=2) + "\n").encode("utf-8")


def _polygon_geometry(polygon) -> Dict[str, Any]:
    coords = [[x, y] for x, y in polygon.closed_points()]
    return {"type": "Polygon", "coordinates": [coords]}
