"""
Basic Strategy Generator — model_lab

Generates LayoutStrategy instances with either:
  - fixed preset strategies (for deterministic sweeps)
  - randomised strategies (for high-volume stochastic dataset generation)

No production code is modified.
"""

from __future__ import annotations

import random
from typing import List, Optional

from model_lab.strategy_models.strategy_interface import (
    DensityGoal,
    EntryPoint,
    LayoutStrategy,
    RoadType,
)

# ---------------------------------------------------------------------------
# All possible values per dimension
# ---------------------------------------------------------------------------

ALL_ROAD_TYPES: List[RoadType] = ["loop", "spine", "parallel", "culdesac"]
ALL_ENTRY_POINTS: List[EntryPoint] = ["north", "south", "east", "west"]
ALL_DENSITY_GOALS: List[DensityGoal] = ["low", "medium", "high"]

# ---------------------------------------------------------------------------
# Fixed presets (deterministic — used for the first pass of every parcel)
# ---------------------------------------------------------------------------

PRESET_STRATEGIES: List[LayoutStrategy] = [
    LayoutStrategy(road_type="loop",     entry_point="south", culdesac_count=0, density_goal="medium"),
    LayoutStrategy(road_type="spine",    entry_point="south", culdesac_count=0, density_goal="medium"),
    LayoutStrategy(road_type="parallel", entry_point="south", culdesac_count=0, density_goal="high"),
    LayoutStrategy(road_type="culdesac", entry_point="south", culdesac_count=1, density_goal="low"),
]


def preset_strategies() -> List[LayoutStrategy]:
    """Return the four canonical preset strategies (deterministic, no randomness)."""
    return list(PRESET_STRATEGIES)


# ---------------------------------------------------------------------------
# Random strategy generation
# ---------------------------------------------------------------------------

def random_strategy(rng: Optional[random.Random] = None) -> LayoutStrategy:
    """
    Generate a single randomised layout strategy.

    culdesac_count is only meaningful when road_type == "culdesac" but is
    always populated so the schema stays consistent.
    """
    r = rng or random
    road_type: RoadType = r.choice(ALL_ROAD_TYPES)
    entry_point: EntryPoint = r.choice(ALL_ENTRY_POINTS)
    density_goal: DensityGoal = r.choice(ALL_DENSITY_GOALS)
    culdesac_count = r.randint(0, 3) if road_type == "culdesac" else 0
    return LayoutStrategy(
        road_type=road_type,
        entry_point=entry_point,
        culdesac_count=culdesac_count,
        density_goal=density_goal,
    )


def generate_strategies(
    count: int,
    include_presets: bool = True,
    seed: Optional[int] = None,
) -> List[LayoutStrategy]:
    """
    Generate a mix of preset + random strategies.

    Args:
        count: Total number of strategies to return.
        include_presets: Whether to always include the 4 canonical presets first.
        seed: Optional RNG seed for reproducibility.
    """
    rng = random.Random(seed)
    strategies: List[LayoutStrategy] = []

    if include_presets:
        strategies.extend(PRESET_STRATEGIES)

    remaining = count - len(strategies)
    for _ in range(max(0, remaining)):
        strategies.append(random_strategy(rng))

    return strategies[:count]


# ---------------------------------------------------------------------------
# Full-coverage sweep — one strategy per road type × density combo
# ---------------------------------------------------------------------------

def full_sweep_strategies() -> List[LayoutStrategy]:
    """
    Return one strategy per (road_type × density_goal) combination.
    Useful for exhaustive per-parcel evaluation (12 strategies total).
    """
    strategies = []
    for road_type in ALL_ROAD_TYPES:
        for density in ALL_DENSITY_GOALS:
            strategies.append(
                LayoutStrategy(
                    road_type=road_type,
                    entry_point="south",
                    culdesac_count=1 if road_type == "culdesac" else 0,
                    density_goal=density,
                )
            )
    return strategies
