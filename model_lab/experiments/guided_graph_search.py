"""
Guided Graph Search — model_lab Phase 8

Compares:
  A. Random graph proposals → topo-agnostic subdivision
  B. Graph-prior guided proposals → topo-agnostic subdivision

For both strategies, run N generations of evolutionary search.
Report:
  - best layout score achieved
  - score at each generation
  - total simulations run
  - efficiency: score / simulation count

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
# Data types
# ---------------------------------------------------------------------------

@dataclass
class GenerationResult:
    generation:    int
    n_simulated:   int
    best_score:    float
    best_type:     str
    elapsed:       float
    all_scores:    List[float] = field(default_factory=list)
    cumulative_sims: int = 0


@dataclass
class SearchResult:
    strategy:         str    # "random" or "guided"
    generations:      List[GenerationResult]
    best_score:       float
    total_sims:       int
    total_time:       float
    sims_to_baseline: Optional[int]   # sims needed to first beat baseline


# ---------------------------------------------------------------------------
# Parcel construction helpers
# ---------------------------------------------------------------------------

def _make_parcel_polygon(area_acres: float = 10.0, shape: str = "square"):
    """Return (parcel_geojson, parcel_polygon, area_sqft)."""
    from shapely.geometry import Polygon
    area_sqft = area_acres * 43560.0

    if shape == "square":
        side = area_sqft ** 0.5
        coords = [(0, 0), (side, 0), (side, side), (0, side), (0, 0)]
    elif shape == "rect":
        w = (area_sqft * 2) ** 0.5
        h = w / 2
        coords = [(0, 0), (w, 0), (w, h), (0, h), (0, 0)]
    elif shape == "l_shape":
        side = (area_sqft * 4 / 3) ** 0.5
        h = side * 0.5
        coords = [(0, 0), (side, 0), (side, h), (h, h), (h, side), (0, side), (0, 0)]
    else:
        side = area_sqft ** 0.5
        coords = [(0, 0), (side, 0), (side, side), (0, side), (0, 0)]

    geojson = {"type": "Polygon", "coordinates": [coords]}
    poly    = Polygon([(c[0], c[1]) for c in coords[:-1]])
    return geojson, poly, area_sqft


def _simulate(graph, parcel_polygon) -> Optional[Tuple[float, int, float]]:
    from model_lab.subdivision.subdivision_engine import (
        run_subdivision, score_subdivision_result,
    )
    try:
        result = run_subdivision(graph, parcel_polygon, road_width_ft=32.0)
        if result is None or result.lot_count == 0:
            return None
        return score_subdivision_result(result), result.lot_count, result.road_length_ft
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Single-strategy search loop
# ---------------------------------------------------------------------------

def _run_search(
    strategy:       str,           # "random" | "guided"
    parcel_geojson: dict,
    parcel_polygon,
    parcel_area_sqft: float,
    generations:    int,
    n_candidates:   int,
    top_n_elite:    int,
    seed:           int,
    baseline:       float,
    prior=None,
    sim_fraction:   float = 1.0,   # guided: fraction of pool to actually simulate
    verbose:        bool = True,
) -> SearchResult:
    """
    Run a single evolutionary search strategy.

    For 'guided' strategy:
      - Fresh candidates are type-distribution guided (via prior)
      - The mutation pool is oversampled (1/sim_fraction × n_candidates),
        scored by prior, and only the top fraction are sent to simulation.
        This is the key efficiency gain: prior screens mutations cheaply
        before the expensive simulation step.
    """
    from model_lab.graph_models.graph_generator import generate_graph_candidates
    from model_lab.graph_models.graph_mutation  import mutate_population
    from model_lab.graph_models.graph_prior     import generate_guided_graphs

    all_gen_results: List[GenerationResult] = []
    elite_graphs = []
    total_sims  = 0
    sims_to_baseline: Optional[int] = None
    best_ever = 0.0
    t_total = time.perf_counter()

    for gen in range(generations):
        t0 = time.perf_counter()

        if strategy == "guided" and prior is not None:
            # --- Guided: oversample then prior-filter ---
            oversample = max(1, int(1.0 / sim_fraction))

            if elite_graphs:
                n_mutants_full = n_candidates * oversample * 2 // 3
                n_fresh_full   = n_candidates * oversample - n_mutants_full
                mutants_full   = mutate_population(elite_graphs, n_mutants_full,
                                                   magnitude=40.0, n_ops=2,
                                                   base_seed=seed + gen * 10000)
                fresh_full     = generate_guided_graphs(
                    parcel_geojson=parcel_geojson,
                    parcel_area_sqft=parcel_area_sqft,
                    n_final=n_fresh_full,
                    n_pool=n_fresh_full * 4,
                    seed=seed + gen * 777,
                    prior=prior,
                )
                oversized_pool = mutants_full + fresh_full
            else:
                oversized_pool = generate_guided_graphs(
                    parcel_geojson=parcel_geojson,
                    parcel_area_sqft=parcel_area_sqft,
                    n_final=n_candidates * oversample,
                    n_pool=n_candidates * oversample * 4,
                    seed=seed,
                    prior=prior,
                )

            # Score pool with prior (free), keep only top n_candidates
            if len(oversized_pool) > n_candidates:
                ranked = prior.rank_graphs(oversized_pool, parcel_geojson, parcel_area_sqft)
                all_graphs = [p.graph for p in ranked[:n_candidates]]
            else:
                all_graphs = oversized_pool

        else:
            # --- Random: standard pool ---
            if elite_graphs:
                n_mutants = n_candidates * 2 // 3
                n_fresh   = n_candidates - n_mutants
                mutants   = mutate_population(elite_graphs, n_mutants,
                                              magnitude=40.0, n_ops=2,
                                              base_seed=seed + gen * 10000)
                fresh     = generate_graph_candidates(
                    parcel_geojson=parcel_geojson,
                    parcel_area_sqft=parcel_area_sqft,
                    n=n_fresh, seed=seed + gen * 777,
                )
                all_graphs = mutants + fresh
            else:
                all_graphs = generate_graph_candidates(
                    parcel_geojson=parcel_geojson,
                    parcel_area_sqft=parcel_area_sqft,
                    n=n_candidates, seed=seed,
                )

        # --- Simulate (the expensive step) ---
        scored: List[Tuple[float, object]] = []
        for g in all_graphs:
            res = _simulate(g, parcel_polygon)
            if res:
                sc, lots, rlen = res
                scored.append((sc, g))
                total_sims += 1
                if sc > baseline and sims_to_baseline is None:
                    sims_to_baseline = total_sims

        if not scored:
            continue

        scored.sort(key=lambda x: x[0], reverse=True)
        best_score = scored[0][0]
        best_type  = scored[0][1].generator_type
        best_ever  = max(best_ever, best_score)
        elite_graphs = [g for _, g in scored[:top_n_elite]]

        gen_result = GenerationResult(
            generation=gen + 1,
            n_simulated=len(scored),
            best_score=best_score,
            best_type=best_type,
            elapsed=time.perf_counter() - t0,
            all_scores=[sc for sc, _ in scored],
            cumulative_sims=total_sims,
        )
        all_gen_results.append(gen_result)

        if verbose:
            marker = "★" if best_score > baseline else " "
            print(f"    Gen {gen+1:2d}{marker} best={best_score:.4f}  "
                  f"type={best_type:12s}  sims={len(scored)}/{len(all_graphs)}  "
                  f"cumul={total_sims}  ({gen_result.elapsed:.2f}s)")

    return SearchResult(
        strategy=strategy,
        generations=all_gen_results,
        best_score=best_ever,
        total_sims=total_sims,
        total_time=time.perf_counter() - t_total,
        sims_to_baseline=sims_to_baseline,
    )


# ---------------------------------------------------------------------------
# Main comparison
# ---------------------------------------------------------------------------

def run_guided_comparison(
    area_acres:    float = 10.0,
    parcel_shape:  str   = "square",
    generations:   int   = 8,
    n_candidates:  int   = 24,
    top_n_elite:   int   = 6,
    seed:          int   = 0,
    verbose:       bool  = True,
) -> Tuple[SearchResult, SearchResult]:
    """
    Run both random and guided search on the same parcel.

    Returns:
        (random_result, guided_result)
    """
    from model_lab.experiments.graph_search import _template_baseline
    from model_lab.training.parcel_loader import ParcelSample
    from model_lab.graph_models.graph_prior import GraphPrior

    geojson, poly, area_sqft = _make_parcel_polygon(area_acres, parcel_shape)

    if verbose:
        print("=" * 68)
        print("GUIDED vs RANDOM GRAPH SEARCH (Phase 8)")
        print(f"  Parcel: {area_acres:.0f} acres ({parcel_shape})  "
              f"Gens: {generations}  Pool: {n_candidates}  Seed: {seed}")
        print("=" * 68)

    # Template baseline
    if verbose:
        print("\n[Baseline] Template strategies...")
    parcel_sample = ParcelSample(
        "guided-eval", None, None, area_sqft, geojson, False, "synthetic")
    baseline = _template_baseline(parcel_sample, area_sqft)
    if verbose:
        print(f"  Template baseline: {baseline:.4f}")

    # Load prior once
    try:
        prior = GraphPrior.load()
        if verbose:
            print(f"  Graph prior loaded.")
    except Exception as e:
        prior = None
        if verbose:
            print(f"  WARNING: could not load graph prior: {e}")

    # Random search
    if verbose:
        print(f"\n[Random] {generations} generations × {n_candidates} candidates...")
    random_result = _run_search(
        strategy="random",
        parcel_geojson=geojson,
        parcel_polygon=poly,
        parcel_area_sqft=area_sqft,
        generations=generations,
        n_candidates=n_candidates,
        top_n_elite=top_n_elite,
        seed=seed,
        baseline=baseline,
        prior=None,
        verbose=verbose,
    )

    # Guided search: generate 2× candidates, screen with prior, simulate top half
    if verbose:
        print(f"\n[Guided] {generations} generations × {n_candidates} candidates "
              f"(2× oversample + prior filter)...")
    guided_result = _run_search(
        strategy="guided",
        parcel_geojson=geojson,
        parcel_polygon=poly,
        parcel_area_sqft=area_sqft,
        generations=generations,
        n_candidates=n_candidates,
        top_n_elite=top_n_elite,
        seed=seed,
        baseline=baseline,
        prior=prior,
        sim_fraction=0.5,   # generate 2×, prior-filter to 1×, simulate 1×
        verbose=verbose,
    )

    # Summary
    if verbose:
        print(f"\n{'─'*68}")
        print("COMPARISON SUMMARY")
        print(f"{'─'*68}")
        print(f"  {'Strategy':10s}  {'Best Score':>10s}  {'vs Baseline':>12s}  "
              f"{'Total Sims':>10s}  {'Sims→Baseline':>13s}  {'Time':>6s}")
        print(f"  {'─'*10}  {'─'*10}  {'─'*12}  {'─'*10}  {'─'*13}  {'─'*6}")

        for res, label in [(random_result, "Random"), (guided_result, "Guided")]:
            pct  = (res.best_score - baseline) / max(baseline, 1e-9)
            stb  = str(res.sims_to_baseline) if res.sims_to_baseline else "never"
            print(f"  {label:10s}  {res.best_score:10.4f}  {pct:+12.1%}  "
                  f"{res.total_sims:10d}  {stb:>13s}  {res.total_time:5.1f}s")

        if (random_result.sims_to_baseline and guided_result.sims_to_baseline
                and guided_result.sims_to_baseline < random_result.sims_to_baseline):
            reduction = 1.0 - guided_result.sims_to_baseline / random_result.sims_to_baseline
            print(f"\n  Guided search reached baseline {reduction:.0%} fewer simulations.")
        elif guided_result.best_score > random_result.best_score:
            improvement = (guided_result.best_score - random_result.best_score) / \
                          max(random_result.best_score, 1e-9)
            print(f"\n  Guided search improved best score by {improvement:.1%}.")

    return random_result, guided_result


def run_multi_parcel_comparison(
    parcel_configs: Optional[List[dict]] = None,
    generations:    int = 6,
    n_candidates:   int = 24,
    seed:           int = 0,
    verbose:        bool = True,
) -> None:
    """
    Run guided vs random comparison across multiple parcel types.
    Aggregates results to show average improvement.
    """
    if parcel_configs is None:
        parcel_configs = [
            {"area_acres": 5.0,  "shape": "square"},
            {"area_acres": 10.0, "shape": "square"},
            {"area_acres": 10.0, "shape": "rect"},
            {"area_acres": 15.0, "shape": "l_shape"},
            {"area_acres": 20.0, "shape": "rect"},
        ]

    print(f"\n{'='*68}")
    print("MULTI-PARCEL GUIDED vs RANDOM COMPARISON")
    print(f"{'='*68}")
    print(f"  {len(parcel_configs)} parcel types  "
          f"{generations} gens × {n_candidates} candidates\n")

    rows = []
    for cfg in parcel_configs:
        area   = cfg["area_acres"]
        shape  = cfg["shape"]
        print(f"  ── {area:.0f}ac {shape} ─────────────────────────────────────")
        rand_r, guid_r = run_guided_comparison(
            area_acres=area,
            parcel_shape=shape,
            generations=generations,
            n_candidates=n_candidates,
            seed=seed,
            verbose=False,  # suppress per-gen output
        )
        rows.append({
            "parcel": f"{area:.0f}ac {shape}",
            "random_score": rand_r.best_score,
            "guided_score": guid_r.best_score,
            "random_sims":  rand_r.total_sims,
            "guided_sims":  guid_r.total_sims,
            "rand_stb":     rand_r.sims_to_baseline,
            "guid_stb":     guid_r.sims_to_baseline,
        })
        delta = guid_r.best_score - rand_r.best_score
        pct   = delta / max(rand_r.best_score, 1e-9)
        print(f"  Random: {rand_r.best_score:.4f}  Guided: {guid_r.best_score:.4f}  "
              f"Δ={delta:+.4f} ({pct:+.1%})  "
              f"Sims: {rand_r.total_sims} vs {guid_r.total_sims}")

    # Aggregate
    print(f"\n{'─'*68}")
    print("AGGREGATE RESULTS")
    print(f"{'─'*68}")
    print(f"  {'Parcel':18s}  {'Random':>8s}  {'Guided':>8s}  {'Δ Score':>8s}  {'Sims Rand':>9s}  {'Sims Guid':>9s}")
    print(f"  {'─'*18}  {'─'*8}  {'─'*8}  {'─'*8}  {'─'*9}  {'─'*9}")
    for r in rows:
        delta = r["guided_score"] - r["random_score"]
        print(f"  {r['parcel']:18s}  {r['random_score']:8.4f}  {r['guided_score']:8.4f}  "
              f"{delta:+8.4f}  {r['random_sims']:9d}  {r['guided_sims']:9d}")

    avg_rand  = sum(r["random_score"] for r in rows) / len(rows)
    avg_guid  = sum(r["guided_score"] for r in rows) / len(rows)
    avg_sims_r = sum(r["random_sims"] for r in rows) / len(rows)
    avg_sims_g = sum(r["guided_sims"] for r in rows) / len(rows)
    print(f"  {'AVERAGE':18s}  {avg_rand:8.4f}  {avg_guid:8.4f}  "
          f"{avg_guid-avg_rand:+8.4f}  {avg_sims_r:9.0f}  {avg_sims_g:9.0f}")

    # Sim reduction analysis
    stb_pairs = [(r["rand_stb"], r["guid_stb"]) for r in rows
                 if r["rand_stb"] and r["guid_stb"]]
    if stb_pairs:
        reductions = [1.0 - g/r for r, g in stb_pairs if r > 0]
        avg_red = sum(reductions) / len(reductions)
        print(f"\n  Average simulation reduction to reach baseline: {avg_red:.0%}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--mode",       choices=["single", "multi"], default="single")
    parser.add_argument("--area-acres", type=float, default=10.0)
    parser.add_argument("--shape",      default="square")
    parser.add_argument("--generations", type=int, default=8)
    parser.add_argument("--n-candidates", type=int, default=24)
    parser.add_argument("--seed",       type=int, default=0)
    args = parser.parse_args()

    if args.mode == "multi":
        run_multi_parcel_comparison(
            generations=args.generations,
            n_candidates=args.n_candidates,
            seed=args.seed,
        )
    else:
        run_guided_comparison(
            area_acres=args.area_acres,
            parcel_shape=args.shape,
            generations=args.generations,
            n_candidates=args.n_candidates,
            seed=args.seed,
        )
