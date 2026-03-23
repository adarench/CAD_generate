"""
Parameterized Strategy Schema — model_lab

Extends the categorical LayoutStrategy with continuous parameters.

LayoutStrategy (Phase 1–4):
  road_type ∈ {loop, spine, parallel, culdesac}
  density_goal ∈ {low, medium, high}
  entry_point ∈ {north, south, east, west}

ParamStrategy (Phase 5):
  All of the above, PLUS continuous controls that feed directly
  into the engine:
    road_width_ft          → Road(width_ft=...)
    min_lot_area_sqft      → ZoningRules(min_area_sqft=...)
    min_frontage_ft        → ZoningRules(min_frontage_ft=...)
    min_depth_ft           → ZoningRules(min_depth_ft=...)
    target_density_du_per_acre → Lots(count=area_acres * density)

  Plus conceptual geometry parameters (stored in feature vector,
  available for future engine support):
    branch_count, branch_angle_deg, road_spacing_ft,
    loop_radius_ft, culdesac_radius_ft, culdesac_depth_ft,
    collector_length_ft, orientation_angle_deg

All parameters have defined [min, max] ranges used for sampling
and mutation.

No production code is modified.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from typing import ClassVar, Dict, Optional, Tuple

ROAD_TYPES   = ["loop", "spine", "parallel", "culdesac"]
ENTRY_POINTS = ["north", "south", "east", "west"]

# ---------------------------------------------------------------------------
# Parameter ranges — (min, max) for continuous params
# ---------------------------------------------------------------------------

PARAM_RANGES: Dict[str, Tuple[float, float]] = {
    # Engine-connected
    "road_width_ft":           (24.0,  50.0),
    "min_lot_area_sqft":       (3000.0, 9000.0),
    "min_frontage_ft":         (40.0,  80.0),
    "min_depth_ft":            (80.0, 140.0),
    "target_density_du_per_acre": (2.0, 14.0),
    # Conceptual geometry
    "branch_count":            (1.0,   6.0),
    "branch_angle_deg":        (30.0,  90.0),
    "road_spacing_ft":         (100.0, 350.0),
    "loop_radius_ft":          (80.0,  220.0),
    "culdesac_radius_ft":      (30.0,   60.0),
    "culdesac_depth_ft":       (100.0, 250.0),
    "collector_length_ft":     (200.0, 600.0),
    "orientation_angle_deg":   (0.0,   90.0),
}

# Default / baseline values (matches current production defaults)
PARAM_DEFAULTS: Dict[str, float] = {
    "road_width_ft":              40.0,
    "min_lot_area_sqft":        6000.0,
    "min_frontage_ft":            60.0,
    "min_depth_ft":              110.0,
    "target_density_du_per_acre":  5.0,
    "branch_count":                2.0,
    "branch_angle_deg":           90.0,
    "road_spacing_ft":           200.0,
    "loop_radius_ft":            150.0,
    "culdesac_radius_ft":         40.0,
    "culdesac_depth_ft":         180.0,
    "collector_length_ft":       400.0,
    "orientation_angle_deg":       0.0,
}


@dataclass
class ParamStrategy:
    """
    Fully parameterized subdivision strategy.

    Categorical selectors
    ---------------------
    road_type       : loop | spine | parallel | culdesac
    entry_point     : north | south | east | west

    Engine-connected continuous params
    ----------------------------------
    road_width_ft              Road(width_ft=...)
    min_lot_area_sqft          ZoningRules(min_area_sqft=...)
    min_frontage_ft            ZoningRules(min_frontage_ft=...)
    min_depth_ft               ZoningRules(min_depth_ft=...)
    target_density_du_per_acre Lots(count = area_acres * density)

    Conceptual geometry params (feature vector only)
    -------------------------------------------------
    branch_count
    branch_angle_deg
    road_spacing_ft
    loop_radius_ft
    culdesac_radius_ft
    culdesac_depth_ft
    collector_length_ft
    orientation_angle_deg
    """

    # Categorical
    road_type:   str = "loop"
    entry_point: str = "north"

    # Engine-connected
    road_width_ft:              float = 40.0
    min_lot_area_sqft:          float = 6000.0
    min_frontage_ft:            float = 60.0
    min_depth_ft:               float = 110.0
    target_density_du_per_acre: float = 5.0

    # Conceptual geometry
    branch_count:            float = 2.0
    branch_angle_deg:        float = 90.0
    road_spacing_ft:         float = 200.0
    loop_radius_ft:          float = 150.0
    culdesac_radius_ft:      float = 40.0
    culdesac_depth_ft:       float = 180.0
    collector_length_ft:     float = 400.0
    orientation_angle_deg:   float = 0.0

    # ---------------------------------------------------------------------------
    # Engine translation
    # ---------------------------------------------------------------------------

    def compute_target_lot_count(self, parcel_area_sqft: float) -> int:
        """Convert density + area to integer target lot count."""
        area_acres = parcel_area_sqft / 43560.0
        raw = self.target_density_du_per_acre * area_acres
        # Also apply a floor based on min_lot_area to avoid over-requesting
        max_possible = int(parcel_area_sqft / max(self.min_lot_area_sqft, 100))
        return max(4, min(int(raw), max_possible, 120))

    def road_orientation(self) -> str:
        return (
            "north_south" if self.entry_point in ("north", "south") else "east_west"
        )

    def to_engine_params(self, parcel_area_sqft: float) -> dict:
        """
        Return a dict suitable for constructing engine inputs.

        Keys: road_width_ft, min_lot_area_sqft, min_frontage_ft, min_depth_ft,
              target_lot_count, road_orientation, road_type
        """
        return {
            "road_type":          self.road_type,
            "road_orientation":   self.road_orientation(),
            "road_width_ft":      self.road_width_ft,
            "min_lot_area_sqft":  self.min_lot_area_sqft,
            "min_frontage_ft":    self.min_frontage_ft,
            "min_depth_ft":       self.min_depth_ft,
            "target_lot_count":   self.compute_target_lot_count(parcel_area_sqft),
        }

    # ---------------------------------------------------------------------------
    # Compatibility
    # ---------------------------------------------------------------------------

    def density_goal(self) -> str:
        """Map continuous density to a categorical label (for compatibility)."""
        if self.target_density_du_per_acre < 4.0:
            return "low"
        if self.target_density_du_per_acre < 8.0:
            return "medium"
        return "high"

    def to_strategy_dict(self) -> dict:
        """Minimal dict compatible with LayoutStrategy.from_dict()."""
        return {
            "road_type":       self.road_type,
            "entry_point":     self.entry_point,
            "culdesac_count":  max(0, int(round(self.branch_count))),
            "density_goal":    self.density_goal(),
        }

    # ---------------------------------------------------------------------------
    # Serialisation
    # ---------------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "road_type":                  self.road_type,
            "entry_point":               self.entry_point,
            "road_width_ft":             round(self.road_width_ft, 2),
            "min_lot_area_sqft":         round(self.min_lot_area_sqft, 1),
            "min_frontage_ft":           round(self.min_frontage_ft, 2),
            "min_depth_ft":              round(self.min_depth_ft, 2),
            "target_density_du_per_acre": round(self.target_density_du_per_acre, 3),
            "branch_count":              round(self.branch_count, 2),
            "branch_angle_deg":          round(self.branch_angle_deg, 2),
            "road_spacing_ft":           round(self.road_spacing_ft, 2),
            "loop_radius_ft":            round(self.loop_radius_ft, 2),
            "culdesac_radius_ft":        round(self.culdesac_radius_ft, 2),
            "culdesac_depth_ft":         round(self.culdesac_depth_ft, 2),
            "collector_length_ft":       round(self.collector_length_ft, 2),
            "orientation_angle_deg":     round(self.orientation_angle_deg, 2),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ParamStrategy":
        return cls(
            road_type=d.get("road_type", "loop"),
            entry_point=d.get("entry_point", "north"),
            road_width_ft=float(d.get("road_width_ft", 40.0)),
            min_lot_area_sqft=float(d.get("min_lot_area_sqft", 6000.0)),
            min_frontage_ft=float(d.get("min_frontage_ft", 60.0)),
            min_depth_ft=float(d.get("min_depth_ft", 110.0)),
            target_density_du_per_acre=float(d.get("target_density_du_per_acre", 5.0)),
            branch_count=float(d.get("branch_count", 2.0)),
            branch_angle_deg=float(d.get("branch_angle_deg", 90.0)),
            road_spacing_ft=float(d.get("road_spacing_ft", 200.0)),
            loop_radius_ft=float(d.get("loop_radius_ft", 150.0)),
            culdesac_radius_ft=float(d.get("culdesac_radius_ft", 40.0)),
            culdesac_depth_ft=float(d.get("culdesac_depth_ft", 180.0)),
            collector_length_ft=float(d.get("collector_length_ft", 400.0)),
            orientation_angle_deg=float(d.get("orientation_angle_deg", 0.0)),
        )

    @classmethod
    def from_template(cls, road_type: str, entry_point: str, density_goal: str) -> "ParamStrategy":
        """Create a ParamStrategy from categorical template (defaults for continuous params)."""
        density_map = {"low": 3.0, "medium": 5.5, "high": 9.0}
        return cls(
            road_type=road_type,
            entry_point=entry_point,
            target_density_du_per_acre=density_map.get(density_goal, 5.0),
        )

    def __repr__(self) -> str:
        return (
            f"ParamStrategy(type={self.road_type}, entry={self.entry_point}, "
            f"density={self.target_density_du_per_acre:.1f}du/ac, "
            f"road_w={self.road_width_ft:.0f}ft, "
            f"min_lot={self.min_lot_area_sqft:.0f}sqft)"
        )
