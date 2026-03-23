from __future__ import annotations

from shapely.geometry import shape

from bedrock.contracts.layout_result import LayoutResult
from bedrock.contracts.parcel import Parcel
from bedrock.contracts.zoning_rules import ZoningRules
from model_lab.services.candidate_generation_service import STRATEGIES, generate_candidates
from model_lab.strategy_models import culdesac_strategy, grid_strategy, spine_strategy
from model_lab.strategy_models.layout_generation_utils import max_units_allowed


def _sample_parcel() -> Parcel:
    return Parcel(
        parcel_id="phase2-test-parcel",
        geometry={
            "type": "Polygon",
            "coordinates": [[[0.0, 0.0], [0.0, 520.0], [520.0, 520.0], [520.0, 0.0], [0.0, 0.0]]],
        },
        area_sqft=270400.0,
        centroid=[260.0, 260.0],
        bounding_box=[0.0, 0.0, 520.0, 520.0],
        jurisdiction="test-jurisdiction",
    )


def _sample_zoning(parcel_id: str) -> ZoningRules:
    return ZoningRules(
        parcel_id=parcel_id,
        jurisdiction="test-jurisdiction",
        district="R-1",
        min_lot_size_sqft=6000.0,
        max_units_per_acre=5.0,
        setbacks={"front": 25.0, "side": 8.0, "rear": 20.0},
    )


def test_strategy_interface_compliance() -> None:
    parcel = _sample_parcel()
    zoning = _sample_zoning(parcel.parcel_id)
    for strategy in (grid_strategy, spine_strategy, culdesac_strategy):
        assert hasattr(strategy, "generate_layout")
        result = strategy.generate_layout(parcel, zoning)
        assert isinstance(result, LayoutResult)
        assert result.parcel_id == parcel.parcel_id


def test_deterministic_output_for_fixed_inputs() -> None:
    parcel = _sample_parcel()
    zoning = _sample_zoning(parcel.parcel_id)
    first = generate_candidates(parcel, zoning)
    second = generate_candidates(parcel, zoning)

    assert [c.strategy_name for c in first] == [c.strategy_name for c in second]
    assert [c.layout.unit_count for c in first] == [c.layout.unit_count for c in second]
    assert [round(c.layout.road_length_ft, 4) for c in first] == [
        round(c.layout.road_length_ft, 4) for c in second
    ]
    assert [round(float(c.layout.score or 0.0), 6) for c in first] == [
        round(float(c.layout.score or 0.0), 6) for c in second
    ]


def test_zoning_constraint_satisfaction() -> None:
    parcel = _sample_parcel()
    zoning = _sample_zoning(parcel.parcel_id)
    max_units = max_units_allowed(parcel, zoning)
    candidates = generate_candidates(parcel, zoning)
    assert candidates
    for candidate in candidates:
        layout = candidate.layout
        assert layout.unit_count <= max_units
        for lot_geo in layout.lot_geometries:
            assert float(shape(lot_geo).area) + 1e-6 >= float(zoning.min_lot_size_sqft or 0.0)


def test_multiple_strategies_attempted_per_parcel() -> None:
    parcel = _sample_parcel()
    zoning = _sample_zoning(parcel.parcel_id)
    candidates = generate_candidates(parcel, zoning)
    attempted = {c.strategy_name for c in candidates}
    assert set(STRATEGIES.keys()).issubset(attempted)
    assert len(candidates) >= 3

