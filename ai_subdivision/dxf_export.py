from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Tuple

from .geometry import Polygon2D
from .subdivision import LayoutData, LotLabel

try:
    import ezdxf
except ImportError:  # pragma: no cover - optional dependency
    ezdxf = None


LAYER_MAP = {
    "parcel": "PARCEL",
    "road": "ROAD",
    "optimized_road": "OPT_ROAD",
    "lots": "LOT_LINES",
    "easements": "EASEMENTS",
    "lot_labels": "LOT_LABELS",
}

LAYER_COLORS = {
    "PARCEL": 7,
    "ROAD": 1,
    "OPT_ROAD": 6,
    "LOT_LINES": 3,
    "EASEMENTS": 5,
    "LOT_LABELS": 2,
}


def export_dxf(layout: LayoutData, output_path: str = "subdivision_layout.dxf") -> str:
    if ezdxf is not None:
        return _export_with_ezdxf(layout, output_path)
    return _export_ascii_dxf(layout, output_path)


def _export_with_ezdxf(layout: LayoutData, output_path: str) -> str:
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    for layer in LAYER_COLORS:
        if layer not in doc.layers:
            doc.layers.add(name=layer, color=LAYER_COLORS[layer])

    for group_name, polygons in layout.polygon_groups().items():
        layer = _layer_for_group(layout, group_name)
        for polygon in polygons:
            coords = [(x, y) for x, y in polygon.points]
            msp.add_lwpolyline(coords, close=True, dxfattribs={"layer": layer})
    _add_labels_ezdxf(msp, layout.lot_labels)

    doc.saveas(output_path)
    return output_path


def _export_ascii_dxf(layout: LayoutData, output_path: str) -> str:
    lines: List[str] = []
    lines.extend(_dxf_header())
    lines.extend(_dxf_layers())
    lines.extend(["0", "SECTION", "2", "ENTITIES"])

    for group_name, polygons in layout.polygon_groups().items():
        layer = _layer_for_group(layout, group_name)
        for polygon in polygons:
            lines.extend(_lwpolyline_entity(polygon.points, layer))
    for label in layout.lot_labels:
        lines.extend(_text_entity(label, layer=LAYER_MAP["lot_labels"]))

    lines.extend(["0", "ENDSEC", "0", "EOF"])
    Path(output_path).write_text("\n".join(lines) + "\n", encoding="ascii")
    return output_path


def _dxf_header() -> List[str]:
    return [
        "0",
        "SECTION",
        "2",
        "HEADER",
        "9",
        "$ACADVER",
        "1",
        "AC1015",
        "0",
        "ENDSEC",
    ]


def _dxf_layers() -> List[str]:
    lines = ["0", "SECTION", "2", "TABLES", "0", "TABLE", "2", "LAYER", "70", str(len(LAYER_COLORS))]
    for name, color in LAYER_COLORS.items():
        lines.extend(
            [
                "0",
                "LAYER",
                "2",
                name,
                "70",
                "0",
                "62",
                str(color),
                "6",
                "CONTINUOUS",
            ]
        )
    lines.extend(["0", "ENDTAB", "0", "ENDSEC"])
    return lines


def _lwpolyline_entity(points: Iterable[Tuple[float, float]], layer: str) -> List[str]:
    pts = list(points)
    entity = [
        "0",
        "LWPOLYLINE",
        "100",
        "AcDbEntity",
        "8",
        layer,
        "100",
        "AcDbPolyline",
        "90",
        str(len(pts)),
        "70",
        "1",
    ]
    for x, y in pts:
        entity.extend(["10", _fmt(x), "20", _fmt(y)])
    return entity


def _add_labels_ezdxf(msp, labels: List[LotLabel]) -> None:
    for label in labels:
        msp.add_text(
            label.text,
            dxfattribs={"layer": LAYER_MAP["lot_labels"], "height": 14},
        ).set_placement(label.position)


def _text_entity(label: LotLabel, layer: str) -> List[str]:
    x, y = label.position
    return [
        "0",
        "TEXT",
        "100",
        "AcDbEntity",
        "8",
        layer,
        "100",
        "AcDbText",
        "10",
        _fmt(x),
        "20",
        _fmt(y),
        "30",
        "0",
        "40",
        "14",
        "1",
        label.text,
    ]


def _layer_for_group(layout: LayoutData, group_name: str) -> str:
    if group_name == "road" and layout.optimized:
        return LAYER_MAP["optimized_road"]
    return LAYER_MAP[group_name]


def _fmt(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")
