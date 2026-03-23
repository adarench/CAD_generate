from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps/python-api"))

from ai_subdivision.constraints import Easement, Lots, Parcel, Road, SubdivisionConstraints
from ai_subdivision.zoning import ZoningRules
from schemas import OptimizationRequest, TopologyEnum
from services.optimization_service import OptimizerService
from services.parcel_adapter import adapt_parcel_geometry


MEDIUM_PARCEL_ID = "ut-SaltLake-22282270250000"


def _load_medium_constraints():
    async def _inner():
        service = OptimizerService()
        parcel = await service.parcels.get_parcel(MEDIUM_PARCEL_ID)
        assert parcel is not None, f"Parcel {MEDIUM_PARCEL_ID} must exist in the parcel cache"
        adapted = adapt_parcel_geometry(parcel.geometryGeoJSON.model_dump())
        boundary = [list(coord) for coord in adapted.parcel_polygon.exterior.coords[:-1]]
        constraints = service._build_constraints({}, boundary)
        zoning = ZoningRules(min_frontage_ft=60, min_depth_ft=110, min_area_sqft=6000)
        return service, constraints, zoning

    return asyncio.run(_inner())


def test_medium_parcel_topology_preferences_produce_distinct_layout_families():
    service, constraints, zoning = _load_medium_constraints()

    observed: dict[str, tuple[str, int, float]] = {}
    for topology in ("parallel", "spine", "loop", "culdesac"):
        result, fallback_details = service._optimize_for_topologies(
            constraints=constraints,
            zoning=zoning,
            preferred_topologies=[topology],
            strict_topology=False,
        )
        assert fallback_details is None
        observed[topology] = (
            result.best_network.topology,
            result.lot_count,
            round(result.best_network.road_length_ft, 1),
        )

    assert observed == {
        "parallel": ("parallel", 15, 1646.5),
        "spine": ("spine", 5, 3193.5),
        "loop": ("loop", 9, 863.0),
        "culdesac": ("culdesac", 4, 240.8),
    }


def test_mixed_preferred_topologies_do_not_fallback_to_nonpreferred_family_when_valid():
    async def _inner():
        service = OptimizerService()
        request = OptimizationRequest(
            parcelId=MEDIUM_PARCEL_ID,
            designConstraints={},
            topologyPreferences=[TopologyEnum.loop, TopologyEnum.culdesac, TopologyEnum.spine],
            strictTopology=False,
            conceptText="",
        )
        run = await service.optimize(request)
        return run.response

    response = asyncio.run(_inner())
    assert response.winningTopology == "loop"
    summaries = {item.topology: item for item in response.candidateSummary}
    assert summaries["parallel"].candidatesTested == 0
    assert summaries["parallel"].status == "not-tested"
    assert summaries["loop"].status == "winner"
    assert summaries["spine"].status == "preferred"
    assert summaries["culdesac"].status == "preferred"


def test_fallback_is_explicit_only_when_strict_mode_is_off(monkeypatch: pytest.MonkeyPatch):
    service = OptimizerService()
    constraints = SubdivisionConstraints(
        parcel=Parcel(shape="rectangle", area_acres=3, aspect_ratio=1.5),
        lots=Lots(count=24),
        road=Road(orientation="north_south", width_ft=40),
        easement=Easement(width_ft=12),
    )
    zoning = ZoningRules(min_frontage_ft=60, min_depth_ft=110, min_area_sqft=6000)
    fallback_result = SimpleNamespace(
        best_network=SimpleNamespace(topology="parallel"),
        lot_count=12,
        candidate_summary=[],
    )
    calls: list[tuple[str, tuple[str, ...] | None]] = []

    def fake_optimize_yield(_constraints, _zoning, allowed_topologies=None, max_layout_tests=100):
        calls.append(("call", tuple(allowed_topologies) if allowed_topologies else None))
        if allowed_topologies:
            raise ValueError("No preferred candidates")
        return fallback_result

    monkeypatch.setattr("services.optimization_service.optimize_yield", fake_optimize_yield)

    result, fallback_details = service._optimize_for_topologies(
        constraints=constraints,
        zoning=zoning,
        preferred_topologies=["loop"],
        strict_topology=False,
    )
    assert result is fallback_result
    assert fallback_details == "preferred topology set (loop) produced no valid layouts"
    assert calls == [("call", ("loop",)), ("call", None)]

    calls.clear()
    with pytest.raises(ValueError):
        service._optimize_for_topologies(
            constraints=constraints,
            zoning=zoning,
            preferred_topologies=["loop"],
            strict_topology=True,
        )
    assert calls == [("call", ("loop",))]
