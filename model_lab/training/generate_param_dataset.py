"""
Parameterized Dataset Generator — model_lab

Generates a large layout dataset using ParamStrategy (continuous parameters)
instead of categorical templates only.

Produces:
  model_lab/datasets/layout_training/param_layout_examples.jsonl

Each record matches the layout_examples.jsonl schema PLUS strategy fields
from ParamStrategy (road_width_ft, min_lot_area_sqft, target_density_du_per_acre, etc.)

Usage:
    python model_lab/training/generate_param_dataset.py
    python model_lab/training/generate_param_dataset.py --num-parcels 200 --strategies-per-parcel 48
    python model_lab/training/generate_param_dataset.py --workers 4 --append

No production code is modified.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from model_lab.strategy_models.param_strategy import ParamStrategy
from model_lab.strategy_models.strategy_sampler import generate_mixed_pool, sample_random
from model_lab.training.layout_runner import run_layout_param
from model_lab.training.layout_scoring import score_layout
from model_lab.training.parcel_loader import generate_synthetic_parcels, load_parcels

OUTPUT_PATH = (
    REPO_ROOT / "model_lab" / "datasets" / "layout_training" / "param_layout_examples.jsonl"
)


# ---------------------------------------------------------------------------
# Work unit
# ---------------------------------------------------------------------------

@dataclass
class WorkUnit:
    parcel_id:   str
    parcel_area: float
    parcel_geom: dict
    strategy:    dict    # ParamStrategy.to_dict()
    unit_id:     str
    is_geographic: bool = False


def _execute_work_unit(unit: WorkUnit) -> Optional[dict]:
    """Top-level function (must be picklable for ProcessPoolExecutor)."""
    import sys
    sys.path.insert(0, str(REPO_ROOT))

    try:
        from model_lab.strategy_models.param_strategy import ParamStrategy
        from model_lab.training.layout_runner import run_layout_param
        from model_lab.training.layout_scoring import score_layout
        from model_lab.training.parcel_loader import ParcelSample

        ps = ParamStrategy.from_dict(unit.strategy)
        parcel = ParcelSample(
            parcel_id=unit.parcel_id,
            county=None, apn=None,
            area_sqft=unit.parcel_area,
            geometry_geojson=unit.parcel_geom,
            is_geographic=unit.is_geographic,
            source="synthetic",
        )

        result = run_layout_param(parcel, ps)
        if result is None:
            return None

        score = score_layout(result.metrics)

        return {
            "unit_id":          unit.unit_id,
            "parcel_id":        unit.parcel_id,
            "parcel_area_sqft": unit.parcel_area,
            "parcel_source":    "synthetic_param",
            "parcel_polygon":   unit.parcel_geom,
            "strategy":         unit.strategy,
            "road_graph":       result.road_graph.to_dict(),
            "layout_metrics":   result.metrics.to_dict(),
            "score": {
                "overall_score":    round(score.overall_score, 6),
                "yield_score":      round(score.yield_score, 6),
                "efficiency_score": round(score.efficiency_score, 6),
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        return None


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

def generate_param_dataset(
    num_parcels:           int = 150,
    strategies_per_parcel: int = 40,
    workers:               int = 4,
    output:                Path = OUTPUT_PATH,
    append:                bool = False,
    seed:                  int = 42,
    min_area_acres:        float = 3.0,
    max_area_acres:        float = 40.0,
) -> None:
    print("=" * 66)
    print("PARAMETERIZED DATASET GENERATOR")
    print("=" * 66)
    print(f"  Parcels: {num_parcels}  ×  Strategies: {strategies_per_parcel}")
    print(f"  Workers: {workers}   Target: {num_parcels * strategies_per_parcel:,} records")
    print(f"  Output:  {output}")

    # Generate parcels
    print(f"\nGenerating {num_parcels} synthetic parcels...")
    parcel_samples = generate_synthetic_parcels(
        count=num_parcels, seed=seed,
        min_acres=min_area_acres, max_acres=max_area_acres,
    )
    print(f"  Generated: {len(parcel_samples)}")

    # Generate strategy pool per parcel
    import random
    rng = random.Random(seed)

    work_units = []
    for parcel in parcel_samples:
        # Mix of grid + random parameterised strategies
        n_random   = max(1, strategies_per_parcel - 12)
        strategies = sample_random(n_random, seed=rng.randint(0, 999999))
        # Add one template per topology to anchor the dataset
        from model_lab.strategy_models.param_strategy import ROAD_TYPES, ENTRY_POINTS
        for rt in ROAD_TYPES:
            for dg in ["low", "medium", "high"]:
                if len(strategies) < strategies_per_parcel:
                    strategies.append(ParamStrategy.from_template(rt, rng.choice(ENTRY_POINTS), dg))

        strategies = strategies[:strategies_per_parcel]

        for i, strat in enumerate(strategies):
            unit_id = f"param-{parcel.parcel_id}-s{i:03d}"
            work_units.append(WorkUnit(
                parcel_id=parcel.parcel_id,
                parcel_area=parcel.area_sqft,
                parcel_geom=parcel.geometry_geojson,
                strategy=strat.to_dict(),
                unit_id=unit_id,
                is_geographic=parcel.is_geographic,
            ))

    total = len(work_units)
    print(f"  Work units: {total:,}")

    # Write output
    mode = "a" if append else "w"
    output.parent.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    written = 0
    failed  = 0
    progress_interval = max(1, total // 20)

    with open(output, mode, encoding="utf-8", buffering=1) as out_f:
        if workers <= 1:
            for i, unit in enumerate(work_units):
                rec = _execute_work_unit(unit)
                if rec:
                    out_f.write(json.dumps(rec) + "\n")
                    written += 1
                else:
                    failed += 1
                if (i + 1) % progress_interval == 0:
                    elapsed = time.time() - t0
                    rate = (i + 1) / elapsed
                    eta = (total - i - 1) / rate
                    print(f"  [{i+1}/{total}] written={written} failed={failed} "
                          f"rate={rate:.0f}/s eta={eta:.0f}s")
        else:
            with ProcessPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(_execute_work_unit, u): u for u in work_units}
                done = 0
                for future in as_completed(futures):
                    rec = future.result()
                    done += 1
                    if rec:
                        out_f.write(json.dumps(rec) + "\n")
                        out_f.flush()
                        written += 1
                    else:
                        failed += 1
                    if done % progress_interval == 0:
                        elapsed = time.time() - t0
                        rate = done / elapsed
                        eta = (total - done) / rate
                        print(f"  [{done}/{total}] written={written} failed={failed} "
                              f"rate={rate:.0f}/s eta={eta:.0f}s")

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed:.1f}s")
    print(f"  Written: {written:,}  Failed: {failed:,}  "
          f"({failed/max(total,1):.1%} failure rate)")
    print(f"  Output: {output}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate parameterized layout dataset.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--num-parcels",           type=int,   default=150)
    parser.add_argument("--strategies-per-parcel", type=int,   default=40)
    parser.add_argument("--workers",               type=int,   default=4)
    parser.add_argument("--output",                type=Path,  default=OUTPUT_PATH)
    parser.add_argument("--append",                action="store_true")
    parser.add_argument("--seed",                  type=int,   default=42)
    parser.add_argument("--min-area-acres",        type=float, default=3.0)
    parser.add_argument("--max-area-acres",        type=float, default=40.0)
    args = parser.parse_args()

    generate_param_dataset(
        num_parcels=args.num_parcels,
        strategies_per_parcel=args.strategies_per_parcel,
        workers=args.workers,
        output=args.output,
        append=args.append,
        seed=args.seed,
        min_area_acres=args.min_area_acres,
        max_area_acres=args.max_area_acres,
    )


if __name__ == "__main__":
    main()
