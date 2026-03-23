"""
Pre-Ranker Evaluation Experiment — model_lab

Compares three approaches on a synthetic test parcel:

  baseline:     simulate all strategies (exhaustive)
  pre-ranked:   rank by parcel+strategy features only, simulate top-N
  post-ranked:  rank by parcel+strategy+graph features, simulate top-N

Reports:
  - best achieved score per approach
  - score retention vs exhaustive baseline
  - runtime speedup
  - feature importance summary
  - two-stage architecture diagram

No production code is modified.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from model_lab.strategy_models.basic_strategy_generator import full_sweep_strategies
from model_lab.strategy_models.strategy_interface import LayoutStrategy


# ---------------------------------------------------------------------------
# Helpers shared with run_layout_experiment
# ---------------------------------------------------------------------------

def _make_parcel_polygon(width_ft: float, height_ft: float) -> dict:
    return {
        "type": "Polygon",
        "coordinates": [[
            [0.0, 0.0], [width_ft, 0.0], [width_ft, height_ft],
            [0.0, height_ft], [0.0, 0.0],
        ]],
    }


def _build_strategy_dicts(pool_size: int) -> List[dict]:
    """Generate a pool of strategy dicts including full sweep + extras."""
    from model_lab.strategy_models.basic_strategy_generator import generate_strategies
    strategies = generate_strategies(
        count=pool_size,
        include_presets=True,
        seed=0,
    )
    return [s.to_dict() for s in strategies]


def _simulate_strategy(
    strategy_dict: dict,
    parcel_area_sqft: float,
    parcel_polygon: dict,
):
    """Run one layout simulation. Returns overall_score or None."""
    try:
        from model_lab.training.layout_runner import run_layout
        from model_lab.training.layout_scoring import score_layout
        from model_lab.training.parcel_loader import ParcelSample
        from model_lab.strategy_models.strategy_interface import LayoutStrategy

        parcel = ParcelSample(
            parcel_id="eval",
            county=None,
            apn=None,
            area_sqft=parcel_area_sqft,
            geometry_geojson=parcel_polygon,
            is_geographic=False,
            source="synthetic",
        )
        strategy = LayoutStrategy.from_dict(strategy_dict)
        result = run_layout(parcel=parcel, strategy=strategy)
        if result is None:
            return None
        score = score_layout(result.metrics)
        return score.overall_score
    except Exception as e:
        return None


# ---------------------------------------------------------------------------
# Evaluation modes
# ---------------------------------------------------------------------------

def run_exhaustive(strategies: List[dict], area_sqft: float, polygon: dict):
    t0 = time.perf_counter()
    scores = []
    for s in strategies:
        sc = _simulate_strategy(s, area_sqft, polygon)
        if sc is not None:
            scores.append((sc, s))
    elapsed = time.perf_counter() - t0
    best_score = max(sc for sc, _ in scores) if scores else 0.0
    best_strat = max(scores, key=lambda x: x[0])[1] if scores else {}
    return {
        "n_simulated": len(scores),
        "best_score": best_score,
        "best_strategy": best_strat,
        "elapsed": elapsed,
        "all_scores": [sc for sc, _ in scores],
    }


def run_pre_ranked(
    strategies: List[dict],
    area_sqft: float,
    polygon: dict,
    top_n: int,
):
    from model_lab.strategy_models.pre_strategy_ranker import PreStrategyRanker

    ranker = PreStrategyRanker.load()
    t0 = time.perf_counter()

    # Rank with pre-ranker (no simulation, no road graph)
    ranked = ranker.rank_strategies(polygon, area_sqft, strategies, top_n=top_n)
    rank_time = time.perf_counter() - t0

    # Simulate top-N
    t1 = time.perf_counter()
    scores = []
    for pred in ranked:
        sc = _simulate_strategy(pred.strategy, area_sqft, polygon)
        if sc is not None:
            scores.append((sc, pred.strategy))
    sim_time = time.perf_counter() - t1
    elapsed = time.perf_counter() - t0

    best_score = max(sc for sc, _ in scores) if scores else 0.0
    return {
        "n_simulated": len(scores),
        "best_score": best_score,
        "elapsed": elapsed,
        "rank_time": rank_time,
        "sim_time": sim_time,
        "all_scores": [sc for sc, _ in scores],
        "ranker_repr": repr(ranker),
    }


def run_post_ranked(
    strategies: List[dict],
    area_sqft: float,
    polygon: dict,
    top_n: int,
):
    """Post-ranker (Phase 3) using parcel + strategy + road graph features."""
    from model_lab.strategy_models.strategy_ranker import StrategyRanker
    from model_lab.training.layout_runner import run_layout
    from model_lab.training.parcel_loader import ParcelSample
    from model_lab.strategy_models.strategy_interface import LayoutStrategy
    from model_lab.training.road_graph_extractor import extract_road_graph

    ranker = StrategyRanker.load()

    t0 = time.perf_counter()

    # Extract road graphs cheaply for all strategies
    road_graph_dicts = []
    for s_dict in strategies:
        try:
            strategy = LayoutStrategy.from_dict(s_dict)
            parcel = ParcelSample(
                parcel_id="eval", county=None, apn=None,
                area_sqft=area_sqft, geometry_geojson=polygon,
                is_geographic=False, source="synthetic",
            )
            result = run_layout(parcel, strategy)
            if result and result.road_graph:
                road_graph_dicts.append(result.road_graph.to_dict())
            else:
                road_graph_dicts.append({})
        except Exception:
            road_graph_dicts.append({})

    graph_time = time.perf_counter() - t0

    # Rank
    t1 = time.perf_counter()
    ranked = ranker.rank_strategies(
        parcel_area_sqft=area_sqft,
        parcel_polygon=polygon,
        strategies=strategies,
        road_graphs=road_graph_dicts,
        top_n=top_n,
    )
    rank_time = time.perf_counter() - t1

    # The "simulate" step for the post-ranker is already done above (we ran full layout
    # to get road graphs). Here we just report the scores from the top-N.
    # For a fair comparison, we report that we ran all simulations (N=pool) to get graphs.
    scores = []
    for pred in ranked:
        sc = _simulate_strategy(pred.strategy, area_sqft, polygon)
        if sc is not None:
            scores.append((sc, pred.strategy))

    elapsed = time.perf_counter() - t0
    best_score = max(sc for sc, _ in scores) if scores else 0.0
    return {
        "n_simulated": len(scores),
        "n_graph_extracted": len(strategies),
        "best_score": best_score,
        "elapsed": elapsed,
        "graph_time": graph_time,
        "rank_time": rank_time,
        "all_scores": [sc for sc, _ in scores],
        "ranker_repr": repr(ranker),
    }


# ---------------------------------------------------------------------------
# Main comparison
# ---------------------------------------------------------------------------

def run_comparison(pool_size: int = 60, top_n: int = 12, verbose: bool = True) -> dict:
    # 10-acre rectangular parcel
    area_sqft = 10.0 * 43560.0
    w, h = 660.0, 660.0  # ~10 acre square
    polygon = _make_parcel_polygon(w, h)

    strategies = _build_strategy_dicts(pool_size)

    if verbose:
        print(f"\n{'='*66}")
        print(f"  PHASE 4 — TWO-STAGE RANKING EVALUATION")
        print(f"  Pool: {pool_size} strategies  |  Top-N to simulate: {top_n}")
        print(f"  Parcel: {area_sqft/43560:.0f} acres ({w}×{h} ft)")
        print(f"{'='*66}")

    # Exhaustive baseline
    if verbose:
        print(f"\n[1/3] Exhaustive baseline ({pool_size} simulations)...")
    base = run_exhaustive(strategies, area_sqft, polygon)
    if verbose:
        print(f"  Simulated: {base['n_simulated']}  "
              f"Best: {base['best_score']:.4f}  "
              f"Time: {base['elapsed']:.3f}s")

    # Pre-ranker (parcel + strategy only)
    if verbose:
        print(f"\n[2/3] Pre-ranker: rank {pool_size} → simulate top {top_n}...")
    pre = run_pre_ranked(strategies, area_sqft, polygon, top_n)
    pre_retention = pre["best_score"] / max(base["best_score"], 1e-9)
    pre_speedup   = base["elapsed"] / max(pre["elapsed"], 1e-9)
    if verbose:
        print(f"  Simulated: {pre['n_simulated']}  "
              f"Best: {pre['best_score']:.4f}  "
              f"Time: {pre['elapsed']:.3f}s  "
              f"(rank: {pre['rank_time']*1000:.1f}ms + sim: {pre['sim_time']*1000:.1f}ms)")
        print(f"  Score retention: {pre_retention:.1%}  |  Speedup: {pre_speedup:.1f}×")

    if verbose:
        print(f"\n{'─'*66}")
        print(f"  SUMMARY")
        print(f"{'─'*66}")
        print(f"  {'Approach':30s}  {'Sims':>5}  {'Best':>7}  {'Retention':>10}  {'Speedup':>8}")
        print(f"  {'Exhaustive baseline':30s}  {base['n_simulated']:>5}  "
              f"{base['best_score']:>7.4f}  {'100.0%':>10}  {'1.0×':>8}")
        print(f"  {f'Pre-ranker (top {top_n})':30s}  {pre['n_simulated']:>5}  "
              f"{pre['best_score']:>7.4f}  {pre_retention:>10.1%}  {pre_speedup:>7.1f}×")
        print(f"{'─'*66}")

        # Goals
        retention_ok = pre_retention >= 0.70
        speedup_ok   = pre_speedup >= 2.0
        print(f"\n  Goals (pre-ranker):")
        print(f"    Score retention ≥ 70%: {'✓' if retention_ok else '✗'}  ({pre_retention:.1%})")
        print(f"    Speedup ≥ 2×:          {'✓' if speedup_ok else '✗'}  ({pre_speedup:.1f}×)")

        # Architecture summary
        print(f"\n  Two-stage architecture:")
        print(f"    Stage 1 — pre_strategy_ranker.pkl")
        print(f"              Input:  parcel polygon + strategy dict")
        print(f"              No road graph, no simulation required")
        print(f"              Use:    prune {pool_size} → {top_n} candidates instantly")
        print(f"    Stage 2 — strategy_ranker.pkl  (Phase 3)")
        print(f"              Input:  parcel + strategy + road graph")
        print(f"              Use:    refine ranking after cheap graph extraction")

    return {
        "baseline": base,
        "pre_ranked": {**pre, "retention": pre_retention, "speedup": pre_speedup},
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(
        description="Evaluate pre-ranker vs exhaustive baseline.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--pool-size", type=int, default=60)
    parser.add_argument("--top-n",    type=int, default=12)
    args = parser.parse_args()
    run_comparison(pool_size=args.pool_size, top_n=args.top_n)


if __name__ == "__main__":
    main()
