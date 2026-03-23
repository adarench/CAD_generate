from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from services.layout_models import LayoutResult, ParcelInput, ZoningInput

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
BEDROCK_ROOT = WORKSPACE_ROOT / "bedrock"

bedrock_root_str = str(BEDROCK_ROOT)
if bedrock_root_str not in sys.path:
    sys.path.append(bedrock_root_str)

_BEDROCK_LAYOUT_SERVICE_SPEC = importlib.util.spec_from_file_location(
    "bedrock_layout_service_module",
    BEDROCK_ROOT / "services" / "layout_service.py",
)
if _BEDROCK_LAYOUT_SERVICE_SPEC is None or _BEDROCK_LAYOUT_SERVICE_SPEC.loader is None:
    raise ImportError("Unable to load bedrock layout service module")

_BEDROCK_LAYOUT_SERVICE = importlib.util.module_from_spec(_BEDROCK_LAYOUT_SERVICE_SPEC)
sys.modules[_BEDROCK_LAYOUT_SERVICE_SPEC.name] = _BEDROCK_LAYOUT_SERVICE
_BEDROCK_LAYOUT_SERVICE_SPEC.loader.exec_module(_BEDROCK_LAYOUT_SERVICE)

from contracts.parcel import Parcel  # type: ignore  # noqa: E402
ZoningRules = _BEDROCK_LAYOUT_SERVICE.ZoningRules
search_canonical_layout = _BEDROCK_LAYOUT_SERVICE.search_layout


def _to_canonical_parcel(parcel: ParcelInput) -> Parcel:
    return Parcel(
        parcel_id=parcel.parcel_id,
        geometry=parcel.geometry,
        area=float(parcel.area_sqft),
        jurisdiction="unknown",
        zoning_district=None,
        utilities=[],
        access_points=[],
        topography={},
        existing_structures=[],
        metadata=None,
    )


def _to_canonical_zoning(zoning: ZoningInput) -> ZoningRules:
    return ZoningRules(
        district=zoning.district,
        min_lot_size_sqft=float(zoning.min_lot_size_sqft),
        max_units_per_acre=float(zoning.max_units_per_acre),
        setbacks=dict(zoning.setbacks),
    )


def search_layout(parcel: ParcelInput, zoning: ZoningInput, max_candidates: int = 50) -> LayoutResult:
    result = search_canonical_layout(
        _to_canonical_parcel(parcel),
        _to_canonical_zoning(zoning),
        max_candidates=max_candidates,
    )
    return LayoutResult(
        layout_id=result.layout_id,
        units=result.units,
        road_length=result.road_length,
        lot_geometries=result.lot_geometries,
        road_geometries=result.road_geometries,
        score=result.score,
        metadata={
            "source_engine": "bedrock.layout_service",
            "source_contract": "canonical_layout_result",
        },
    )
