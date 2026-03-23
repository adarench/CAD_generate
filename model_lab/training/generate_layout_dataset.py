"""
Automatic Layout Dataset Generator — model_lab  (Phase 2)

Runs parcel × strategy simulations in parallel and writes JSONL training data.
Each record now includes a full road graph alongside layout metrics.

Usage:
    python model_lab/training/generate_layout_dataset.py --runs 20

    python model_lab/training/generate_layout_dataset.py \\
        --runs 1000 --source synthetic --workers 8

    python model_lab/training/generate_layout_dataset.py \\
        --runs 5000 --source mixed --workers 8 --strategies sweep

    python model_lab/training/generate_layout_dataset.py \\
        --runs 1000 --source local_cache --workers 4

Output:
    model_lab/datasets/layout_training/layout_examples.jsonl

Record schema (Phase 2):
    {
      "unit_id":         int,
      "parcel_id":       str,
      "parcel_area_sqft": float,
      "parcel_source":   "synthetic" | "local_cache" | "postgis",
      "parcel_polygon":  GeoJSON dict,
      "strategy":        { road_type, entry_point, culdesac_count, density_goal },
      "road_graph": {
        "nodes":   [{"id": int, "x": float, "y": float}, ...],
        "edges":   [{"from": int, "to": int, "length": float, "coords": [...]}, ...],
        "metrics": { node_count, edge_count, intersection_count, dead_end_count,
                     avg_edge_length_ft, max_edge_length_ft, total_road_length_ft,
                     road_density_ft_per_acre, graph_diameter }
      },
      "layout_metrics":  { lot_count, avg_lot_area_sqft, road_length_ft,
                           developable_area_sqft, parcel_area_sqft,
                           network_topology, network_orientation,
                           graph_node_count, graph_edge_count,
                           intersection_count, dead_end_count,
                           avg_edge_length_ft, road_density_ft_per_acre,
                           graph_diameter, ... },
      "score":           { yield_score, efficiency_score, overall_score },
      "generated_at":    ISO timestamp
    }

Safety:
    This script never modifies production code.
    ai_subdivision and other backend modules are imported read-only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

# ---------------------------------------------------------------------------
# Path setup — repo root must be in sys.path for all imports to resolve
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# ---------------------------------------------------------------------------
# Model lab imports (production code never imports from model_lab)
# ---------------------------------------------------------------------------
from model_lab.strategy_models.basic_strategy_generator import (
    full_sweep_strategies,
    generate_strategies,
    preset_strategies,
)
from model_lab.strategy_models.strategy_interface import LayoutStrategy
from model_lab.training.layout_runner import LayoutResult, run_layout
from model_lab.training.layout_scoring import score_layout
from model_lab.training.parcel_loader import ParcelSample, load_parcels

# ---------------------------------------------------------------------------
# Output path
# ---------------------------------------------------------------------------
DATASET_DIR = REPO_ROOT / "model_lab" / "datasets" / "layout_training"
DATASET_FILE = DATASET_DIR / "layout_examples.jsonl"


# ---------------------------------------------------------------------------
# Work unit
# ---------------------------------------------------------------------------

@dataclass
class WorkUnit:
    """A single (parcel, strategy) simulation job."""
    parcel: ParcelSample
    strategy: LayoutStrategy
    unit_id: int


# ---------------------------------------------------------------------------
# Worker function (must be top-level for multiprocessing pickling)
# ---------------------------------------------------------------------------

def _execute_work_unit(unit: WorkUnit) -> dict:
    """
    Execute one layout simulation — road graph extraction included.

    Runs in a worker process — no shared state.
    Returns a dict ready for JSONL serialisation.
    """
    try:
        result: LayoutResult = run_layout(unit.parcel, unit.strategy)
        score = score_layout(result.metrics)

        return {
            "unit_id": unit.unit_id,
            "parcel_id": unit.parcel.parcel_id,
            "parcel_area_sqft": unit.parcel.area_sqft,
            "parcel_source": unit.parcel.source,
            "parcel_polygon": unit.parcel.geometry_geojson,
            "strategy": unit.strategy.to_dict(),
            "road_graph": result.road_graph.to_dict(),
            "layout_metrics": result.metrics.to_dict(),
            "score": score.to_dict(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as exc:
        return {
            "_error": str(exc),
            "_traceback": traceback.format_exc(limit=5),
            "_unit_id": unit.unit_id,
            "parcel_id": unit.parcel.parcel_id,
            "strategy": unit.strategy.to_dict(),
        }


# ---------------------------------------------------------------------------
# Dataset writer
# ---------------------------------------------------------------------------

class DatasetWriter:
    """Appends JSONL records to the output file."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        self._file = open(path, "a", encoding="utf-8")
        self.written = 0
        self.errors = 0

    def write(self, record: dict) -> None:
        if "_error" in record:
            self.errors += 1
        else:
            self._file.write(json.dumps(record) + "\n")
            self._file.flush()
            self.written += 1

    def close(self) -> None:
        self._file.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


