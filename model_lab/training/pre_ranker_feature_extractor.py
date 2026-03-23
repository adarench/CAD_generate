"""
Pre-Ranker Feature Extractor — model_lab

Combines parcel geometry features + strategy parameters into a flat feature
vector suitable for pre-simulation ranking.

Deliberately excludes:
  - road_graph metrics   (requires generate_candidate_street_networks)
  - layout_metrics       (requires generate_subdivision)
  - score fields         (the prediction target, not an input)

This is the Stage-1 feature set in the two-stage ranking architecture:

  Stage 1 (pre-ranker):   parcel + strategy  → predicted_score
  Stage 2 (post-ranker):  parcel + strategy + road_graph → refined_score

No production code is modified.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from model_lab.training.parcel_feature_extractor import (
    PARCEL_FEATURE_NAMES,
    extract_parcel_features,
)

# ---------------------------------------------------------------------------
# Strategy feature names
# ---------------------------------------------------------------------------

STRATEGY_FEATURE_NAMES: List[str] = [
    # Road topology (4 one-hot)
    "strat_road_loop",
    "strat_road_spine",
    "strat_road_parallel",
    "strat_road_culdesac",
    # Entry point (4 one-hot)
    "strat_entry_north",
    "strat_entry_south",
    "strat_entry_east",
    "strat_entry_west",
    # Density goal (3 one-hot)
    "strat_density_low",
    "strat_density_medium",
    "strat_density_high",
    # Raw count
    "strat_culdesac_count",
    # Interaction: topology × density
    "strat_loop_x_high",
    "strat_spine_x_high",
    "strat_culdesac_x_low",
    "strat_parallel_x_medium",
    # --- Phase 5: continuous engine-connected params ---
    # Defaults for template records: road_width=40, min_lot=6000,
    # min_frontage=60, min_depth=110, density_du=5.0
    "strat_road_width_ft",
    "strat_min_lot_area_sqft",
    "strat_min_frontage_ft",
    "strat_min_depth_ft",
    "strat_target_density_du_per_acre",
    # Conceptual geometry params (defaults=0 for template records)
    "strat_branch_count",
    "strat_branch_angle_deg",
    "strat_road_spacing_ft",
    "strat_loop_radius_ft",
    "strat_culdesac_radius_ft",
]

# Combined feature list (canonical ordering for numpy arrays)
ALL_PRE_RANKER_FEATURE_NAMES: List[str] = PARCEL_FEATURE_NAMES + STRATEGY_FEATURE_NAMES


# ---------------------------------------------------------------------------
# Strategy feature extractor
# ---------------------------------------------------------------------------

def _extract_strategy_features(strategy: dict) -> Dict[str, float]:
    road    = strategy.get("road_type",     "")
    entry   = strategy.get("entry_point",   "")
    cul     = float(strategy.get("culdesac_count", 0))

    # Density: prefer categorical label; derive from continuous if absent
    density = strategy.get("density_goal", "")
    if not density:
        du = float(strategy.get("target_density_du_per_acre", 5.0))
        density = "low" if du < 4.0 else "high" if du >= 8.0 else "medium"

    road_loop     = float(road == "loop")
    road_spine    = float(road == "spine")
    road_parallel = float(road == "parallel")
    road_culdesac = float(road == "culdesac")
    den_low       = float(density == "low")
    den_medium    = float(density == "medium")
    den_high      = float(density == "high")

    # Continuous params — use defaults matching production values for template records
    road_width   = float(strategy.get("road_width_ft",              40.0))
    min_lot      = float(strategy.get("min_lot_area_sqft",        6000.0))
    min_front    = float(strategy.get("min_frontage_ft",            60.0))
    min_depth    = float(strategy.get("min_depth_ft",              110.0))
    tgt_density  = float(strategy.get("target_density_du_per_acre",  5.0))
    branch_ct    = float(strategy.get("branch_count",                2.0))
    branch_ang   = float(strategy.get("branch_angle_deg",           90.0))
    spacing      = float(strategy.get("road_spacing_ft",           200.0))
    loop_r       = float(strategy.get("loop_radius_ft",            150.0))
    cul_r        = float(strategy.get("culdesac_radius_ft",         40.0))

    return {
        "strat_road_loop":          road_loop,
        "strat_road_spine":         road_spine,
        "strat_road_parallel":      road_parallel,
        "strat_road_culdesac":      road_culdesac,
        "strat_entry_north":        float(entry == "north"),
        "strat_entry_south":        float(entry == "south"),
        "strat_entry_east":         float(entry == "east"),
        "strat_entry_west":         float(entry == "west"),
        "strat_density_low":        den_low,
        "strat_density_medium":     den_medium,
        "strat_density_high":       den_high,
        "strat_culdesac_count":     cul,
        # Interactions
        "strat_loop_x_high":        road_loop    * den_high,
        "strat_spine_x_high":       road_spine   * den_high,
        "strat_culdesac_x_low":     road_culdesac * den_low,
        "strat_parallel_x_medium":  road_parallel * den_medium,
        # Continuous engine params
        "strat_road_width_ft":                road_width,
        "strat_min_lot_area_sqft":            min_lot,
        "strat_min_frontage_ft":              min_front,
        "strat_min_depth_ft":                 min_depth,
        "strat_target_density_du_per_acre":   tgt_density,
        "strat_branch_count":                 branch_ct,
        "strat_branch_angle_deg":             branch_ang,
        "strat_road_spacing_ft":              spacing,
        "strat_loop_radius_ft":               loop_r,
        "strat_culdesac_radius_ft":           cul_r,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_pre_ranker_features(record: dict) -> Dict[str, float]:
    """
    Extract pre-simulation features from a JSONL dataset record.

    Uses: parcel_polygon, parcel_area_sqft, strategy.
    Ignores: road_graph, layout_metrics, score.

    Returns a flat dict with ALL_PRE_RANKER_FEATURE_NAMES as keys.
    """
    area_sqft = float(record.get("parcel_area_sqft") or 0.0)
    geojson   = record.get("parcel_polygon", {})

    features: Dict[str, float] = {}
    features.update(extract_parcel_features(geojson, area_sqft))
    features.update(_extract_strategy_features(record.get("strategy", {})))
    return features


def records_to_arrays(
    records: list,
    target:  str = "overall_score",
    feature_names: Optional[List[str]] = None,
):
    """
    Convert JSONL records to (X, y, names) using pre-ranker features only.

    Args:
        records:       list of decoded JSONL dicts
        target:        score field to use as y
        feature_names: explicit ordering; defaults to ALL_PRE_RANKER_FEATURE_NAMES

    Returns:
        X:     (n, n_features) float32 array
        y:     (n,) float64 array
        names: list of feature name strings
    """
    import numpy as np

    names = feature_names or ALL_PRE_RANKER_FEATURE_NAMES
    X_rows, y_vals = [], []

    for rec in records:
        feat = extract_pre_ranker_features(rec)
        X_rows.append([feat.get(n, 0.0) for n in names])
        y_vals.append(float(rec.get("score", {}).get(target, 0.0)))

    X = np.array(X_rows, dtype=np.float32)
    y = np.array(y_vals, dtype=np.float64)
    return X, y, names
