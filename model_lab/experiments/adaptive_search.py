"""
Adaptive Strategy Search — model_lab

Evolutionary search over parameterized strategy space.

Pipeline per generation:
  1. Candidate pool of N random ParamStrategies
  2. Pre-ranker (parcel + strategy features) selects top-k quickly
  3. Full simulation of top-k
  4. Best performers are mutated to seed next generation

Goal: discover strategies (especially road_width, density, zoning params)
that outperform the fixed categorical templates.

Usage:
    python model_lab/experiments/adaptive_search.py
    python model_lab/experiments/adaptive_search.py --generations 8 --pool-size 80 --top-k 20

No production code is modified.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# Search result types
# ---------------------------------------------------------------------------

@dataclass
class SearchCandidate:
    strategy: object          # ParamStrategy
    actual_score: float = 0.0
    predicted_score: float = 0.0
    simulated: bool = False


@dataclass
class GenerationResult:
    generation: int
    pool_size: int
    simulated: int
    best_score: float
    best_strategy: object
    improvement_over_baseline: float
    elapsed: float
    all_scores: List[float] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_default_parcel(area_acres: float = 10.0):
    """Return a (ParcelSample, polygon_geojson, area_sqft) tuple."""
    from model_lab.training.parcel_loader import ParcelSample
    w = (area_acres * 43560.0) ** 0.5
    polygon = {
        "type": "Polygon",
        "coordinates": [[
            [0.0, 0.0], [w, 0.0], [w, w], [0.0, w], [0.0, 0.0],
        ]],
    }
    area_sqft = area_acres * 43560.0
    parcel = ParcelSample(
        parcel_id="adaptive-eval",
        county=None, apn=None,
        area_sqft=area_sqft,
        geometry_geojson=polygon,
        is_geographic=False,
        source="synthetic",
    )
    return parcel, polygon, area_sqft


def _simulate_one(parcel, strategy) -> Optional[float]:
    """Run full layout + score. Returns overall_score or None."""
    try:
        from model_lab.training.layout_runner import run_layout_param
        from model_lab.training.layout_scoring import score_layout
        result = run_layout_param(parcel, strategy)
        if result is None:
            return None
        return score_layout(result.metrics).overall_score
    except Exception:
        return None


def _pre_rank(polygon: dict, area_sqft: float, strategies: list, top_k: int) -> list:
    """Use pre-ranker to pick top-k strategies (no simulation needed)."""
    try:
        from model_lab.strategy_models.pre_strategy_ranker import PreStrategyRanker
        ranker = PreStrategyRanker.load()
        strategy_dicts = [s.to_dict() for s in strategies]
        ranked = ranker.rank_strategies(polygon, area_sqft, strategy_dicts, top_n=top_k)
        # Map predictions back to original strategy objects
        result = []
        for pred in ranked:
            from model_lab.strategy_models.param_strategy import ParamStrategy
            result.append((ParamStrategy.from_dict(pred.strategy), pred.predicted_score))
        return result
    except Exception:
        # Fallback: no pre-ranking, return first top_k
        return [(s, 0.0) for s in strategies[:top_k]]


def _get_template_baseline(parcel, polygon, area_sqft) -> float:
    """Simulate all 48 categorical template strategies, return best score."""
    from model_lab.strategy_models.strategy_sampler import template_strategies
    templates = template_strategies()
    scores = []
    for s in templates:
        sc = _simulate_one(parcel, s)
        if sc is not None:
            scores.append(sc)
    return max(scores) if scores else 0.0


# ---------------------------------------------------------------------------
# Main search loop
# ---------------------------------------------------------------------------

def run_adaptive_search(
    generations:       int = 6,
    pool_size:         int = 80,
    top_k:             int = 20,
    n_elite:           int = 5,
    mutation_magnitude: float = 0.18,
    area_acres:        float = 10.0,
    seed:              int = 0,
    verbose:           bool = True,
) -> List[GenerationResult]:
    """
    Run evolutionary strategy search.

    Args:
        generations:  number of evolutionary rounds
        pool_size:    strategies per generation (random + mutants)
        top_k:        how many to simulate after pre-ranking
        n_elite:      top-N survivors that seed next generation
        mutation_magnitude: perturbation magnitude [0..1]
        area_acres:   test parcel size
        seed:         random seed

    Returns:
        list of GenerationResult, one per generation
    """
    from model_lab.strategy_models.strategy_sampler import (
        sample_random, mutate_population, template_strategies,
    )
    from model_lab.strategy_models.param_strategy import ParamStrategy

    parcel, polygon, area_sqft = _make_default_parcel(area_acres)

    if verbose:
        print("=" * 66)
        print("ADAPTIVE STRATEGY SEARCH")
        print(f"  Parcel: {area_acres:.0f} acres ({area_sqft/43560:.1f}ac square)")
        print(f"  Pool: {pool_size}  Top-K: {top_k}  Elite: {n_elite}  Generations: {generations}")
        print("=" * 66)

    # Baseline: templates
    if verbose:
        print(f"\n[Baseline] Simulating 48 template strategies...")
    t_base = time.perf_counter()
    baseline_score = _get_template_baseline(parcel, polygon, area_sqft)
    baseline_time  = time.perf_counter() - t_base
    if verbose:
        print(f"  Template best: {baseline_score:.4f}  ({baseline_time:.2f}s)")

    # Generation 0: pure random pool
    elites: List[ParamStrategy] = []
    results: List[GenerationResult] = []

    import random
    rng = random.Random(seed)

    for gen in range(generations):
        t0 = time.perf_counter()

        # Build pool: random sample + mutations of elites
        if elites:
            n_mutants = pool_size // 2
            n_fresh   = pool_size - n_mutants
            mutants   = mutate_population(elites, n_mutants, mutation_magnitude,
                                          base_seed=seed + gen * 10000)
            fresh     = sample_random(n_fresh, seed=rng.randint(0, 999999))
            pool      = mutants + fresh
        else:
            pool = sample_random(pool_size, seed=rng.randint(0, 999999))

        # Pre-rank to select top-k (no simulation)
        ranked_pairs = _pre_rank(polygon, area_sqft, pool, top_k)

        # Simulate top-k
        sim_results: List[Tuple[float, ParamStrategy]] = []
        for strategy, pred_score in ranked_pairs:
            sc = _simulate_one(parcel, strategy)
            if sc is not None:
                sim_results.append((sc, strategy))

        if not sim_results:
            if verbose:
                print(f"  Gen {gen+1}: no successful simulations")
            continue

        sim_results.sort(key=lambda x: x[0], reverse=True)
        best_score   = sim_results[0][0]
        best_strategy = sim_results[0][1]
        improvement  = best_score - baseline_score
        elapsed      = time.perf_counter() - t0

        # Update elites
        elites = [s for _, s in sim_results[:n_elite]]

        gen_result = GenerationResult(
            generation=gen + 1,
            pool_size=pool_size,
            simulated=len(sim_results),
            best_score=best_score,
            best_strategy=best_strategy,
            improvement_over_baseline=improvement,
            elapsed=elapsed,
            all_scores=[sc for sc, _ in sim_results],
        )
        results.append(gen_result)

        if verbose:
            marker = "★" if improvement > 0 else " "
            print(
                f"  Gen {gen+1:2d} {marker}  best={best_score:.4f}  "
                f"vs baseline={baseline_score:.4f}  "
                f"improvement={improvement:+.4f}  "
                f"({len(sim_results)} sims in {elapsed:.2f}s)"
            )
            bs = best_strategy
            print(
                f"         best: {bs.road_type}/{bs.density_goal()}  "
                f"road_w={bs.road_width_ft:.0f}ft  "
                f"min_lot={bs.min_lot_area_sqft:.0f}sqft  "
                f"density={bs.target_density_du_per_acre:.1f}du/ac"
            )

    # Final report
    if verbose and results:
        best_ever = max(results, key=lambda r: r.best_score)
        print(f"\n{'─'*66}")
        print(f"  ADAPTIVE SEARCH SUMMARY")
        print(f"{'─'*66}")
        print(f"  Template baseline:       {baseline_score:.4f}")
        print(f"  Best discovered:         {best_ever.best_score:.4f} (gen {best_ever.generation})")
        print(f"  Improvement:             {best_ever.improvement_over_baseline:+.4f}  "
              f"({best_ever.improvement_over_baseline/max(baseline_score,1e-9):.1%})")
        print(f"\n  Best strategy found:")
        bs = best_ever.best_strategy
        print(f"    road_type:                 {bs.road_type}")
        print(f"    entry_point:               {bs.entry_point}")
        print(f"    road_width_ft:             {bs.road_width_ft:.1f}")
        print(f"    min_lot_area_sqft:         {bs.min_lot_area_sqft:.0f}")
        print(f"    min_frontage_ft:           {bs.min_frontage_ft:.1f}")
        print(f"    min_depth_ft:              {bs.min_depth_ft:.1f}")
        print(f"    target_density_du_per_acre:{bs.target_density_du_per_acre:.2f}")
        print(f"\n  Generations that beat baseline: "
              f"{sum(1 for r in results if r.improvement_over_baseline > 0)}/{len(results)}")

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(
        description="Adaptive evolutionary strategy search.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--generations",          type=int,   default=6)
    parser.add_argument("--pool-size",            type=int,   default=80)
    parser.add_argument("--top-k",                type=int,   default=20)
    parser.add_argument("--n-elite",              type=int,   default=5)
    parser.add_argument("--mutation-magnitude",   type=float, default=0.18)
    parser.add_argument("--area-acres",           type=float, default=10.0)
    parser.add_argument("--seed",                 type=int,   default=0)
    args = parser.parse_args()

    run_adaptive_search(
        generations=args.generations,
        pool_size=args.pool_size,
        top_k=args.top_k,
        n_elite=args.n_elite,
        mutation_magnitude=args.mutation_magnitude,
        area_acres=args.area_acres,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
