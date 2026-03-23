"""
Build Graph Prior Dataset — model_lab Phase 8

Generates (parcel, graph, score) triples by:
  1. Sampling diverse parcel shapes (square, rectangle, L-shape, etc.)
  2. Generating graph candidates of all 6 types for each parcel
  3. Scoring with the topo-agnostic subdivision engine
  4. Writing records to model_lab/datasets/graph_training.jsonl

Each record:
  {
    "parcel_id":       str,
    "parcel_features": {...},   # 24 parcel geometry features
    "graph_features":  {...},   # 32 graph topology features
    "generator_type":  str,
    "score":           float,
    "lot_count":       int,
    "road_length_ft":  float,
  }

No production code is modified.
"""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

OUTPUT_FILE = REPO_ROOT / "model_lab" / "datasets" / "graph_training.jsonl"


# ---------------------------------------------------------------------------
# Parcel shape generators
# ---------------------------------------------------------------------------

def _square_parcel(area_acres: float):
    side = (area_acres * 43560.0) ** 0.5
    return [(0, 0), (side, 0), (side, side), (0, side), (0, 0)]


def _rectangle_parcel(area_acres: float, aspect: float = 2.0):
    """aspect = width / height"""
    area = area_acres * 43560.0
    h = (area / aspect) ** 0.5
    w = h * aspect
    return [(0, 0), (w, 0), (w, h), (0, h), (0, 0)]


def _l_shape_parcel(area_acres: float):
    """L-shape: full square minus bottom-right quarter."""
    full = (area_acres * 43560.0 * 4.0 / 3.0) ** 0.5  # adjust for L removing 1/4
    h = full * 0.5
    return [
        (0, 0), (full, 0), (full, h), (h, h), (h, full), (0, full), (0, 0)
    ]


def _trapezoid_parcel(area_acres: float, taper: float = 0.7):
    """Wider at bottom than top (taper = top_width / bottom_width)."""
    area = area_acres * 43560.0
    # area = 0.5 * (w + w*taper) * h  →  h = 2*area / (w*(1+taper))
    w = (area * 2.0 / (1.0 + taper)) ** 0.5
    h = area * 2.0 / (w * (1.0 + taper))
    offset = (w - w * taper) / 2.0
    return [(0, 0), (w, 0), (w - offset, h), (offset, h), (0, 0)]


def _elongated_parcel(area_acres: float):
    return _rectangle_parcel(area_acres, aspect=4.0)


PARCEL_SHAPES = [
    ("square",     _square_parcel),
    ("rect_2x",    lambda a: _rectangle_parcel(a, 2.0)),
    ("rect_3x",    lambda a: _rectangle_parcel(a, 3.0)),
    ("elongated",  _elongated_parcel),
    ("trapezoid",  _trapezoid_parcel),
    ("l_shape",    _l_shape_parcel),
]

PARCEL_SIZES = [3.0, 5.0, 8.0, 12.0, 20.0]   # acres


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------

def _simulate(graph, parcel_polygon) -> Optional[Tuple[float, int, float]]:
    from model_lab.subdivision.subdivision_engine import (
        run_subdivision, score_subdivision_result,
    )
    try:
        result = run_subdivision(
            graph_or_centerlines=graph,
            parcel_polygon=parcel_polygon,
            road_width_ft=32.0,
        )
        if result is None or result.lot_count == 0:
            return None
        return score_subdivision_result(result), result.lot_count, result.road_length_ft
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Dataset generation
# ---------------------------------------------------------------------------

def build_graph_dataset(
    graphs_per_parcel: int = 60,
    output_path: Path = OUTPUT_FILE,
    verbose: bool = True,
) -> int:
    """
    Generate graph training dataset.

    Returns total number of records written.
    """
    from shapely.geometry import Polygon
    from model_lab.graph_models.graph_generator import generate_graph_candidates
    from model_lab.training.parcel_feature_extractor import extract_parcel_features
    from model_lab.training.graph_feature_extractor import extract_graph_features

    output_path.parent.mkdir(parents=True, exist_ok=True)

    total_written = 0
    t_start = time.perf_counter()

    with open(output_path, "w") as fout:
        for shape_name, shape_fn in PARCEL_SHAPES:
            for area_acres in PARCEL_SIZES:
                coords = shape_fn(area_acres)
                area_sqft = area_acres * 43560.0
                try:
                    parcel_poly = Polygon([(c[0], c[1]) for c in coords[:-1]])
                    if not parcel_poly.is_valid:
                        parcel_poly = parcel_poly.buffer(0)
                    if parcel_poly.is_empty:
                        continue
                except Exception:
                    continue

                parcel_id = f"{shape_name}_{area_acres:.0f}ac"
                geojson = {"type": "Polygon", "coordinates": [coords]}

                parcel_feats = extract_parcel_features(geojson, area_sqft)

                # Generate graphs across multiple seeds for diversity
                all_graphs = []
                for seed_offset in range(0, graphs_per_parcel, 12):
                    batch = generate_graph_candidates(
                        parcel_geojson=geojson,
                        parcel_area_sqft=area_sqft,
                        n=12,
                        seed=seed_offset * 7 + hash(shape_name) % 1000,
                    )
                    all_graphs.extend(batch)

                n_ok = 0
                for g in all_graphs:
                    sim = _simulate(g, parcel_poly)
                    if sim is None:
                        continue
                    score, lot_count, road_len = sim
                    graph_feats = extract_graph_features(g, area_sqft)

                    record = {
                        "parcel_id":      parcel_id,
                        "parcel_features": parcel_feats,
                        "graph_features":  graph_feats,
                        "generator_type":  g.generator_type,
                        "score":           round(score, 6),
                        "lot_count":       lot_count,
                        "road_length_ft":  round(road_len, 2),
                    }
                    fout.write(json.dumps(record) + "\n")
                    n_ok += 1
                    total_written += 1

                if verbose:
                    elapsed = time.perf_counter() - t_start
                    rate = total_written / max(elapsed, 0.001)
                    print(f"  {parcel_id:20s}  {n_ok:3d}/{len(all_graphs)} records  "
                          f"total={total_written}  {rate:.0f}/s")

    elapsed = time.perf_counter() - t_start
    if verbose:
        print(f"\nDone. {total_written} records → {output_path}  ({elapsed:.1f}s)")
    return total_written


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--graphs-per-parcel", type=int, default=60)
    parser.add_argument("--output", type=str, default=str(OUTPUT_FILE))
    args = parser.parse_args()
    build_graph_dataset(
        graphs_per_parcel=args.graphs_per_parcel,
        output_path=Path(args.output),
    )
