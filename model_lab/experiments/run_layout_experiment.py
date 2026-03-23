"""
Layout Strategy Experiment Runner — model_lab  (Phase 3)

Two modes:
  baseline  — simulate ALL strategies (original behaviour)
  ranked    — AI pre-ranks strategies, simulate only the top N

Usage:
    # Baseline: simulate 4 preset strategies (original behaviour):
    python -m model_lab.experiments.run_layout_experiment

    # Ranked mode: generate 48 strategies, rank with AI, simulate top 12:
    python -m model_lab.experiments.run_layout_experiment \\
        --mode ranked --pool-size 48 --top-n 12

    # Custom parcel:
    python -m model_lab.experiments.run_layout_experiment \\
        --parcel data/sample_irregular_parcel.geojson --mode ranked

    # Comparison experiment (baseline vs ranked):
    python -m model_lab.experiments.run_layout_experiment --compare

This script does NOT modify any production code.
The ai_subdivision package is imported read-only.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# ---------------------------------------------------------------------------
# Production imports (read-only)
# ---------------------------------------------------------------------------
from ai_subdivision import (
    SubdivisionConstraints,
    ZoningRules,
    generate_subdivision,
    load_zoning_rules,
)
from ai_subdivision.constraints import Easement, Lots, Parcel, Road
from ai_subdivision.geometry import parcel_shapely_from_constraints
from ai_subdivision.street_network import generate_candidate_street_networks
from ai_subdivision.subdivision import summarize_layout

# ---------------------------------------------------------------------------
# Model lab imports
# ---------------------------------------------------------------------------
from model_lab.strategy_models.basic_strategy_generator import (
    full_sweep_strategies,
    generate_strategies,
    preset_strategies,
)
from model_lab.strategy_models.strategy_interface import LayoutStrategy
from model_lab.training.road_graph_extractor import extract_road_graph

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DATASET_DIR = REPO_ROOT / "model_lab" / "datasets" / "layout_training"

# ---------------------------------------------------------------------------
# Density → lot count
# ---------------------------------------------------------------------------
DENSITY_LOT_TARGETS: dict[str, int] = {"low": 8, "medium": 16, "high": 24}
DEFAULT_ROAD_WIDTH = 40.0
DEFAULT_ZONING = ZoningRules(min_frontage_ft=60.0, min_depth_ft=110.0, min_area_sqft=6000.0)


# ---------------------------------------------------------------------------
# Parcel loading
# ---------------------------------------------------------------------------

def load_parcel_boundary(geojson_path: Path) -> list[tuple[float, float]]:
    payload = json.loads(geojson_path.read_text(encoding="utf-8"))
    features = payload.get("features", [payload]) if "features" in payload else [payload]
    geometry = features[0].get("geometry", features[0])
    coords = geometry["coordinates"][0]
    if coords[0] == coords[-1]:
        coords = coords[:-1]
    return [(float(x), float(y)) for x, y in coords]


def default_constraints(boundary=None) -> SubdivisionConstraints:
    if boundary:
        parcel = Parcel(shape="polygon", boundary=boundary)
    else:
        parcel = Parcel(shape="rectangle", area_acres=10.0, aspect_ratio=1.5)
    return SubdivisionConstraints(
        parcel=parcel,
        lots=Lots(count=16),
        road=Road(orientation="north_south", width_ft=DEFAULT_ROAD_WIDTH),
        easement=Easement(width_ft=10.0),
    )


# ---------------------------------------------------------------------------
# Single simulation helper
# ---------------------------------------------------------------------------

def _simulate_strategy(
    strategy: LayoutStrategy,
    base_constraints: SubdivisionConstraints,
    candidates_by_topology: dict,
    zoning_rules: ZoningRules,
) -> Optional[dict]:
    """
    Run generate_subdivision for one strategy.  Returns a result dict or None.
    """
    topology_candidates = candidates_by_topology.get(strategy.road_type, [])
    if not topology_candidates:
        topology_candidates = candidates_by_topology.get("collector", [])
    if not topology_candidates:
        return None

    network = max(topology_candidates, key=lambda c: c.road_length_ft)
    target_lots = DENSITY_LOT_TARGETS.get(strategy.density_goal, 16)
    constraints = base_constraints.model_copy(update={"lots": Lots(count=target_lots)})

    try:
        layout = generate_subdivision(
            constraints=constraints,
            zoning_rules=zoning_rules,
            street_network=network,
            target_lot_count=target_lots,
        )
    except Exception as exc:
        return {"error": str(exc), "strategy": strategy.to_dict()}

    summary = summarize_layout(constraints, zoning_rules, layout)
    # Compute consistent score (same formula as layout_scoring.py)
    lot_count = summary["generated_lot_count"]
    road_len  = float(summary["road_length_ft"])
    dev_area  = float(summary["developable_area_sqft"])
    parcel_a  = float(summary["parcel_area_sqft"])
    yield_score      = lot_count / 40.0
    efficiency_score = (dev_area / max(road_len, 1.0)) / 200.0
    overall_score    = 0.6 * yield_score + 0.4 * efficiency_score

    return {
        "strategy":      strategy.to_dict(),
        "topology":      network.topology,
        "orientation":   network.orientation,
        "lot_count":     lot_count,
        "road_length_ft": road_len,
        "developable_area_sqft": dev_area,
        "parcel_area_sqft": parcel_a,
        "overall_score": overall_score,
    }


# ---------------------------------------------------------------------------
# Baseline mode
# ---------------------------------------------------------------------------

def run_baseline(
    base_constraints: SubdivisionConstraints,
    candidates_by_topology: dict,
    zoning_rules: ZoningRules,
    strategies: List[LayoutStrategy],
) -> tuple[list[dict], float]:
    """Simulate every strategy. Returns (results, elapsed_sec)."""
    t0 = time.perf_counter()
    results = []
    for s in strategies:
        r = _simulate_strategy(s, base_constraints, candidates_by_topology, zoning_rules)
        if r and "error" not in r:
            results.append(r)
    elapsed = time.perf_counter() - t0
    return results, elapsed


# ---------------------------------------------------------------------------
# Ranked mode
# ---------------------------------------------------------------------------

def _build_road_graph_for_strategy(
    strategy: LayoutStrategy,
    parcel_polygon,
    candidates_by_topology: dict,
    base_constraints: SubdivisionConstraints,
) -> dict:
    """Extract a road graph (cheap) for a strategy without running full simulation."""
    topology_candidates = candidates_by_topology.get(strategy.road_type, [])
    if not topology_candidates:
        topology_candidates = candidates_by_topology.get("collector", [])
    if not topology_candidates:
        return {"nodes": [], "edges": [], "metrics": {}}

    network = max(topology_candidates, key=lambda c: c.road_length_ft)
    road_graph = extract_road_graph(
        centerlines=network.centerlines,
        parcel_area_sqft=float(parcel_polygon.area),
    )
    return road_graph.to_dict()


def run_ranked(
    base_constraints: SubdivisionConstraints,
    parcel_polygon,
    candidates_by_topology: dict,
    zoning_rules: ZoningRules,
    pool_size: int = 48,
    top_n: int = 12,
    seed: int = 0,
) -> tuple[list[dict], list[dict], float]:
    """
    Ranked simulation:
      1. Generate a large pool of strategies
      2. Extract road graphs (cheap)
      3. Rank with AI model
      4. Simulate only top_n

    Returns (simulated_results, all_predictions, elapsed_sec).
    """
    from model_lab.strategy_models.strategy_ranker import StrategyRanker

    # Load ranker
    try:
        ranker = StrategyRanker.load()
    except FileNotFoundError as exc:
        print(f"  WARNING: {exc}")
        print("  Falling back to baseline (no ranking).")
        strategies = generate_strategies(pool_size, seed=seed)
        results, elapsed = run_baseline(base_constraints, candidates_by_topology, zoning_rules, strategies)
        return results[:top_n], [], elapsed

    # Build strategy pool
    strategies = generate_strategies(pool_size, include_presets=True, seed=seed)

    # Cheap road graph extraction for each strategy
    road_graphs = [
        _build_road_graph_for_strategy(s, parcel_polygon, candidates_by_topology, base_constraints)
        for s in strategies
    ]

    # GeoJSON of the parcel polygon for the ranker
    from shapely.geometry import mapping
    parcel_geojson = dict(mapping(parcel_polygon))
    parcel_area_sqft = float(parcel_polygon.area)

    # Rank
    t0 = time.perf_counter()
    predictions = ranker.rank_strategies(
        parcel_area_sqft=parcel_area_sqft,
        parcel_polygon=parcel_geojson,
        strategies=[s.to_dict() for s in strategies],
        road_graphs=road_graphs,
        top_n=top_n,
    )
    rank_time = time.perf_counter() - t0

    # Simulate top_n
    t1 = time.perf_counter()
    results = []
    for pred in predictions:
        strategy = LayoutStrategy(
            road_type=pred.strategy["road_type"],
            entry_point=pred.strategy["entry_point"],
            culdesac_count=pred.strategy["culdesac_count"],
            density_goal=pred.strategy["density_goal"],
        )
        r = _simulate_strategy(strategy, base_constraints, candidates_by_topology, zoning_rules)
        if r and "error" not in r:
            r["predicted_score"] = pred.predicted_score
            results.append(r)
    sim_time = time.perf_counter() - t1

    elapsed = rank_time + sim_time
    return results, [{"strategy": p.strategy, "predicted_score": p.predicted_score, "rank": p.rank}
                     for p in predictions], elapsed


# ---------------------------------------------------------------------------
# Comparison experiment
# ---------------------------------------------------------------------------

def run_comparison(
    base_constraints: SubdivisionConstraints,
    parcel_polygon,
    candidates_by_topology: dict,
    zoning_rules: ZoningRules,
    pool_size: int = 48,
    top_n: int = 12,
) -> None:
    """Side-by-side: baseline (simulate all) vs ranked (simulate top-N)."""
    print("\n" + "─" * 58)
    print(f"  COMPARISON: Baseline ({pool_size} sims) vs Ranked (top {top_n})")
    print("─" * 58)

    all_strategies = generate_strategies(pool_size, include_presets=True, seed=42)

    # Baseline
    print(f"\n  [Baseline]  Simulating all {len(all_strategies)} strategies...")
    baseline_results, baseline_time = run_baseline(
        base_constraints, candidates_by_topology, zoning_rules, all_strategies
    )
    baseline_best = max(baseline_results, key=lambda r: r["overall_score"]) if baseline_results else {}
    print(f"    Simulated: {len(baseline_results)}  |  Best score: {baseline_best.get('overall_score', 0):.4f}"
          f"  |  Time: {baseline_time:.3f}s")

    # Ranked
    print(f"\n  [Ranked]    Pool {pool_size} → rank → simulate top {top_n}...")
    ranked_results, predictions, ranked_time = run_ranked(
        base_constraints, parcel_polygon, candidates_by_topology, zoning_rules,
        pool_size=pool_size, top_n=top_n,
    )
    ranked_best = max(ranked_results, key=lambda r: r["overall_score"]) if ranked_results else {}
    print(f"    Simulated: {len(ranked_results)}  |  Best score: {ranked_best.get('overall_score', 0):.4f}"
          f"  |  Time: {ranked_time:.3f}s")

    # Stats
    if baseline_best and ranked_best:
        score_retention = ranked_best["overall_score"] / max(baseline_best["overall_score"], 1e-9)
        speedup = baseline_time / max(ranked_time, 1e-9)
        print(f"\n  Score retention : {score_retention:.1%}  (target: >80%)")
        print(f"  Speedup         : {speedup:.1f}×  (target: >5×)")

        goal_retention = score_retention >= 0.80
        goal_speedup   = speedup >= 5.0
        print(f"\n  Goals met:")
        print(f"    Score retention ≥ 80%: {'✓' if goal_retention else '✗'}  ({score_retention:.1%})")
        print(f"    Speedup ≥ 5×:          {'✓' if goal_speedup else '✗'}  ({speedup:.1f}×)")


# ---------------------------------------------------------------------------
# Main experiment runner
# ---------------------------------------------------------------------------

def run_experiment(
    parcel_geojson: Optional[Path] = None,
    mode: str = "baseline",
    pool_size: int = 48,
    top_n: int = 12,
    compare: bool = False,
    save_results: bool = True,
) -> list[dict]:
    """
    Main entry point.

    mode: "baseline" (simulate all) | "ranked" (AI pre-rank + simulate top N)
    """
    # Load parcel
    boundary = None
    if parcel_geojson and parcel_geojson.exists():
        boundary = load_parcel_boundary(parcel_geojson)
        print(f"Loaded parcel: {parcel_geojson.name}  ({len(boundary)} vertices)")
    else:
        print("Using default 10-acre rectangular parcel")

    zoning_rules = DEFAULT_ZONING
    base_constraints = default_constraints(boundary)
    parcel_polygon = parcel_shapely_from_constraints(base_constraints)

    # Generate all candidate networks once (shared by all strategies)
    candidates = generate_candidate_street_networks(
        parcel_polygon=parcel_polygon,
        road_width_ft=DEFAULT_ROAD_WIDTH,
    )
    candidates_by_topology: dict = {}
    for c in candidates:
        candidates_by_topology.setdefault(c.topology, []).append(c)

    # Comparison mode
    if compare:
        run_comparison(base_constraints, parcel_polygon, candidates_by_topology,
                       zoning_rules, pool_size=pool_size, top_n=top_n)
        return []

    # Baseline mode
    if mode == "baseline":
        strategies = preset_strategies()
        print(f"\nBaseline mode: simulating {len(strategies)} preset strategies")
        results, elapsed = run_baseline(
            base_constraints, candidates_by_topology, zoning_rules, strategies
        )
        _print_results(results, elapsed, mode="baseline")

    # Ranked mode
    else:
        print(f"\nRanked mode: pool={pool_size} strategies → simulate top {top_n}")
        results, predictions, elapsed = run_ranked(
            base_constraints, parcel_polygon, candidates_by_topology, zoning_rules,
            pool_size=pool_size, top_n=top_n,
        )
        _print_results(results, elapsed, mode="ranked", predictions=predictions)

    if save_results and results:
        out = DATASET_DIR / "experiment_results.json"
        DATASET_DIR.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"\n  Results saved → {out.relative_to(REPO_ROOT)}")

    return results


def _print_results(results: list[dict], elapsed: float, mode: str, predictions=None) -> None:
    if not results:
        print("  No successful layouts generated.")
        return
    best = max(results, key=lambda r: r["overall_score"])
    print(f"\n  ── {mode.upper()} Results ──────────────────────────────────")
    print(f"  Simulated:    {len(results)}")
    print(f"  Time:         {elapsed:.3f}s")
    print(f"  Best score:   {best['overall_score']:.4f}")
    print(f"  Best topology:{best['topology']}")
    print(f"  Best lots:    {best['lot_count']}")
    print()
    print(f"  {'Topology':12s}  {'Density':8s}  {'Lots':5s}  {'Score':7s}"
          + ("  PredScore" if mode == "ranked" else ""))
    print("  " + "─" * (50 if mode != "ranked" else 60))
    sorted_results = sorted(results, key=lambda r: r["overall_score"], reverse=True)
    for r in sorted_results:
        pred = f"  {r.get('predicted_score', 0):.4f}" if mode == "ranked" else ""
        print(f"  {r['topology']:12s}  {r['strategy']['density_goal']:8s}  "
              f"{r['lot_count']:5d}  {r['overall_score']:7.4f}{pred}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Layout strategy experiment runner with optional AI ranking.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--parcel",    type=Path,  default=None)
    parser.add_argument("--mode",      type=str,   default="baseline",
                        choices=["baseline", "ranked"])
    parser.add_argument("--pool-size", type=int,   default=48,
                        help="Strategy pool size for ranked mode.")
    parser.add_argument("--top-n",     type=int,   default=12,
                        help="Strategies to simulate after ranking.")
    parser.add_argument("--compare",   action="store_true",
                        help="Run baseline vs ranked comparison.")
    parser.add_argument("--no-save",   action="store_true",
                        help="Don't save results JSON.")
    args = parser.parse_args()

    run_experiment(
        parcel_geojson=args.parcel,
        mode=args.mode,
        pool_size=args.pool_size,
        top_n=args.top_n,
        compare=args.compare,
        save_results=not args.no_save,
    )


if __name__ == "__main__":
    main()
