"""
Strategy Sampler — model_lab

Generates ParamStrategy instances via:
  - Random sampling from parameter ranges
  - Grid search over categorical axes
  - Mutation of high-scoring strategies (evolutionary search)

No production code is modified.
"""

from __future__ import annotations

import math
import random
from typing import Callable, List, Optional, Tuple

from model_lab.strategy_models.param_strategy import (
    ENTRY_POINTS,
    PARAM_RANGES,
    ROAD_TYPES,
    ParamStrategy,
)


# ---------------------------------------------------------------------------
# Random sampling
# ---------------------------------------------------------------------------

def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def sample_random(
    n: int,
    seed: Optional[int] = None,
    road_types: Optional[List[str]] = None,
    entry_points: Optional[List[str]] = None,
) -> List[ParamStrategy]:
    """
    Sample n strategies uniformly at random from the full parameter space.

    Args:
        n:            number of strategies to generate
        seed:         random seed for reproducibility
        road_types:   restrict to these road types (default: all four)
        entry_points: restrict to these entry points (default: all four)

    Returns:
        list of ParamStrategy
    """
    rng = random.Random(seed)
    rt_pool = road_types or ROAD_TYPES
    ep_pool = entry_points or ENTRY_POINTS
    strategies = []

    for _ in range(n):
        cont = {
            name: rng.uniform(lo, hi)
            for name, (lo, hi) in PARAM_RANGES.items()
        }
        strategies.append(ParamStrategy(
            road_type=rng.choice(rt_pool),
            entry_point=rng.choice(ep_pool),
            **cont,
        ))

    return strategies


def sample_grid(
    densities: Optional[List[float]] = None,
    road_widths: Optional[List[float]] = None,
    min_lot_areas: Optional[List[float]] = None,
    seed: Optional[int] = None,
) -> List[ParamStrategy]:
    """
    Systematic grid over key engine-connected parameters.

    Default grid:
        road_types     × 4 = 4
        entry_points   × 4 = 4   (one per cardinal direction)
        densities      × 3 = 3   (low/medium/high band centres)
        road_widths    × 3 = 3   (24, 32, 40 ft)
        min_lot_areas  × 3 = 3   (4000, 6000, 8000 sqft)

    Default total: 4 × 1 × 3 × 3 × 3 = 108  (entry_point fixed to north per combo)

    Pass explicit lists to override any axis.
    """
    rng = random.Random(seed)
    densities     = densities     or [3.0, 5.5, 9.0]
    road_widths   = road_widths   or [24.0, 32.0, 40.0]
    min_lot_areas = min_lot_areas or [4000.0, 6000.0, 8000.0]

    strategies = []
    for rt in ROAD_TYPES:
        for ep in ENTRY_POINTS[:1]:   # one entry point per topology in grid
            for density in densities:
                for rw in road_widths:
                    for mla in min_lot_areas:
                        # Fill remaining continuous params with defaults + small noise
                        noise = lambda lo, hi: rng.uniform(lo, hi)
                        s = ParamStrategy(
                            road_type=rt,
                            entry_point=ep,
                            road_width_ft=rw,
                            min_lot_area_sqft=mla,
                            min_frontage_ft=noise(40.0, 80.0),
                            min_depth_ft=noise(80.0, 140.0),
                            target_density_du_per_acre=density,
                            branch_count=noise(*PARAM_RANGES["branch_count"]),
                            branch_angle_deg=noise(*PARAM_RANGES["branch_angle_deg"]),
                            road_spacing_ft=noise(*PARAM_RANGES["road_spacing_ft"]),
                            loop_radius_ft=noise(*PARAM_RANGES["loop_radius_ft"]),
                            culdesac_radius_ft=noise(*PARAM_RANGES["culdesac_radius_ft"]),
                            culdesac_depth_ft=noise(*PARAM_RANGES["culdesac_depth_ft"]),
                            collector_length_ft=noise(*PARAM_RANGES["collector_length_ft"]),
                            orientation_angle_deg=noise(*PARAM_RANGES["orientation_angle_deg"]),
                        )
                        strategies.append(s)
    return strategies


# ---------------------------------------------------------------------------
# Mutation
# ---------------------------------------------------------------------------