# ---------------------------------------------------------------------------
# Summary statistics
# ---------------------------------------------------------------------------

def _print_summary(records: List[dict], elapsed_sec: float) -> None:
    good = [r for r in records if "_error" not in r]
    bad  = [r for r in records if "_error" in r]
    total = len(records)

    print("\n" + "=" * 64)
    print("DATASET GENERATION SUMMARY  (Phase 2 — Road Graph Layer)")
    print("=" * 64)
    print(f"  Total simulations run : {total}")
    print(f"  Successful examples   : {len(good)}")
    print(f"  Failures              : {len(bad)}")
    print(f"  Elapsed               : {elapsed_sec:.1f}s  ({total / max(elapsed_sec, 1):.1f} runs/sec)")

    if not good:
        print("\n  No successful examples generated.")
        return

    # Lot yield stats
    lot_counts = [r["layout_metrics"]["lot_count"] for r in good]
    scores     = [r["score"]["overall_score"] for r in good]
    print(f"\n  Avg lot yield         : {sum(lot_counts) / len(lot_counts):.1f} lots")
    print(f"  Max lot yield         : {max(lot_counts)} lots")

    # Graph stats
    node_counts  = [r["road_graph"]["metrics"]["node_count"]         for r in good]
    ix_counts    = [r["road_graph"]["metrics"]["intersection_count"] for r in good]
    de_counts    = [r["road_graph"]["metrics"]["dead_end_count"]     for r in good]
    avg_el       = [r["road_graph"]["metrics"]["avg_edge_length_ft"] for r in good]
    diameters    = [r["road_graph"]["metrics"]["graph_diameter"]     for r in good]

    print(f"\n  Road Graph stats (avg across {len(good)} examples):")
    print(f"    avg nodes            : {sum(node_counts) / len(node_counts):.1f}")
    print(f"    avg intersections    : {sum(ix_counts) / len(ix_counts):.1f}")
    print(f"    avg dead ends        : {sum(de_counts) / len(de_counts):.1f}")
    print(f"    avg edge length (ft) : {sum(avg_el) / len(avg_el):.1f}")
    print(f"    avg graph diameter   : {sum(diameters) / len(diameters):.1f}")

    # Topology breakdown
    topology_counts: dict = {}
    topology_lots: dict   = {}
    topology_nodes: dict  = {}
    for r in good:
        topo = r["layout_metrics"]["network_topology"]
        topology_counts[topo] = topology_counts.get(topo, 0) + 1
        topology_lots.setdefault(topo, []).append(r["layout_metrics"]["lot_count"])
        topology_nodes.setdefault(topo, []).append(
            r["road_graph"]["metrics"]["node_count"]
        )

    print("\n  Topology breakdown:")
    for topo in sorted(topology_counts):
        avg_l = sum(topology_lots[topo])  / len(topology_lots[topo])
        avg_n = sum(topology_nodes[topo]) / len(topology_nodes[topo])
        print(f"    {topo:10s}  count={topology_counts[topo]:4d}  avg_lots={avg_l:.1f}  avg_nodes={avg_n:.1f}")

    # Top-scoring examples
    print("\n  Top 5 examples by overall score:")
    top5 = sorted(good, key=lambda r: r["score"]["overall_score"], reverse=True)[:5]
    for r in top5:
        m = r["layout_metrics"]
        gm = r["road_graph"]["metrics"]
        print(
            f"    {r['parcel_id'][:24]:24s}  "
            f"topo={m['network_topology']:10s}  "
            f"lots={m['lot_count']:2d}  "
            f"nodes={gm['node_count']:2d}  "
            f"ixn={gm['intersection_count']:1d}  "
            f"score={r['score']['overall_score']:.3f}"
        )

    # Confirm road_graph present in all records
    has_graph = sum(1 for r in good if r.get("road_graph"))
    print(f"\n  road_graph present    : {has_graph}/{len(good)} records ✓")
    print(f"  Output file           : {DATASET_FILE}")
    print("=" * 64)


