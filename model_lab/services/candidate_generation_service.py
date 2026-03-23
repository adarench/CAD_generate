"""Phase 2 research candidate orchestration service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, List

from shapely.geometry import shape

from bedrock.contracts.layout_result import LayoutResult
from bedrock.contracts.parcel import Parcel
from bedrock.contracts.zoning_rules import ZoningRules
from model_lab.strategy_models import culdesac_strategy, grid_strategy, spine_strategy
from model_lab.strategy_models.layout_generation_utils import (
    compactness_score,
    max_units_allowed,
    regularity_score,
)

StrategyFn = Callable[[Parcel, ZoningRules], LayoutResult]


@dataclass(frozen=True)
class CandidateEvaluation:
    strategy_name: str
    layout: LayoutResult
    score_breakdown: dict[str, float]


STRATEGIES: dict[str, StrategyFn] = {
    "grid": grid_strategy.generate_layout,
    "spine-road": spine_strategy.generate_layout,
    "cul-de-sac": culdesac_strategy.generate_layout,
}


def _is_zoning_compliant(layout: LayoutResult, parcel: Parcel, zoning: ZoningRules) -> bool:
    min_lot_size = float(zoning.min_lot_size_sqft or 0.0)
    if min_lot_size <= 0.0:
        return False

    max_units = max_units_allowed(parcel, zoning)
    if layout.unit_count > max_units:
        return False

    for lot in layout.lot_geometries:
        if float(shape(lot).area) + 1e-6 < min_lot_size:
            return False
    return True


def _road_efficiency_score(units: int, road_length_ft: float) -> float:
    return max(0.0, min(1.0, units / (1.0 + (road_length_ft / 200.0))))


def _score_layout(layout: LayoutResult, parcel: Parcel, zoning: ZoningRules) -> tuple[float, dict[str, float]]:
    max_units = max(max_units_allowed(parcel, zoning), 1)
    lots = [shape(g) for g in layout.lot_geometries]
    compliant = 1.0 if _is_zoning_compliant(layout, parcel, zoning) else 0.0
    units_score = max(0.0, min(1.0, layout.unit_count / max_units))
    road_eff = _road_efficiency_score(layout.unit_count, layout.road_length_ft)
    reg = regularity_score(lots)
    compact = compactness_score(lots)

    overall = (
        0.45 * units_score
        + 0.20 * road_eff
        + 0.15 * reg
        + 0.10 * compact
        + 0.10 * compliant
    )
    if not compliant:
        overall *= 0.20
    overall = max(0.0, min(1.0, overall))
    return overall, {
        "overall": round(overall, 6),
        "units_score": round(units_score, 6),
        "road_efficiency": round(road_eff, 6),
        "lot_regularity": round(reg, 6),
        "compactness": round(compact, 6),
        "zoning_compliance": compliant,
    }


def generate_candidates(parcel: Parcel, zoning: ZoningRules) -> List[CandidateEvaluation]:
    """Generate and rank candidate layouts from all Phase 2 strategies."""
    evaluations: list[CandidateEvaluation] = []
    for strategy_name, generator in STRATEGIES.items():
        evaluations.append(evaluate_strategy(strategy_name, generator, parcel, zoning))
    evaluations.sort(key=lambda item: item.layout.score or 0.0, reverse=True)
    return evaluations


def select_best_layout(candidates: Iterable[CandidateEvaluation]) -> CandidateEvaluation | None:
    candidates = list(candidates)
    if not candidates:
        return None
    return max(candidates, key=lambda item: item.layout.score or 0.0)


def evaluate_strategy(
    strategy_name: str,
    generator: StrategyFn,
    parcel: Parcel,
    zoning: ZoningRules,
) -> CandidateEvaluation:
    layout = generator(parcel, zoning)
    score, breakdown = _score_layout(layout, parcel, zoning)
    layout.score = score
    return CandidateEvaluation(
        strategy_name=strategy_name,
        layout=layout,
        score_breakdown=breakdown,
    )
