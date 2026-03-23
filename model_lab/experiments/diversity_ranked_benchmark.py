"""
Diversity-aware ranked layout benchmark (model_lab).

Compares:
  1) standard ranker top-N selection
  2) diversity-aware re-ranked top-N selection (MMR-style)

against full-pool simulation baseline under identical constraints.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from shapely.geometry import mapping

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = REPO_ROOT.parent
for candidate in (REPO_ROOT, WORKSPACE_ROOT):
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

from ai_subdivision.geometry import parcel_shapely_from_constraints
from ai_subdivision.street_network import generate_candidate_street_networks
from model_lab.experiments.run_layout_experiment import (
    _build_road_graph_for_strategy,
    _simulate_strategy,
    default_constraints,
    load_parcel_boundary,
    run_baseline,
)
from model_lab.strategy_models.basic_strategy_generator import generate_strategies
from model_lab.strategy_models.strategy_interface import LayoutStrategy
from model_lab.strategy_models.strategy_ranker import RankerPrediction, StrategyRanker


@dataclass(frozen=True)
class ParcelSpec:
    name: str
    parcel_path: Optional[Path] = None


def _strategy_key(strategy: dict) -> tuple[str, str, str, int]:
    return (
        str(strategy.get("road_type", "")),
        str(strategy.get("entry_point", "")),
        str(strategy.get("density_goal", "")),
        int(strategy.get("culdesac_count", 0)),
    )


def _similarity(a: dict, b: dict) -> float:
    same = 0
    same += 1 if a.get("road_type") == b.get("road_type") else 0
    same += 1 if a.get("entry_point") == b.get("entry_point") else 0
    same += 1 if a.get("density_goal") == b.get("density_goal") else 0
    same += 1 if int(a.get("culdesac_count", 0)) == int(b.get("culdesac_count", 0)) else 0
    return same / 4.0


def select_diverse_predictions(
    predictions: list[RankerPrediction],
    top_n: int,
    lambda_diversity: float,
) -> list[RankerPrediction]:
    """MMR-style selection from a ranked list of predictions."""
    if top_n <= 0 or not predictions:
        return []

    selected: list[RankerPrediction] = [predictions[0]]
    remaining = predictions[1:]

    while len(selected) < top_n and remaining:
        best_idx = 0
        best_mmr = float("-inf")
        for idx, candidate in enumerate(remaining):
            max_sim = max(_similarity(candidate.strategy, chosen.strategy) for chosen in selected)
            mmr = candidate.predicted_score - lambda_diversity * max_sim
            if mmr > best_mmr:
                best_mmr = mmr
                best_idx = idx
        selected.append(remaining.pop(best_idx))

    return selected


def select_road_type_coverage_predictions(
    predictions: list[RankerPrediction],
    top_n: int,
) -> list[RankerPrediction]:
    """Pick highest-ranked strategy per road_type first, then fill by score."""
    if top_n <= 0 or not predictions:
        return []

    selected: list[RankerPrediction] = []
    chosen_ids: set[tuple[str, str, str, int]] = set()
    best_by_type: dict[str, RankerPrediction] = {}
    for pred in predictions:
        road_type = str(pred.strategy.get("road_type", ""))
        if road_type not in best_by_type:
            best_by_type[road_type] = pred

    for pred in sorted(best_by_type.values(), key=lambda p: p.predicted_score, reverse=True):
        key = _strategy_key(pred.strategy)
        if key in chosen_ids:
            continue
        selected.append(pred)
        chosen_ids.add(key)
        if len(selected) >= top_n:
            return selected

    for pred in predictions:
        key = _strategy_key(pred.strategy)
        if key in chosen_ids:
            continue
        selected.append(pred)
        chosen_ids.add(key)
        if len(selected) >= top_n:
            break
    return selected


def _simulate_selected(
    selected: list[RankerPrediction],
    base_constraints,
    candidates_by_topology: dict,
    zoning_rules,
) -> tuple[list[dict], float]:
    t0 = time.perf_counter()
    results: list[dict] = []
    for pred in selected:
        strategy = LayoutStrategy.from_dict(pred.strategy)
        sim = _simulate_strategy(strategy, base_constraints, candidates_by_topology, zoning_rules)
        if sim and "error" not in sim:
            sim["predicted_score"] = pred.predicted_score
            results.append(sim)
    return results, time.perf_counter() - t0


def _safe_mean(values: list[float]) -> float:
    return float(statistics.mean(values)) if values else 0.0


def _road_efficiency(result: dict) -> float:
    road_len = float(result.get("road_length_ft", 0.0))
    dev_area = float(result.get("developable_area_sqft", 0.0))
    return dev_area / max(road_len, 1.0)


def run_case(
    *,
    parcel: ParcelSpec,
    pool_size: int,
    top_n: int,
    seeds: list[int],
    lambda_diversity: float,
    diversity_method: str,
) -> dict:
    boundary = None
    if parcel.parcel_path:
        boundary = load_parcel_boundary(parcel.parcel_path)

    from model_lab.experiments.run_layout_experiment import DEFAULT_ZONING

    zoning_rules = DEFAULT_ZONING
    base_constraints = default_constraints(boundary)
    parcel_polygon = parcel_shapely_from_constraints(base_constraints)
    parcel_area_sqft = float(parcel_polygon.area)
    parcel_geojson = dict(mapping(parcel_polygon))

    candidates = generate_candidate_street_networks(
        parcel_polygon=parcel_polygon,
        road_width_ft=40.0,
    )
    candidates_by_topology: dict = {}
    for c in candidates:
        candidates_by_topology.setdefault(c.topology, []).append(c)

    ranker = StrategyRanker.load()

    per_seed: list[dict] = []
    baseline_best_list: list[float] = []
    standard_best_list: list[float] = []
    diverse_best_list: list[float] = []
    standard_oracle_ret_list: list[float] = []
    diverse_oracle_ret_list: list[float] = []
    standard_lots_mean: list[float] = []
    diverse_lots_mean: list[float] = []
    standard_road_eff_mean: list[float] = []
    diverse_road_eff_mean: list[float] = []
    baseline_times: list[float] = []
    standard_times: list[float] = []
    diverse_times: list[float] = []
    standard_diversity: list[int] = []
    diverse_diversity: list[int] = []

    for seed in seeds:
        strategies = generate_strategies(pool_size, include_presets=True, seed=seed)

        baseline_results, baseline_time = run_baseline(
            base_constraints, candidates_by_topology, zoning_rules, strategies
        )
        baseline_times.append(baseline_time)
        if not baseline_results:
            continue

        by_key: dict[tuple[str, str, str, int], float] = {}
        for row in baseline_results:
            by_key[_strategy_key(row["strategy"])] = float(row["overall_score"])

        baseline_best = max(float(r["overall_score"]) for r in baseline_results)
        baseline_best_list.append(baseline_best)
        oracle_avg_top_n = _safe_mean(
            sorted((float(r["overall_score"]) for r in baseline_results), reverse=True)[:top_n]
        )

        road_graphs = [
            _build_road_graph_for_strategy(s, parcel_polygon, candidates_by_topology, base_constraints)
            for s in strategies
        ]
        predictions = ranker.rank_strategies(
            parcel_area_sqft=parcel_area_sqft,
            parcel_polygon=parcel_geojson,
            strategies=[s.to_dict() for s in strategies],
            road_graphs=road_graphs,
            top_n=None,
        )

        standard_selected = predictions[:top_n]
        if diversity_method == "mmr":
            diverse_selected = select_diverse_predictions(
                predictions=predictions, top_n=top_n, lambda_diversity=lambda_diversity
            )
        else:
            diverse_selected = select_road_type_coverage_predictions(
                predictions=predictions, top_n=top_n
            )

        standard_results, standard_time = _simulate_selected(
            standard_selected, base_constraints, candidates_by_topology, zoning_rules
        )
        diverse_results, diverse_time = _simulate_selected(
            diverse_selected, base_constraints, candidates_by_topology, zoning_rules
        )
        standard_times.append(standard_time)
        diverse_times.append(diverse_time)

        standard_best = max((float(r["overall_score"]) for r in standard_results), default=0.0)
        diverse_best = max((float(r["overall_score"]) for r in diverse_results), default=0.0)
        standard_best_list.append(standard_best)
        diverse_best_list.append(diverse_best)

        standard_selected_scores = [
            by_key.get(_strategy_key(pred.strategy), 0.0) for pred in standard_selected
        ]
        diverse_selected_scores = [
            by_key.get(_strategy_key(pred.strategy), 0.0) for pred in diverse_selected
        ]
        standard_avg_actual = _safe_mean(standard_selected_scores)
        diverse_avg_actual = _safe_mean(diverse_selected_scores)
        standard_oracle_ret = standard_avg_actual / max(oracle_avg_top_n, 1e-9)
        diverse_oracle_ret = diverse_avg_actual / max(oracle_avg_top_n, 1e-9)
        standard_oracle_ret_list.append(standard_oracle_ret)
        diverse_oracle_ret_list.append(diverse_oracle_ret)

        standard_lots_mean.append(_safe_mean([float(r["lot_count"]) for r in standard_results]))
        diverse_lots_mean.append(_safe_mean([float(r["lot_count"]) for r in diverse_results]))
        standard_road_eff_mean.append(_safe_mean([_road_efficiency(r) for r in standard_results]))
        diverse_road_eff_mean.append(_safe_mean([_road_efficiency(r) for r in diverse_results]))

        standard_diversity.append(len({_strategy_key(p.strategy)[0] for p in standard_selected}))
        diverse_diversity.append(len({_strategy_key(p.strategy)[0] for p in diverse_selected}))

        per_seed.append(
            {
                "seed": seed,
                "baseline_best_score": baseline_best,
                "standard_best_score": standard_best,
                "diverse_best_score": diverse_best,
                "standard_best_retention": standard_best / max(baseline_best, 1e-9),
                "diverse_best_retention": diverse_best / max(baseline_best, 1e-9),
                "standard_oracle_topn_retention": standard_oracle_ret,
                "diverse_oracle_topn_retention": diverse_oracle_ret,
                "standard_road_type_diversity": standard_diversity[-1],
                "diverse_road_type_diversity": diverse_diversity[-1],
            }
        )

    summary = {
        "parcel": parcel.name,
        "parcel_path": str(parcel.parcel_path) if parcel.parcel_path else None,
        "pool_size": pool_size,
        "top_n": top_n,
        "lambda_diversity": lambda_diversity,
        "diversity_method": diversity_method,
        "seed_count": len(seeds),
        "metrics": {
            "baseline_best_score_mean": _safe_mean(baseline_best_list),
            "standard_best_score_mean": _safe_mean(standard_best_list),
            "diverse_best_score_mean": _safe_mean(diverse_best_list),
            "standard_best_retention_mean": _safe_mean(
                [s / max(b, 1e-9) for s, b in zip(standard_best_list, baseline_best_list)]
            ),
            "diverse_best_retention_mean": _safe_mean(
                [s / max(b, 1e-9) for s, b in zip(diverse_best_list, baseline_best_list)]
            ),
            "standard_oracle_topn_retention_mean": _safe_mean(standard_oracle_ret_list),
            "diverse_oracle_topn_retention_mean": _safe_mean(diverse_oracle_ret_list),
            "standard_mean_lot_count": _safe_mean(standard_lots_mean),
            "diverse_mean_lot_count": _safe_mean(diverse_lots_mean),
            "standard_mean_road_efficiency": _safe_mean(standard_road_eff_mean),
            "diverse_mean_road_efficiency": _safe_mean(diverse_road_eff_mean),
            "standard_mean_road_type_diversity": _safe_mean(standard_diversity),
            "diverse_mean_road_type_diversity": _safe_mean(diverse_diversity),
            "baseline_time_mean_s": _safe_mean(baseline_times),
            "standard_time_mean_s": _safe_mean(standard_times),
            "diverse_time_mean_s": _safe_mean(diverse_times),
            "standard_speedup_vs_baseline": _safe_mean(
                [b / max(s, 1e-9) for b, s in zip(baseline_times, standard_times)]
            ),
            "diverse_speedup_vs_baseline": _safe_mean(
                [b / max(d, 1e-9) for b, d in zip(baseline_times, diverse_times)]
            ),
        },
        "per_seed": per_seed,
    }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark diversity-aware re-ranking in model_lab.")
    parser.add_argument("--pool-size", type=int, default=96)
    parser.add_argument("--top-n", type=int, default=8)
    parser.add_argument("--seed-start", type=int, default=0)
    parser.add_argument("--seed-count", type=int, default=20)
    parser.add_argument("--lambda-diversity", type=float, default=0.15)
    parser.add_argument(
        "--diversity-method",
        type=str,
        default="road_type_coverage",
        choices=["road_type_coverage", "mmr"],
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "model_lab" / "datasets" / "layout_training" / "diversity_ranked_benchmark.json",
    )
    args = parser.parse_args()

    parcels = [
        ParcelSpec(name="default_rectangular", parcel_path=None),
        ParcelSpec(
            name="sample_irregular",
            parcel_path=REPO_ROOT / "data" / "sample_irregular_parcel.geojson",
        ),
    ]
    seeds = list(range(args.seed_start, args.seed_start + args.seed_count))

    results = []
    for parcel in parcels:
        report = run_case(
            parcel=parcel,
            pool_size=args.pool_size,
            top_n=args.top_n,
            seeds=seeds,
            lambda_diversity=args.lambda_diversity,
            diversity_method=args.diversity_method,
        )
        results.append(report)

    output_payload = {
        "experiment": "diversity_ranked_benchmark",
        "pool_size": args.pool_size,
        "top_n": args.top_n,
        "seed_start": args.seed_start,
        "seed_count": args.seed_count,
        "lambda_diversity": args.lambda_diversity,
        "diversity_method": args.diversity_method,
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output_payload, indent=2), encoding="utf-8")

    print(f"Saved benchmark report to {args.output}")
    for row in results:
        m = row["metrics"]
        print(
            f"[{row['parcel']}] "
            f"std_ret={m['standard_best_retention_mean']:.3f} "
            f"div_ret={m['diverse_best_retention_mean']:.3f} "
            f"std_oracle={m['standard_oracle_topn_retention_mean']:.3f} "
            f"div_oracle={m['diverse_oracle_topn_retention_mean']:.3f} "
            f"std_div={m['standard_mean_road_type_diversity']:.2f} "
            f"div_div={m['diverse_mean_road_type_diversity']:.2f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