# ---------------------------------------------------------------------------
# Main generation loop
# ---------------------------------------------------------------------------

def generate_dataset(
    num_parcels: int = 50,
    source: str = "auto",
    strategy_mode: str = "preset",
    num_strategies: Optional[int] = None,
    workers: int = 4,
    min_area_sqft: float = 87120.0,
    county: Optional[str] = None,
    database_url: Optional[str] = None,
    seed: Optional[int] = None,
    append: bool = True,
) -> List[dict]:
    import time
    start_time = time.time()

    # 1. Load parcels
    print(f"Loading parcels (source={source}, count={num_parcels})...")
    parcels = load_parcels(
        source=source,
        count=num_parcels,
        min_area_sqft=min_area_sqft,
        county=county,
        database_url=database_url,
        synthetic_seed=seed,
    )
    print(f"  Loaded {len(parcels)} parcels")
    if not parcels:
        print("No parcels available. Exiting.")
        return []

    # 2. Build strategies
    if strategy_mode == "sweep":
        strategies = full_sweep_strategies()
    elif strategy_mode == "random":
        n = num_strategies or 8
        strategies = generate_strategies(count=n, include_presets=True, seed=seed)
    else:
        strategies = preset_strategies()

    print(f"  Using {len(strategies)} strategies per parcel")
    total_runs = len(parcels) * len(strategies)
    print(f"  Total simulations planned: {total_runs}")

    # 3. Build work queue
    work_units = [
        WorkUnit(parcel=parcel, strategy=strategy, unit_id=idx)
        for idx, (parcel, strategy) in enumerate(
            (p, s) for p in parcels for s in strategies
        )
    ]

    # 4. Execute
    all_records: List[dict] = []
    if not append and DATASET_FILE.exists():
        DATASET_FILE.unlink()

    use_workers = max(1, min(workers, len(work_units)))
    print(f"\nRunning {len(work_units)} simulations on {use_workers} worker(s)...\n")

    with DatasetWriter(DATASET_FILE) as writer:
        if use_workers == 1:
            for i, unit in enumerate(work_units):
                record = _execute_work_unit(unit)
                writer.write(record)
                all_records.append(record)
                status = "OK" if "_error" not in record else f"ERR: {record['_error'][:60]}"
                if (i + 1) % 10 == 0 or (i + 1) == len(work_units):
                    print(f"  [{i + 1:4d}/{len(work_units)}]  {status}")
        else:
            with ProcessPoolExecutor(max_workers=use_workers) as pool:
                futures = {pool.submit(_execute_work_unit, unit): unit for unit in work_units}
                completed = 0
                for future in as_completed(futures):
                    record = future.result()
                    writer.write(record)
                    all_records.append(record)
                    completed += 1
                    status = "OK" if "_error" not in record else "ERR"
                    if completed % 25 == 0 or completed == len(work_units):
                        print(
                            f"  [{completed:4d}/{len(work_units)}]  "
                            f"written={writer.written}  errors={writer.errors}  {status}"
                        )

    elapsed = time.time() - start_time
    _print_summary(all_records, elapsed)
    return all_records


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate road-graph layout training dataset.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--runs",            type=int,   default=20,
                        help="Parcel sample count. Total sims = runs × strategies.")
    parser.add_argument("--source",          choices=["auto","postgis","local_cache","synthetic","mixed"],
                        default="auto")
    parser.add_argument("--workers",         type=int,   default=4)
    parser.add_argument("--strategies",      choices=["preset","random","sweep"], default="preset")
    parser.add_argument("--num-strategies",  type=int,   default=None)
    parser.add_argument("--county",          type=str,   default=None)
    parser.add_argument("--min-area-acres",  type=float, default=2.0)
    parser.add_argument("--seed",            type=int,   default=None)
    parser.add_argument("--no-append",       action="store_true",
                        help="Overwrite output file instead of appending.")
    args = parser.parse_args()

    generate_dataset(
        num_parcels=args.runs,
        source=args.source,
        strategy_mode=args.strategies,
        num_strategies=args.num_strategies,
        workers=args.workers,
        min_area_sqft=args.min_area_acres * 43560.0,
        county=args.county,
        database_url=os.getenv("DATABASE_URL"),
        seed=args.seed,
        append=not args.no_append,
    )


if __name__ == "__main__":
    main()
