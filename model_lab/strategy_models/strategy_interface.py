"""
Strategy interface for layout models.

This module defines the contract that all layout strategy models must implement.
Future ML models will produce LayoutStrategy instances that drive the layout engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


DensityGoal = Literal["low", "medium", "high"]
RoadType = Literal["loop", "spine", "parallel", "culdesac", "collector"]
EntryPoint = Literal["north", "south", "east", "west"]


@dataclass
class LayoutStrategy:
    """Describes a high-level layout strategy for a parcel.

    This interface is consumed by the experiment runner and will later be
    produced by ML models trained on generated layout datasets.
    """

    road_type: RoadType
    entry_point: EntryPoint
    culdesac_count: int
    density_goal: DensityGoal

    def to_dict(self) -> dict:
        return {
            "road_type": self.road_type,
            "entry_point": self.entry_point,
            "culdesac_count": self.culdesac_count,
            "density_goal": self.density_goal,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LayoutStrategy":
        return cls(
            road_type=data["road_type"],
            entry_point=data["entry_point"],
            culdesac_count=data["culdesac_count"],
            density_goal=data["density_goal"],
        )
