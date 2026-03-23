from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ParcelInput(BaseModel):
    parcel_id: str
    geometry: Dict[str, Any]
    area_sqft: float = Field(gt=0)


class ZoningInput(BaseModel):
    district: str
    min_lot_size_sqft: float = Field(default=6000.0, gt=0)
    max_units_per_acre: float = Field(default=5.0, gt=0)
    setbacks: Dict[str, float] = Field(default_factory=dict)


class LayoutResult(BaseModel):
    layout_id: str
    units: int
    road_length: float
    lot_geometries: List[Dict[str, Any]] = Field(default_factory=list)
    road_geometries: List[Dict[str, Any]] = Field(default_factory=list)
    score: float
    metadata: Dict[str, Any] = Field(default_factory=dict)
