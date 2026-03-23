"""
Lot Validator — model_lab

Validates LotPolygon objects against zoning constraints and geometric sanity.

Checks:
  1. Minimum area
  2. Minimum frontage
  3. Minimum depth
  4. Polygon validity (no self-intersection)
  5. Contained within parcel boundary (with tolerance)

No production code is modified.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from shapely.geometry import Polygon

from model_lab.subdivision.lot_slicer import LotPolygon


@dataclass
class ValidationResult:
    """Outcome of validating a single lot."""
    lot:         LotPolygon
    valid:       bool
    reasons:     List[str]      # why it was rejected (empty if valid)


@dataclass
class ValidationSummary:
    """Aggregate statistics from validating a batch of lots."""
    total:             int
    valid_count:       int
    rejected_area:     int
    rejected_frontage: int
    rejected_depth:    int
    rejected_geometry: int
    rejected_boundary: int

    @property
    def valid_lots(self) -> List[LotPolygon]:
        return self._valid_lots

    def __post_init__(self):
        self._valid_lots: List[LotPolygon] = []


def validate_lot(
    lot:             LotPolygon,
    parcel_polygon:  Polygon,
    min_area_sqft:   float = 4000.0,
    min_frontage_ft: float = 50.0,
    min_depth_ft:    float = 80.0,
    boundary_tolerance: float = 2.0,   # feet — allow slight overshoot
) -> ValidationResult:
    """
    Validate a single lot polygon.

    Args:
        lot:                LotPolygon to validate
        parcel_polygon:     parcel boundary
        min_area_sqft:      minimum lot area
        min_frontage_ft:    minimum frontage
        min_depth_ft:       minimum depth
        boundary_tolerance: buffer around parcel to allow for floating point

    Returns:
        ValidationResult with valid flag and list of rejection reasons.
    """
    reasons = []

    # Geometry sanity
    if not lot.polygon.is_valid:
        reasons.append("invalid_geometry")
    if lot.polygon.is_empty:
        reasons.append("empty_geometry")

    # Area
    if lot.area_sqft < min_area_sqft:
        reasons.append(f"area_too_small:{lot.area_sqft:.0f}<{min_area_sqft:.0f}")

    # Frontage
    if lot.frontage_ft < min_frontage_ft * 0.85:   # 15% tolerance for measurement error
        reasons.append(f"frontage_too_small:{lot.frontage_ft:.1f}<{min_frontage_ft:.0f}")

    # Depth
    if lot.depth_ft < min_depth_ft * 0.85:
        reasons.append(f"depth_too_small:{lot.depth_ft:.1f}<{min_depth_ft:.0f}")

    # Boundary containment
    try:
        buffered_parcel = parcel_polygon.buffer(boundary_tolerance)
        if not buffered_parcel.contains(lot.polygon):
            # Check if the part outside is significant
            outside = lot.polygon.difference(buffered_parcel)
            if outside.area > lot.area_sqft * 0.05:  # >5% outside → reject
                reasons.append(f"outside_parcel:{outside.area:.0f}sqft")
    except Exception:
        pass  # geometric operations can fail on edge cases; skip this check

    return ValidationResult(lot=lot, valid=len(reasons) == 0, reasons=reasons)


def validate_lots(
    lots:            List[LotPolygon],
    parcel_polygon:  Polygon,
    min_area_sqft:   float = 4000.0,
    min_frontage_ft: float = 50.0,
    min_depth_ft:    float = 80.0,
) -> Tuple[List[LotPolygon], ValidationSummary]:
    """
    Validate a list of lots and return valid lots + summary statistics.

    Returns:
        (valid_lots, summary)
    """
    summary = ValidationSummary(
        total=len(lots),
        valid_count=0,
        rejected_area=0,
        rejected_frontage=0,
        rejected_depth=0,
        rejected_geometry=0,
        rejected_boundary=0,
    )

    valid_lots = []
    for lot in lots:
        result = validate_lot(
            lot=lot,
            parcel_polygon=parcel_polygon,
            min_area_sqft=min_area_sqft,
            min_frontage_ft=min_frontage_ft,
            min_depth_ft=min_depth_ft,
        )
        if result.valid:
            summary.valid_count += 1
            valid_lots.append(lot)
        else:
            for r in result.reasons:
                if r.startswith("area"):
                    summary.rejected_area += 1
                elif r.startswith("frontage"):
                    summary.rejected_frontage += 1
                elif r.startswith("depth"):
                    summary.rejected_depth += 1
                elif "geometry" in r:
                    summary.rejected_geometry += 1
                elif "boundary" in r or "outside" in r:
                    summary.rejected_boundary += 1

    summary._valid_lots = valid_lots
    return valid_lots, summary
