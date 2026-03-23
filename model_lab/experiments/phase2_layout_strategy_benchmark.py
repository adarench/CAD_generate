"""Phase 2 benchmark runner for layout strategy expansion research."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
GIS_ROOT = Path(__file__).resolve().parents[2]
for candidate in (WORKSPACE_ROOT, GIS_ROOT):
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

from bedrock.contracts.parcel import Parcel
from bedrock.contracts.zoning_rules import ZoningRules
from model_lab.services.candidate_generation_service import (
    STRATEGIES,
    evaluate_strategy,
    select_best_layout,
)


def _load_parcel(parcel_path: Path) -> Parcel:
    payload = json.loads(parcel_path.read_text(encoding="utf-8"))
    return Parcel(
        parcel_id=payload["parcel_id"],
        geometry=payload["geometry"],
        area_sqft=float(payload["area_sqft"]),
        centroid=payload.get("centroid"),
        bounding_box=payload.get("bounding_box"),
        jurisdiction=payload.get("jurisdiction", "unknown"),
        land_use=payload.get("land_use"),
        slope_percent=payload.get("slope_percent"),
        flood_zone=payload.get("flood_zone"),
        zoning_district=payload.get("zoning_district"),
        utilities=payload.get("utilities", []),
        access_points=payload.get("access_points", []),
        topography=payload.get("topography", {}),
        existing_structures=payload.get("existing_structures", []),
    )


def _load_zoning(zoning_path: Path, parcel_id: str) -> ZoningRules:
    payload = json.loads(zoning_path.read_text(encoding="utf-8"))
    return ZoningRules(
        parcel_id=parcel_id,
        jurisdiction=payload.get("jurisdiction"),
        district=payload.get("district", "unknown"),
        district_id=payload.get("district_id"),
        description=payload.get("description"),
        setbacks=payload.get("setbacks", {}),
        min_lot_size_sqft=payload.get("min_lot_size_sqft"),
        max_units_per_acre=payload.get("max_units_per_acre"),
        min_frontage_ft=payload.get("min_frontage_ft"),
        road_right_of_way_ft=payload.get("road_right_of_way_ft"),
        height_limit_ft=payload.get("height_limit_ft"),
        lot_coverage_max=payload.get("lot_coverage_max"),
        allowed_uses=payload.get("allowed_uses", []),
        citations=payload.get("citations", []),
        standards=payload.get("standards", []),
    )


def run_benchmark(
    *,
    parcel_dir: Path,
    zoning_file: Path,
    max_cases: int | None = None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    parcel_files = sorted(parcel_dir.glob("*.json"))
    if max_cases is not None:
        parcel_files = parcel_files[: max(0, max_cases)]

    records: list[dict[str, Any]] = []
    for parcel_file in parcel_files:
        parcel = _load_parcel(parcel_file)
        zoning = _load_zoning(zoning_file, parcel.parcel_id)

        case_candidates = []
        for strategy_name, generator in STRATEGIES.items():
            t0 = time.perf_counter()
            evaluation = evaluate_strategy(strategy_name, generator, parcel, zoning)
            runtime_ms = (time.perf_counter() - t0) * 1000.0
            records.append(
                {
                    "case_id": parcel.parcel_id,
                    "strategy": strategy_name,
                    "units": evaluation.layout.unit_count,
                    "road_length_ft": round(evaluation.layout.road_length_ft, 2),
                    "layout_score": round(float(evaluation.layout.score or 0.0), 6),
                    "runtime_ms": round(runtime_ms, 3),
                }
            )
            case_candidates.append(evaluation)

        best = select_best_layout(case_candidates)
        if best is not None:
            records.append(
                {
                    "case_id": parcel.parcel_id,
                    "strategy": "best",
                    "units": best.layout.unit_count,
                    "road_length_ft": round(best.layout.road_length_ft, 2),
                    "layout_score": round(float(best.layout.score or 0.0), 6),
                    "runtime_ms": 0.0,
                }
            )

    report = {
        "benchmark_name": "phase2_layout_strategy_benchmark",
        "total_cases": len(parcel_files),
        "strategies": list(STRATEGIES.keys()),
        "records": records,
    }
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 2 strategy benchmark.")
    parser.add_argument(
        "--parcel-dir",
        type=Path,
        default=WORKSPACE_ROOT / "test_data" / "layout_benchmark_parcels",
    )
    parser.add_argument(
        "--zoning-file",
        type=Path,
        default=WORKSPACE_ROOT / "test_data" / "benchmark_zoning" / "benchmark_case_001.json",
    )
    parser.add_argument("--max-cases", type=int, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    report = run_benchmark(
        parcel_dir=args.parcel_dir,
        zoning_file=args.zoning_file,
        max_cases=args.max_cases,
        output_path=args.output,
    )
    print(
        f"Phase2 benchmark complete: cases={report['total_cases']} "
        f"records={len(report['records'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
