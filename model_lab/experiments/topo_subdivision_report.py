"""
Phase 7 Report — Topology-Agnostic Lot Subdivision
===================================================

Generates a comparison table and per-type analysis showing how the new
subdivision engine (Phase 7) affects graph proposal scoring vs the
production template engine (Phase 6).

No production code is modified.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def run_report(
    area_acres:  float = 10.0,
    pool_size:   int   = 60,
    evo_gens:    int   = 5,
    evo_pool:    int   = 36,
    seed:        int   = 0,
) -> None:
    from model_lab.experiments.graph_search import (
        _template_baseline,
        _make_parcel,
        _simulate_graph_candidate,
        _simulate_graph_candidate_topo,
        run_topo_graph_search,
    )
    from model_lab.graph_models.graph_generator import generate_graph_candidates
    from model_lab.graph_models.graph_to_strategy import graphs_to_candidates
    from shapely.geometry import Polygon
    from ai_subdivision.zoning import ZoningRules

    parcel, polygon_geojson, area_sqft = _make_parcel(area_acres)
    side = (area_sqft) ** 0.5
    parcel_polygon = Polygon([(0, 0), (side, 0), (side, side), (0, side)])
    zoning = ZoningRules(min_frontage_ft=40.0, min_depth_ft=80.0, min_area_sqft=4000.0)
    target_lots = max(4, int(area_sqft / 43560.0 * 6.0))

    print("=" * 70)
    print("PHASE 7 REPORT — TOPOLOGY-AGNOSTIC LOT SUBDIVISION")
    print(f"  Parcel: {area_acres:.0f} acres ({area_sqft:.0f} sqft)  "
          f"Pool: {pool_size}  Evo-gens: {evo_gens}")
    print("=" * 70)

    # ------------------------------------------------------------------ #
    # 1. Template baseline (production engine)
    # ------------------------------------------------------------------ #
    print("\n[1] Template baseline (production engine)...")
    t0 = time.perf_counter()
    baseline = _template_baseline(parcel, area_sqft)
    print(f"    Score: {baseline:.4f}  ({time.perf_counter()-t0:.2f}s)")

    # ------------------------------------------------------------------ #
    # 2. Graph proposals — production engine (Phase 6)
    # ------------------------------------------------------------------ #
    print(f"\n[2] Graph proposals — production engine (n={pool_size}, seed={seed})...")
    t0 = time.perf_counter()
    graphs = generate_graph_candidates(polygon_geojson, area_sqft, n=pool_size, seed=seed)
    pairs  = graphs_to_candidates(graphs)
    ph6_scores, ph6_types, ph6_lots = [], {}, {}
    for g, cand in pairs:
        res = _simulate_graph_candidate(parcel, cand, zoning, target_lots)
        if res:
            sc, lots, rlen = res
            ph6_scores.append(sc)
            gt = g.generator_type
            if sc > ph6_types.get(gt, 0.0):
                ph6_types[gt] = sc
                ph6_lots[gt]  = lots
    ph6_best = max(ph6_scores) if ph6_scores else 0.0
    ph6_time = time.perf_counter() - t0
    print(f"    Best: {ph6_best:.4f}  n={len(ph6_scores)}/{len(pairs)}  ({ph6_time:.2f}s)")

    # ------------------------------------------------------------------ #
    # 3. Graph proposals — topo-agnostic engine (Phase 7, single-shot)
    # ------------------------------------------------------------------ #
    print(f"\n[3] Graph proposals — topo-agnostic engine (n={pool_size}, seed={seed})...")
    t0 = time.perf_counter()
    graphs2 = generate_graph_candidates(polygon_geojson, area_sqft, n=pool_size, seed=seed)
    ph7_scores, ph7_types, ph7_lots = [], {}, {}
    for g in graphs2:
        res = _simulate_graph_candidate_topo(g, parcel_polygon)
        if res:
            sc, lots, rlen = res
            ph7_scores.append(sc)
            gt = g.generator_type
            if sc > ph7_types.get(gt, 0.0):
                ph7_types[gt] = sc
                ph7_lots[gt]  = lots
    ph7_best = max(ph7_scores) if ph7_scores else 0.0
    ph7_time = time.perf_counter() - t0
    print(f"    Best: {ph7_best:.4f}  n={len(ph7_scores)}/{len(graphs2)}  ({ph7_time:.2f}s)")

    # ------------------------------------------------------------------ #
    # 4. Evolutionary search — topo-agnostic engine
    # ------------------------------------------------------------------ #
    print(f"\n[4] Evolutionary search — topo-agnostic engine "
          f"({evo_gens} gens × {evo_pool} candidates)...")
    t0 = time.perf_counter()
    evo_results = run_topo_graph_search(
        generations=evo_gens,
        n_candidates=evo_pool,
        area_acres=area_acres,
        seed=seed,
        verbose=True,
    )
    evo_best = max(r.best_score for r in evo_results) if evo_results else 0.0
    evo_time = time.perf_counter() - t0
    print(f"    Best after evolution: {evo_best:.4f}  ({evo_time:.2f}s)")

    # ------------------------------------------------------------------ #
    # 5. Per-type comparison table
    # ------------------------------------------------------------------ #
    all_types = sorted(set(list(ph6_types.keys()) + list(ph7_types.keys())))

    print(f"\n{'─'*70}")
    print("PER-TYPE SCORE COMPARISON")
    print(f"{'─'*70}")
    print(f"  {'Generator':16s}  {'Phase6 (prod)':>13s}  {'Phase7 (topo)':>13s}  "
          f"{'Δ':>8s}  {'Lots6':>5s}  {'Lots7':>5s}")
    print(f"  {'─'*16}  {'─'*13}  {'─'*13}  {'─'*8}  {'─'*5}  {'─'*5}")
    for gt in all_types:
        sc6 = ph6_types.get(gt, 0.0)
        sc7 = ph7_types.get(gt, 0.0)
        delta = sc7 - sc6
        l6 = ph6_lots.get(gt, 0)
        l7 = ph7_lots.get(gt, 0)
        marker = "↑" if delta > 0.01 else ("↓" if delta < -0.01 else " ")
        print(f"  {gt:16s}  {sc6:13.4f}  {sc7:13.4f}  "
              f"{delta:+7.4f}{marker}  {l6:5d}  {l7:5d}")

    print(f"\n{'─'*70}")
    print("SUMMARY")
    print(f"{'─'*70}")
    print(f"  {'Approach':<40s}  {'Score':>8s}  {'vs Baseline':>12s}")
    print(f"  {'─'*40}  {'─'*8}  {'─'*12}")

    def pct(sc): return f"{(sc-baseline)/max(baseline,1e-9):+.1%}"

    print(f"  {'Template strategies (baseline)':<40s}  {baseline:.4f}  {'—':>12s}")
    print(f"  {'Graph + prod engine (Phase 6)':<40s}  {ph6_best:.4f}  {pct(ph6_best):>12s}")
    print(f"  {'Graph + topo engine, 1-shot (Phase 7)':<40s}  {ph7_best:.4f}  {pct(ph7_best):>12s}")
    print(f"  {'Graph + topo engine, evolved (Phase 7)':<40s}  {evo_best:.4f}  {pct(evo_best):>12s}")

    print(f"\n  Key insight: grid topology went from {ph6_types.get('grid',0):.4f} "
          f"(Phase 6) to {ph7_types.get('grid',0):.4f} (Phase 7) — "
          f"{(ph7_types.get('grid',0)-ph6_types.get('grid',0))/max(ph6_types.get('grid',1e-9),1e-9):+.0%} improvement.")
    print(f"  Evolutionary search closes gap to template baseline: "
          f"{evo_best:.4f} vs {baseline:.4f} "
          f"({(evo_best-baseline)/max(baseline,1e-9):+.1%}).")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--area-acres",  type=float, default=10.0)
    parser.add_argument("--pool-size",   type=int,   default=60)
    parser.add_argument("--evo-gens",    type=int,   default=5)
    parser.add_argument("--evo-pool",    type=int,   default=36)
    parser.add_argument("--seed",        type=int,   default=0)
    args = parser.parse_args()
    run_report(
        area_acres=args.area_acres,
        pool_size=args.pool_size,
        evo_gens=args.evo_gens,
        evo_pool=args.evo_pool,
        seed=args.seed,
    )