def mutate_strategy(
    strategy: ParamStrategy,
    magnitude: float = 0.15,
    seed: Optional[int] = None,
    flip_categorical: float = 0.15,
) -> ParamStrategy:
    """
    Produce a mutated copy of a strategy.

    Continuous parameters are perturbed by ±magnitude fraction of their range.
    Categorical parameters (road_type, entry_point) flip with probability
    flip_categorical.

    Args:
        strategy:         source strategy to mutate
        magnitude:        fraction of each parameter's range to perturb (0.1 = ±10%)
        seed:             random seed
        flip_categorical: probability of flipping each categorical param

    Returns:
        new ParamStrategy
    """
    rng = random.Random(seed)

    def _perturb(val: float, name: str) -> float:
        lo, hi = PARAM_RANGES[name]
        span = hi - lo
        delta = rng.gauss(0, magnitude * span)
        return _clamp(val + delta, lo, hi)

    road_type = (
        rng.choice(ROAD_TYPES)
        if rng.random() < flip_categorical else strategy.road_type
    )
    entry_point = (
        rng.choice(ENTRY_POINTS)
        if rng.random() < flip_categorical else strategy.entry_point
    )

    return ParamStrategy(
        road_type=road_type,
        entry_point=entry_point,
        road_width_ft=_perturb(strategy.road_width_ft, "road_width_ft"),
        min_lot_area_sqft=_perturb(strategy.min_lot_area_sqft, "min_lot_area_sqft"),
        min_frontage_ft=_perturb(strategy.min_frontage_ft, "min_frontage_ft"),
        min_depth_ft=_perturb(strategy.min_depth_ft, "min_depth_ft"),
        target_density_du_per_acre=_perturb(
            strategy.target_density_du_per_acre, "target_density_du_per_acre"
        ),
        branch_count=_perturb(strategy.branch_count, "branch_count"),
        branch_angle_deg=_perturb(strategy.branch_angle_deg, "branch_angle_deg"),
        road_spacing_ft=_perturb(strategy.road_spacing_ft, "road_spacing_ft"),
        loop_radius_ft=_perturb(strategy.loop_radius_ft, "loop_radius_ft"),
        culdesac_radius_ft=_perturb(strategy.culdesac_radius_ft, "culdesac_radius_ft"),
        culdesac_depth_ft=_perturb(strategy.culdesac_depth_ft, "culdesac_depth_ft"),
        collector_length_ft=_perturb(strategy.collector_length_ft, "collector_length_ft"),
        orientation_angle_deg=_perturb(
            strategy.orientation_angle_deg, "orientation_angle_deg"
        ),
    )


def mutate_population(
    strategies: List[ParamStrategy],
    n_offspring: int,
    magnitude: float = 0.15,
    base_seed: int = 0,
) -> List[ParamStrategy]:
    """
    Mutate a list of strategies, producing n_offspring total offspring.
    Each parent produces roughly equal numbers of children.
    """
    offspring = []
    n_parents = len(strategies)
    if n_parents == 0:
        return []

    per_parent = max(1, n_offspring // n_parents)
    extra = n_offspring - per_parent * n_parents

    for i, parent in enumerate(strategies):
        count = per_parent + (1 if i < extra else 0)
        for j in range(count):
            child = mutate_strategy(parent, magnitude=magnitude, seed=base_seed + i * 1000 + j)
            offspring.append(child)

    return offspring[:n_offspring]


# ---------------------------------------------------------------------------
# Template strategies (baseline set for comparison)
# ---------------------------------------------------------------------------

def template_strategies() -> List[ParamStrategy]:
    """All original categorical template strategies as ParamStrategy."""
    results = []
    for rt in ROAD_TYPES:
        for density_goal in ["low", "medium", "high"]:
            for ep in ENTRY_POINTS:
                results.append(ParamStrategy.from_template(rt, ep, density_goal))
    return results


def generate_mixed_pool(
    n_random: int = 80,
    include_templates: bool = True,
    include_grid: bool = False,
    seed: Optional[int] = None,
) -> List[ParamStrategy]:
    """
    Generate a mixed strategy pool combining templates, grid, and random samples.

    Default: 48 templates + 80 random = 128 total
    """
    pool = []
    if include_templates:
        pool.extend(template_strategies())
    if include_grid:
        pool.extend(sample_grid(seed=seed))
    pool.extend(sample_random(n_random, seed=seed))
    return pool
