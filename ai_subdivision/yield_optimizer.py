from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence

from .constraints import SubdivisionConstraints
from .geometry import parcel_shapely_from_constraints
from .street_network import StreetNetworkCandidate, generate_candidate_street_networks
from .subdivision import LayoutData, generate_optimization_target, generate_subdivision
from .zoning import ZoningRules


@dataclass(frozen=True)
class OptimizationResult:
    best_layout: LayoutData
    lot_count: int
    layouts_tested: int
    best_network: StreetNetworkCandidate


def optimize_yield(
    constraints: SubdivisionConstraints,
    zoning_rules: ZoningRules,
    max_layout_tests: int = 100,
    allowed_topologies: Sequence[str] | None = None,
) -> OptimizationResult:
    parcel_polygon = parcel_shapely_from_constraints(constraints)
    target_lot_count = generate_optimization_target(constraints, zoning_rules)
    street_networks = generate_candidate_street_networks(
        parcel_polygon=parcel_polygon,
        road_width_ft=constraints.road.width_ft,
        max_candidates=max_layout_tests,
    )
    if allowed_topologies:
        street_networks = [
            network for network in street_networks if network.topology in allowed_topologies
        ]
    # Previously the optimizer just picked the candidate with the most lots and emitted
    # whatever topology that happened to be (usually parallel), so even if loops/culdesacs
    # existed they were never surfaced. This filtering + logging ensures each topology is
    # treated as a first-class variable.

    best_layout = None
    best_lot_count = -1
    tested = 0
    candidate_results: List[tuple[str, int, float]] = []

    for network in street_networks:
        tested += 1
        try:
            layout = generate_subdivision(
                constraints=constraints,
                zoning_rules=zoning_rules,
                street_network=network,
                target_lot_count=target_lot_count,
                optimized=True,
            )
        except ValueError:
            continue
        lot_count = len(layout.lots)
        candidate_results.append((network.topology, lot_count, network.road_length_ft))
        if lot_count > best_lot_count:
            best_layout = layout
            best_lot_count = lot_count

    if best_layout is None:
        raise RuntimeError("Yield optimization did not produce any layouts.")

    print("\nTested street network candidates:")
    for topology, count, length in candidate_results:
        print(f"  {topology:8s} → lots={count:2d}, road_length={length:.1f} ft")

    return OptimizationResult(
        best_layout=best_layout,
        lot_count=best_lot_count,
        layouts_tested=tested,
        best_network=best_layout.street_network,
    )
