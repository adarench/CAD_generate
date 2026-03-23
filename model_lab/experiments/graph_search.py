"""
Graph Search Experiment — model_lab

Evolutionary search over the road graph proposal space.

Pipeline
--------
1. Generate N graph candidates (all 6 generator types)
2. Convert each to StreetNetworkCandidate
3. Simulate via production layout engine
4. Score and rank results
5. Mutate top performers → next generation
6. Repeat for several generations

Also runs a comparison between:
  - Template strategies (baseline)
  - Parameterized strategies (Phase 5)
  - Graph proposals (Phase 6)

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
class GraphCandidate:
    graph:           object        # ProposedGraph
    candidate:       object        # StreetNetworkCandidate (may be None)
    score:           Optional[float] = None
    lot_count:       int = 0
    road_length_ft:  float = 0.0


@dataclass
class SearchGeneration:
    generation:    int
    n_generated:   int
    n_converted:   int
    n_simulated:   int
    best_score:    float
    best_type:     str
    elapsed:       float
    all_scores:    List[float] = field(default_factory=list)
    improvement:   float = 0.0


# ---------------------------------------------------------------------------
# Parcel helpers
# ---------------------------------------------------------------------------

def _make_parcel(area_acres: float = 10.0):
    from model_lab.training.parcel_loader import ParcelSample
    side = (area_acres * 43560.0) ** 0.5
    polygon = {"type": "Polygon", "coordinates": [
        [[0.0, 0.0], [side, 0.0], [side, side], [0.0, side], [0.0, 0.0]]
    ]}
    area_sqft = area_acres * 43560.0
    parcel = ParcelSample("graph-eval", None, None, area_sqft, polygon, False, "synthetic")
    return parcel, polygon, area_sqft


# ---------------------------------------------------------------------------
# Single simulation using a graph candidate
# ---------------------------------------------------------------------------

def _simulate_graph_candidate_topo(
    graph,
    parcel_polygon,         # shapely Polygon
    road_width_ft: float = 32.0,
    min_frontage_ft: float = 50.0,
    min_lot_area_sqft: float = 4000.0,
    min_depth_ft: float = 80.0,
    lot_depth: float = 110.0,
) -> Optional[Tuple[float, int, float]]:
    """
    Simulate using the topology-agnostic subdivision engine (Phase 7).

    Returns (overall_score, lot_count, road_length_ft) or None on failure.
    """
    try:
        from model_lab.subdivision.subdivision_engine import (
            run_subdivision, score_subdivision_result,
        )
        result = run_subdivision(
            graph_or_centerlines=graph,
            parcel_polygon=parcel_polygon,
            road_width_ft=road_width_ft,
            lot_depth=lot_depth,
            min_frontage_ft=min_frontage_ft,
            min_lot_area_sqft=min_lot_area_sqft,
            min_depth_ft=min_depth_ft,
        )
        if result is None or result.lot_count == 0:
            return None
        score = score_subdivision_result(result)
        return score, result.lot_count, result.road_length_ft
    except Exception:
        return None


def _simulate_graph_candidate(
    parcel,
    candidate,
    zoning,
    target_lots: int,
) -> Optional[Tuple[float, int, float]]:
    """
    Run generate_subdivision with a custom graph candidate.

    Returns (overall_score, lot_count, road_length_ft) or None on failure.
    """
    try:
        from ai_subdivision.constraints import (
            Easement, Lots, Parcel, Road, SubdivisionConstraints
        )
        from ai_subdivision.geometry import parcel_shapely_from_constraints
        from ai_subdivision.subdivision import generate_subdivision, summarize_layout
        from model_lab.training.layout_runner import (
            _extract_exterior_ring, _geographic_to_feet,
        )
        from model_lab.training.layout_scoring import score_layout, LayoutScore
        from model_lab.training.layout_runner import _extract_exterior_ring

        ring = _extract_exterior_ring(parcel.geometry_geojson)
        boundary_ft = [(float(c[0]), float(c[1])) for c in ring]

        constraints = SubdivisionConstraints(
            parcel=Parcel(shape="polygon", boundary=boundary_ft),
            lots=Lots(count=target_lots),
            road=Road(orientation=candidate.orientation,
                      width_ft=candidate.metadata.get("road_width_ft", 32.0)),
            easement=Easement(width_ft=10.0),
        )

        layout = generate_subdivision(
            constraints=constraints,
            zoning_rules=zoning,
            street_network=candidate,
            target_lot_count=target_lots,
        )
        summary = summarize_layout(constraints, zoning, layout)
        lot_count  = summary["generated_lot_count"]
        road_len   = float(summary["road_length_ft"])
        dev_area   = float(summary["developable_area_sqft"])

        yield_sc = lot_count / 40.0
        eff_sc   = (dev_area / max(road_len, 1)) / 200.0
        overall  = 0.6 * yield_sc + 0.4 * eff_sc

        return overall, lot_count, road_len
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Baseline: template strategies
# ---------------------------------------------------------------------------

def _template_baseline(parcel, area_sqft: float, road_width: float = 40.0) -> float:
    from model_lab.strategy_models.strategy_sampler import template_strategies
    from model_lab.training.layout_runner import run_layout_param

    from model_lab.training.layout_scoring import score_layout
    best = 0.0
    for s in template_strategies():
        try:
            result = run_layout_param(parcel, s)
            if result:
                sc = score_layout(result.metrics).overall_score
                best = max(best, sc)
        except Exception:
            pass
    return best


# ---------------------------------------------------------------------------
# Graph search
# ---------------------------------------------------------------------------

def run_graph_search(
    generations: int = 5,
    n_candidates: int = 36,
    top_n_elite: int = 6,
    area_acres: float = 10.0,
    road_width_ft: float = 32.0,
    target_density_du_per_ac: float = 6.0,
    seed: int = 0,
    verbose: bool = True,
) -> List[SearchGeneration]:
    from model_lab.graph_models.graph_generator import generate_graph_candidates
    from model_lab.graph_models.graph_mutation import mutate_population
    from model_lab.graph_models.graph_to_strategy import graphs_to_candidates
    from ai_subdivision.zoning import ZoningRules

    parcel, polygon_geojson, area_sqft = _make_parcel(area_acres)
    target_lots = max(4, int(area_sqft / 43560.0 * target_density_du_per_ac))
    zoning = ZoningRules(min_frontage_ft=40.0, min_depth_ft=80.0, min_area_sqft=4000.0)

    if verbose:
        print("=" * 66)
        print("GRAPH SEARCH — EVOLUTIONARY ROAD NETWORK EXPLORATION")
        print(f"  Parcel: {area_acres:.0f} acres   "
              f"Target density: {target_density_du_per_ac:.0f} du/ac  "
              f"Target lots: {target_lots}")
        print(f"  Pool: {n_candidates}  Elite: {top_n_elite}  Generations: {generations}")
        print("=" * 66)

    # Baseline
    if verbose:
        print(f"\n[Baseline] Template strategies...")
    t_b = time.perf_counter()
    baseline = _template_baseline(parcel, area_sqft)
    if verbose:
        print(f"  Best template score: {baseline:.4f}  ({time.perf_counter()-t_b:.2f}s)")

    elite_graphs = []
    results: List[SearchGeneration] = []

    for gen in range(generations):
        t0 = time.perf_counter()

        # Build candidate pool
        if elite_graphs:
            n_mutants = n_candidates * 2 // 3
            n_fresh   = n_candidates - n_mutants
            mutants   = mutate_population(elite_graphs, n_mutants,
                                          magnitude=40.0, n_ops=2,
                                          base_seed=seed + gen * 10000)
            fresh     = generate_graph_candidates(
                parcel_geojson=polygon_geojson,
                parcel_area_sqft=area_sqft,
                n=n_fresh, seed=seed + gen * 777,
            )
            all_graphs = mutants + fresh
        else:
            all_graphs = generate_graph_candidates(
                parcel_geojson=polygon_geojson,
                parcel_area_sqft=area_sqft,
                n=n_candidates, seed=seed + gen * 100,
            )

        # Convert to engine candidates
        pairs = graphs_to_candidates(all_graphs, road_width_ft=road_width_ft)

        # Simulate
        scored: List[Tuple[float, object]] = []
        for g, cand in pairs:
            result = _simulate_graph_candidate(parcel, cand, zoning, target_lots)
            if result is not None:
                sc, lots, rlen = result
                scored.append((sc, g))

        if not scored:
            if verbose:
                print(f"  Gen {gen+1}: 0 successful simulations")
            continue

        scored.sort(key=lambda x: x[0], reverse=True)
        best_score    = scored[0][0]
        best_type     = scored[0][1].generator_type
        improvement   = best_score - baseline
        elapsed       = time.perf_counter() - t0
        all_scores    = [sc for sc, _ in scored]

        elite_graphs  = [g for _, g in scored[:top_n_elite]]

        gen_result = SearchGeneration(
            generation=gen + 1,
            n_generated=len(all_graphs),
            n_converted=len(pairs),
            n_simulated=len(scored),
            best_score=best_score,
            best_type=best_type,
            elapsed=elapsed,
            all_scores=all_scores,
            improvement=improvement,
        )
        results.append(gen_result)

        if verbose:
            marker = "★" if improvement > 0 else " "
            type_dist = {}
            for sc, g in scored[:10]:
                type_dist[g.generator_type] = type_dist.get(g.generator_type, 0) + 1
            print(
                f"  Gen {gen+1:2d} {marker}  "
                f"best={best_score:.4f}  "
                f"vs baseline={baseline:.4f}  "
                f"Δ={improvement:+.4f}  "
                f"({len(scored)}/{len(pairs)} sims in {elapsed:.2f}s)"
            )
            print(f"         best_type={best_type}  "
                  f"top-10 types: {type_dist}")

    # Final summary
    if verbose and results:
        best_ever = max(results, key=lambda r: r.best_score)
        print(f"\n{'─'*66}")
        print("GRAPH SEARCH SUMMARY")
        print(f"{'─'*66}")
        print(f"  Template baseline:    {baseline:.4f}")
        print(f"  Best graph score:     {best_ever.best_score:.4f}  "
              f"(gen {best_ever.generation}, type={best_ever.best_type})")
        print(f"  Improvement:          {best_ever.improvement:+.4f}  "
              f"({best_ever.improvement/max(baseline,1e-9):.1%})")
        print(f"  Gens beating baseline: "
              f"{sum(1 for r in results if r.improvement > 0)}/{len(results)}")

        # Type breakdown across all generations
        all_type_best: dict = {}
        for r in results:
            t = r.best_type
            all_type_best[t] = max(all_type_best.get(t, 0.0), r.best_score)
        print(f"\n  Best score per generator type:")
        for t, sc in sorted(all_type_best.items(), key=lambda x: x[1], reverse=True):
            print(f"    {t:16s}  {sc:.4f}")

    return results


# ---------------------------------------------------------------------------
# Three-way comparison
# ---------------------------------------------------------------------------

def run_three_way_comparison(
    area_acres: float = 10.0,
    pool_size:  int = 60,
    top_n:      int = 12,
    seed:       int = 0,
) -> None:
    """Compare template, parameterized, and graph proposal strategies."""
    from model_lab.strategy_models.strategy_sampler import sample_random
    from model_lab.strategy_models.pre_strategy_ranker import PreStrategyRanker
    from model_lab.training.layout_runner import run_layout_param
    from model_lab.training.layout_scoring import score_layout

    parcel, polygon, area_sqft = _make_parcel(area_acres)

    print(f"\n{'='*66}")
    print("THREE-WAY COMPARISON: Template / Param / Graph")
    print(f"{'='*66}\n")

    # 1. Template baseline
    t0 = time.perf_counter()
    template_best = _template_baseline(parcel, area_sqft)
    template_time = time.perf_counter() - t0
    print(f"[1] Template (48 sims):    best={template_best:.4f}  t={template_time:.2f}s")

    # 2. Parameterised + pre-ranker
    try:
        t0 = time.perf_counter()
        strats = sample_random(pool_size, seed=seed)
        ranker = PreStrategyRanker.load()
        ranked = ranker.rank_strategies(polygon, area_sqft,
                                        [s.to_dict() for s in strats], top_n=top_n)
        param_scores = []
        for pred in ranked:
            from model_lab.strategy_models.param_strategy import ParamStrategy
            ps = ParamStrategy.from_dict(pred.strategy)
            result = run_layout_param(parcel, ps)
            if result:
                param_scores.append(score_layout(result.metrics).overall_score)
        param_best = max(param_scores) if param_scores else 0.0
        param_time = time.perf_counter() - t0
        print(f"[2] Param+pre-rank ({top_n}/{pool_size}): "
              f"best={param_best:.4f}  t={param_time:.2f}s  "
              f"vs template: {(param_best-template_best)/max(template_best,1e-9):+.1%}")
    except Exception as e:
        print(f"[2] Param: ERROR — {e}")
        param_best = 0.0

    # 3. Graph proposals (1 generation, no evolution)
    from model_lab.graph_models.graph_generator import generate_graph_candidates
    from model_lab.graph_models.graph_to_strategy import graphs_to_candidates
    from ai_subdivision.zoning import ZoningRules

    t0 = time.perf_counter()
    target_lots = max(4, int(area_sqft / 43560.0 * 6.0))
    zoning = ZoningRules(min_frontage_ft=40.0, min_depth_ft=80.0, min_area_sqft=4000.0)

    graphs = generate_graph_candidates(polygon, area_sqft, n=pool_size, seed=seed)
    pairs  = graphs_to_candidates(graphs, road_width_ft=32.0)
    graph_scores = []
    graph_types  = {}
    for g, cand in pairs:
        res = _simulate_graph_candidate(parcel, cand, zoning, target_lots)
        if res:
            sc, lots, rlen = res
            graph_scores.append(sc)
            graph_types[g.generator_type] = max(
                graph_types.get(g.generator_type, 0.0), sc
            )
    graph_best = max(graph_scores) if graph_scores else 0.0
    graph_time = time.perf_counter() - t0

    print(f"[3] Graph proposals ({len(graph_scores)}/{len(pairs)}): "
          f"best={graph_best:.4f}  t={graph_time:.2f}s  "
          f"vs template: {(graph_best-template_best)/max(template_best,1e-9):+.1%}")
    print(f"    Best per type: " +
          "  ".join(f"{t}={sc:.3f}" for t, sc in sorted(
              graph_types.items(), key=lambda x: x[1], reverse=True)))

    print(f"\n{'─'*66}")
    print(f"  Approach          Best Score  vs Baseline  Speedup  Sims")
    print(f"  Template (base)   {template_best:.4f}    —           1.0×    48")
    print(f"  Parameterized     {param_best:.4f}  "
          f"  {(param_best-template_best)/max(template_best,1e-9):+.1%}       "
          f"{48/max(top_n,1):.1f}×    {len(param_scores)}")
    print(f"  Graph proposals   {graph_best:.4f}  "
          f"  {(graph_best-template_best)/max(template_best,1e-9):+.1%}       "
          f"—      {len(graph_scores)}")


# ---------------------------------------------------------------------------
# Topology-agnostic graph search (Phase 7)
# ---------------------------------------------------------------------------

def run_topo_graph_search(
    generations:   int = 5,
    n_candidates:  int = 36,
    top_n_elite:   int = 6,
    area_acres:    float = 10.0,
    road_width_ft: float = 32.0,
    target_density_du_per_ac: float = 6.0,
    seed:          int = 0,
    verbose:       bool = True,
) -> List[SearchGeneration]:
    """
    Evolutionary graph search using the topology-agnostic subdivision engine.

    Same structure as run_graph_search but simulation uses run_subdivision()
    instead of the production generate_subdivision() — novel topologies are
    no longer penalized by template-specific lot-placement.
    """
    from model_lab.graph_models.graph_generator import generate_graph_candidates
    from model_lab.graph_models.graph_mutation import mutate_population
    from shapely.geometry import Polygon

    parcel, polygon_geojson, area_sqft = _make_parcel(area_acres)
    # Build shapely polygon from GeoJSON
    coords = polygon_geojson["coordinates"][0]
    parcel_polygon = Polygon([(c[0], c[1]) for c in coords])

    if verbose:
        print("=" * 66)
        print("TOPO-AGNOSTIC GRAPH SEARCH (Phase 7)")
        print(f"  Parcel: {area_acres:.0f} acres   "
              f"Road width: {road_width_ft:.0f}ft   "
              f"Target density: {target_density_du_per_ac:.0f} du/ac")
        print(f"  Pool: {n_candidates}  Elite: {top_n_elite}  Generations: {generations}")
        print("=" * 66)

    elite_graphs = []
    results: List[SearchGeneration] = []

    for gen in range(generations):
        t0 = time.perf_counter()

        if elite_graphs:
            n_mutants = n_candidates * 2 // 3
            n_fresh   = n_candidates - n_mutants
            mutants   = mutate_population(elite_graphs, n_mutants,
                                          magnitude=40.0, n_ops=2,
                                          base_seed=seed + gen * 10000)
            fresh     = generate_graph_candidates(
                parcel_geojson=polygon_geojson,
                parcel_area_sqft=area_sqft,
                n=n_fresh, seed=seed + gen * 777,
            )
            all_graphs = mutants + fresh
        else:
            all_graphs = generate_graph_candidates(
                parcel_geojson=polygon_geojson,
                parcel_area_sqft=area_sqft,
                n=n_candidates, seed=seed + gen * 100,
            )

        scored: List[Tuple[float, object]] = []
        for g in all_graphs:
            result = _simulate_graph_candidate_topo(
                graph=g,
                parcel_polygon=parcel_polygon,
                road_width_ft=road_width_ft,
            )
            if result is not None:
                sc, lots, rlen = result
                scored.append((sc, g))

        if not scored:
            if verbose:
                print(f"  Gen {gen+1}: 0 successful simulations")
            continue

        scored.sort(key=lambda x: x[0], reverse=True)
        best_score  = scored[0][0]
        best_type   = scored[0][1].generator_type
        elapsed     = time.perf_counter() - t0
        all_scores  = [sc for sc, _ in scored]
        elite_graphs = [g for _, g in scored[:top_n_elite]]

        gen_result = SearchGeneration(
            generation=gen + 1,
            n_generated=len(all_graphs),
            n_converted=len(all_graphs),
            n_simulated=len(scored),
            best_score=best_score,
            best_type=best_type,
            elapsed=elapsed,
            all_scores=all_scores,
            improvement=0.0,
        )
        results.append(gen_result)

        if verbose:
            type_dist = {}
            for sc, g in scored[:10]:
                type_dist[g.generator_type] = type_dist.get(g.generator_type, 0) + 1
            print(
                f"  Gen {gen+1:2d}  "
                f"best={best_score:.4f}  "
                f"({len(scored)}/{len(all_graphs)} sims in {elapsed:.2f}s)"
            )
            print(f"         best_type={best_type}  top-10 types: {type_dist}")

    if verbose and results:
        best_ever = max(results, key=lambda r: r.best_score)
        all_type_best: dict = {}
        for r in results:
            t = r.best_type
            all_type_best[t] = max(all_type_best.get(t, 0.0), r.best_score)
        print(f"\n{'─'*66}")
        print("TOPO-AGNOSTIC SEARCH SUMMARY")
        print(f"  Best overall:  {best_ever.best_score:.4f}  "
              f"(gen {best_ever.generation}, type={best_ever.best_type})")
        print(f"  Best per generator type:")
        for t, sc in sorted(all_type_best.items(), key=lambda x: x[1], reverse=True):
            print(f"    {t:16s}  {sc:.4f}")

    return results


def run_topo_comparison(
    area_acres: float = 10.0,
    pool_size:  int = 60,
    seed:       int = 0,
) -> None:
    """
    Compare all 6 graph generator types using topology-agnostic subdivision.
    Shows whether novel types (grid, herringbone, radial) can now compete.
    """
    from model_lab.graph_models.graph_generator import generate_graph_candidates
    from shapely.geometry import Polygon

    parcel, polygon_geojson, area_sqft = _make_parcel(area_acres)
    parcel_polygon = Polygon([(c[0], c[1]) for c in polygon_geojson["coordinates"][0]])

    print(f"\n{'='*66}")
    print("TOPOLOGY-AGNOSTIC COMPARISON (Phase 7)")
    print(f"  {pool_size} candidates, {area_acres:.0f}-acre parcel")
    print(f"{'='*66}\n")

    t0 = time.perf_counter()
    graphs = generate_graph_candidates(polygon_geojson, area_sqft, n=pool_size, seed=seed)

    type_scores: dict = {}
    type_lots:   dict = {}
    n_ok = 0

    for g in graphs:
        res = _simulate_graph_candidate_topo(g, parcel_polygon)
        if res:
            sc, lots, rlen = res
            n_ok += 1
            gt = g.generator_type
            if sc > type_scores.get(gt, 0.0):
                type_scores[gt] = sc
                type_lots[gt]   = lots

    elapsed = time.perf_counter() - t0
    print(f"  Simulated {n_ok}/{len(graphs)} graphs in {elapsed:.2f}s\n")
    print(f"  {'Generator':16s}  {'Best Score':>10s}  {'Best Lots':>9s}")
    print(f"  {'─'*16}  {'─'*10}  {'─'*9}")
    for gt, sc in sorted(type_scores.items(), key=lambda x: x[1], reverse=True):
        print(f"  {gt:16s}  {sc:10.4f}  {type_lots.get(gt, 0):9d}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(
        description="Evolutionary search over road graph proposal space.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--generations",   type=int,   default=5)
    parser.add_argument("--n-candidates",  type=int,   default=36)
    parser.add_argument("--top-n-elite",   type=int,   default=6)
    parser.add_argument("--area-acres",    type=float, default=10.0)
    parser.add_argument("--road-width",    type=float, default=32.0)
    parser.add_argument("--target-density", type=float, default=6.0)
    parser.add_argument("--seed",          type=int,   default=0)
    parser.add_argument("--topo",          action="store_true",
                        help="Use topology-agnostic engine (Phase 7)")
    parser.add_argument("--compare",       action="store_true",
                        help="Run three-way comparison after search")
    args = parser.parse_args()

    if args.topo:
        run_topo_graph_search(
            generations=args.generations,
            n_candidates=args.n_candidates,
            top_n_elite=args.top_n_elite,
            area_acres=args.area_acres,
            road_width_ft=args.road_width,
            target_density_du_per_ac=args.target_density,
            seed=args.seed,
        )
        if args.compare:
            run_topo_comparison(area_acres=args.area_acres, pool_size=60, seed=args.seed)
        return

    run_graph_search(
        generations=args.generations,
        n_candidates=args.n_candidates,
        top_n_elite=args.top_n_elite,
        area_acres=args.area_acres,
        road_width_ft=args.road_width,
        target_density_du_per_ac=args.target_density,
        seed=args.seed,
    )

    if args.compare:
        run_three_way_comparison(
            area_acres=args.area_acres,
            pool_size=60,
            top_n=12,
            seed=args.seed,
        )


if __name__ == "__main__":
    main()
