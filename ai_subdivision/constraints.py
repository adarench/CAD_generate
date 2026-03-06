from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


RoadOrientation = Literal["north_south", "east_west"]
ParcelShape = Literal["rectangle", "polygon"]
Point2D = tuple[float, float]


class Parcel(BaseModel):
    shape: ParcelShape = Field(default="rectangle")
    area_acres: Optional[float] = Field(
        default=None, gt=0, description="Parcel area in acres."
    )
    aspect_ratio: float = Field(
        default=1.5,
        gt=0,
        description="Width / height ratio for synthetic rectangular parcels.",
    )
    boundary: Optional[list[Point2D]] = Field(
        default=None,
        description="Parcel polygon vertices in feet, without repeating the closing vertex.",
    )

    @model_validator(mode="after")
    def validate_inputs(self) -> "Parcel":
        if self.shape == "rectangle" and self.area_acres is None:
            raise ValueError("Rectangle parcels require area_acres.")
        if self.shape == "polygon":
            if not self.boundary or len(self.boundary) < 3:
                raise ValueError("Polygon parcels require at least 3 boundary points.")
        return self


class Lots(BaseModel):
    count: int = Field(gt=0, description="Target lot count.")


class Road(BaseModel):
    orientation: RoadOrientation = Field(default="north_south")
    width_ft: float = Field(default=40.0, gt=0)


class Easement(BaseModel):
    width_ft: float = Field(default=10.0, ge=0)


class SubdivisionConstraints(BaseModel):
    parcel: Parcel
    lots: Lots
    road: Road
    easement: Easement = Field(default_factory=Easement)
