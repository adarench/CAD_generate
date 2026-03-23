"""
Real Layout Loader — model_lab

Parses production export files to extract ground-truth training examples.

Sources:
  apps/python-api/data/runs.json        — run metadata (constraints, topology)
  apps/python-api/data/exports/<id>/    — geojson layout files

Extracts from each completed run:
  - parcel polygon
  - road geometry → road graph metrics
  - lot count and area
  - strategy parameters (road width, zoning, topology, orientation)
  - reconstructed score

Output format matches layout_examples.jsonl schema so records can be
directly mixed into training datasets.

No production code is modified.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

EXPORTS_DIR = REPO_ROOT / "apps" / "python-api" / "data" / "exports"
RUNS_FILE   = REPO_ROOT / "apps" / "python-api" / "data" / "runs.json"

_REF_MAX_EFFICIENCY = 200.0
_REF_MAX_LOTS       = 40.0


# ---------------------------------------------------------------------------
# GeoJSON parsing helpers
# ---------------------------------------------------------------------------

def _polygon_area_sqft(geometry: dict) -> float:
    """Shoelace area for a Polygon geometry (coordinates in feet or deg)."""
    try:
        from shapely.geometry import shape
        return float(shape(geometry).area)
    except Exception:
        return 0.0


def _polygon_perimeter(geometry: dict) -> float:
    try:
        from shapely.geometry import shape
        return float(shape(geometry).length)
    except Exception:
        return 0.0


def _extract_road_metrics(road_features: list, parcel_area_sqft: float) -> dict:
    """
    Extract road length from road polygon features.
    Road polygons have area = length × width; we estimate length
    as the longer axis of each road polygon's bounding box.
    """
    total_road_length = 0.0
    for feat in road_features:
        geom = feat.get("geometry", {})
        try:
            from shapely.geometry import shape
            g = shape(geom)
            bounds = g.bounds
            w = bounds[2] - bounds[0]
            h = bounds[3] - bounds[1]
            # Longer axis ≈ road length
            total_road_length += max(w, h)
        except Exception:
            pass
    acres = parcel_area_sqft / 43560.0 if parcel_area_sqft > 0 else 1.0
    return {
        "total_road_length_ft": total_road_length,
        "road_density_ft_per_acre": total_road_length / max(acres, 1e-9),
    }


def _score(lot_count: int, dev_area_sqft: float, road_length_ft: float) -> dict:
    yield_score = lot_count / _REF_MAX_LOTS
    if road_length_ft > 0:
        eff_raw = dev_area_sqft / road_length_ft
        eff_score = eff_raw / _REF_MAX_EFFICIENCY
    else:
        eff_score = 0.0
    overall = 0.6 * yield_score + 0.4 * eff_score
    return {
        "overall_score":    round(overall, 6),
        "yield_score":      round(yield_score, 6),
        "efficiency_score": round(eff_score, 6),
    }


# ---------------------------------------------------------------------------
# Loads from runs.json + exports
# ---------------------------------------------------------------------------

def _entry_from_orientation(orientation: str) -> str:
    return "north" if orientation == "north_south" else "east"


def _density_from_lot_count_and_area(lot_count: int, area_sqft: float) -> str:
    area_acres = area_sqft / 43560.0
    du_per_acre = lot_count / max(area_acres, 0.1)
    if du_per_acre < 4:
        return "low"
    if du_per_acre < 8:
        return "medium"
    return "high"


def load_real_layouts(
    exports_dir: Path = EXPORTS_DIR,
    runs_file:   Path = RUNS_FILE,
    min_lot_count: int = 4,
) -> List[dict]:
    """
    Load all completed run exports and convert to training record format.

    Returns list of dicts matching layout_examples.jsonl schema.
    """
    if not runs_file.exists():
        print(f"  WARN: runs.json not found at {runs_file}")
        return []

    with open(runs_file, encoding="utf-8") as f:
        runs_data = json.load(f)

    records = []
    skipped = 0

    for run_id, run in runs_data.items():
        if run.get("status") != "completed":
            skipped += 1
            continue

        # Load geojson
        export_path = exports_dir / run_id / "subdivision_layout.geojson"
        if not export_path.exists():
            skipped += 1
            continue

        try:
            with open(export_path, encoding="utf-8") as f:
                geo = json.load(f)
        except (json.JSONDecodeError, IOError):
            skipped += 1
            continue

        features  = geo.get("features", [])
        by_layer: Dict[str, list] = {}
        for feat in features:
            layer = feat.get("properties", {}).get("layer", "?")
            by_layer.setdefault(layer, []).append(feat)

        # Extract parcel
        parcel_feats = by_layer.get("parcel", [])
        if not parcel_feats:
            skipped += 1
            continue
        parcel_geom = parcel_feats[0]["geometry"]
        parcel_area = _polygon_area_sqft(parcel_geom)
        if parcel_area < 50000:
            skipped += 1
            continue

        # Extract lots
        lot_feats   = by_layer.get("lots", [])
        lot_count   = len(lot_feats)
        if lot_count < min_lot_count:
            skipped += 1
            continue

        lot_areas       = [_polygon_area_sqft(f["geometry"]) for f in lot_feats]
        avg_lot_area    = sum(lot_areas) / len(lot_areas) if lot_areas else 0.0
        dev_area        = sum(lot_areas)

        # Extract road geometry
        road_feats  = by_layer.get("road", [])
        road_metrics = _extract_road_metrics(road_feats, parcel_area)

        # Strategy from run metadata
        ic    = run.get("inputConstraints", {})
        topo_prefs = run.get("topologyPreferences", [])
        road_type  = topo_prefs[0] if topo_prefs else "parallel"
        if road_type not in ["loop", "spine", "parallel", "culdesac"]:
            road_type = "parallel"

        road_width   = float(ic.get("roadWidth",    40.0))
        min_front    = float(ic.get("minFrontage",  60.0))
        min_depth    = float(ic.get("minDepth",    110.0))
        min_area     = float(ic.get("minArea",    6000.0))
        orientation  = ic.get("roadOrientation", "north_south")
        entry_point  = _entry_from_orientation(orientation)

        response      = run.get("response", {})
        road_length   = float(response.get("roadLengthFt", road_metrics["total_road_length_ft"]))
        winning_topo  = response.get("winningTopology", road_type)
        if winning_topo in ["loop", "spine", "parallel", "culdesac"]:
            road_type = winning_topo

        # Reconstruct target density
        area_acres   = parcel_area / 43560.0
        density_du   = lot_count / max(area_acres, 0.1)
        density_goal = _density_from_lot_count_and_area(lot_count, parcel_area)

        score = _score(lot_count, dev_area, road_length)

        # Build strategy dict (ParamStrategy-compatible)
        strategy_dict = {
            "road_type":                  road_type,
            "entry_point":               entry_point,
            "road_width_ft":             road_width,
            "min_lot_area_sqft":         min_area,
            "min_frontage_ft":           min_front,
            "min_depth_ft":              min_depth,
            "target_density_du_per_acre": round(density_du, 3),
            "density_goal":              density_goal,
            # Conceptual params — defaults
            "branch_count":          2.0,
            "branch_angle_deg":      90.0,
            "road_spacing_ft":       200.0,
            "loop_radius_ft":        150.0,
            "culdesac_radius_ft":    40.0,
            "culdesac_depth_ft":     180.0,
            "collector_length_ft":   400.0,
            "orientation_angle_deg": 0.0,
        }

        layout_metrics_dict = {
            "lot_count":             lot_count,
            "avg_lot_area_sqft":     round(avg_lot_area, 2),
            "road_length_ft":        round(road_length, 2),
            "developable_area_sqft": round(dev_area, 2),
            "parcel_area_sqft":      round(parcel_area, 2),
            "road_width_ft":         road_width,
            "network_topology":      road_type,
            "network_orientation":   orientation,
            "road_offset_ft":        0.0,
            "road_count":            len(road_feats),
            # Graph metrics — not available from exports
            "graph_node_count":             0,
            "graph_edge_count":             0,
            "intersection_count":           0,
            "dead_end_count":               0,
            "avg_edge_length_ft":           0.0,
            "max_edge_length_ft":           0.0,
            "road_density_ft_per_acre":     round(road_metrics["road_density_ft_per_acre"], 4),
            "graph_diameter":               0,
        }

        parcel_id = f"real-{run.get('parcelId', run_id)[:16]}-{run_id[:8]}"

        record = {
            "unit_id":          f"real-{run_id}",
            "parcel_id":        parcel_id,
            "parcel_area_sqft": round(parcel_area, 2),
            "parcel_source":    "real_export",
            "parcel_polygon":   parcel_geom,
            "strategy":         strategy_dict,
            "road_graph":       {"nodes": [], "edges": [], "metrics": {
                "node_count": 0, "edge_count": 0, "intersection_count": 0,
                "dead_end_count": 0, "avg_edge_length_ft": 0, "max_edge_length_ft": 0,
                "total_road_length_ft": road_length, "road_density_ft_per_acre":
                road_metrics["road_density_ft_per_acre"], "graph_diameter": 0,
            }},
            "layout_metrics":   layout_metrics_dict,
            "score":            score,
            "generated_at":     "real_export",
        }
        records.append(record)

    print(f"  Real layouts: {len(records)} loaded, {skipped} skipped")
    return records


def main() -> None:
    records = load_real_layouts()
    if records:
        out = REPO_ROOT / "model_lab" / "datasets" / "layout_training" / "real_layouts.jsonl"
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")
        print(f"  Written → {out}")

        # Summary
        scores = [r["score"]["overall_score"] for r in records]
        import numpy as np
        arr = np.array(scores)
        print(f"  Score stats: min={arr.min():.3f} median={np.median(arr):.3f} max={arr.max():.3f}")


if __name__ == "__main__":
    main()
