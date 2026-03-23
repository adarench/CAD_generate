"""
Layout Scoring — model_lab

Computes multi-dimensional scores for a completed layout.

Scores are normalised to [0, 1] where practical:
  yield_score       — raw lot count (higher = more units)
  efficiency_score  — developable area utilisation relative to road cost
  overall_score     — weighted combination of the above

These scores will evolve toward profit estimation as the model lab matures.
No production code is modified.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from model_lab.training.layout_runner import LayoutMetrics


# ---------------------------------------------------------------------------
# Score dataclass
# ---------------------------------------------------------------------------

@dataclass
class LayoutScore:
    yield_score: float
    efficiency_score: float
    overall_score: float

    def to_dict(self) -> dict:
        return {
            "yield_score": round(self.yield_score, 4),
            "efficiency_score": round(self.efficiency_score, 4),
            "overall_score": round(self.overall_score, 4),
        }


# ---------------------------------------------------------------------------
# Reference bounds (used for normalisation)
# Loose upper bounds; scores can exceed 1.0 for exceptional layouts.
# ---------------------------------------------------------------------------

_REF_MAX_LOTS = 40.0                   # lots in a typical 10-acre subdivision
_REF_MAX_EFFICIENCY = 200.0            # sqft developable per ft of road (calibrated empirically)
_WEIGHT_YIELD = 0.6
_WEIGHT_EFFICIENCY = 0.4


# ---------------------------------------------------------------------------
# Scoring functions
# ---------------------------------------------------------------------------

def compute_yield_score(metrics: LayoutMetrics) -> float:
    """
    Lot-count score, lightly normalised against a reference maximum.

    Returns a float in [0, ~1].  Values > 1 indicate above-reference yield.
    """
    return metrics.lot_count / _REF_MAX_LOTS


def compute_efficiency_score(metrics: LayoutMetrics) -> float:
    """
    Ratio of developable area to road length.

    Higher = more land is available for lots relative to road infrastructure cost.
    Returns 0 when road_length_ft == 0 to avoid division by zero.
    """
    if metrics.road_length_ft <= 0:
        return 0.0
    raw = metrics.developable_area_sqft / metrics.road_length_ft
    return raw / _REF_MAX_EFFICIENCY


def compute_overall_score(yield_score: float, efficiency_score: float) -> float:
    """Weighted combination of yield and efficiency scores."""
    return _WEIGHT_YIELD * yield_score + _WEIGHT_EFFICIENCY * efficiency_score


def score_layout(metrics: LayoutMetrics) -> LayoutScore:
    """
    Compute the full score for a layout given its metrics.

    This is the primary entry point used by the dataset generator.
    """
    if metrics.lot_count == 0:
        return LayoutScore(yield_score=0.0, efficiency_score=0.0, overall_score=0.0)

    yield_score = compute_yield_score(metrics)
    efficiency_score = compute_efficiency_score(metrics)
    overall_score = compute_overall_score(yield_score, efficiency_score)

    return LayoutScore(
        yield_score=yield_score,
        efficiency_score=efficiency_score,
        overall_score=overall_score,
    )


# ---------------------------------------------------------------------------
# Batch ranking helper
# ---------------------------------------------------------------------------

def rank_layouts(scored_layouts: list[tuple[dict, LayoutScore]]) -> list[tuple[dict, LayoutScore]]:
    """
    Sort (layout_dict, score) pairs by overall_score descending.
    Useful for selecting the best strategy for a given parcel.
    """
    return sorted(scored_layouts, key=lambda item: item[1].overall_score, reverse=True)
