"""
Production Layout Engine Validation

Compares production engine outputs vs model_lab reference implementation,
and verifies production code has no model_lab imports.

Run from repo root:
    python apps/python-api/scripts/validate_layout_engine.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PROD_API   = REPO_ROOT / "apps" / "python-api"
sys.path.insert(0, str(PROD_API))

import math
from shapely.geometry import Polygon

# ---------------------------------------------------------------------------
# 1. Model_lab isolation check
# ---------------------------------------------------------------------------

def check_isolation():
    print("[1] Production code isolation check")
    print("─" * 60)
    prod_py = list((REPO_ROOT / "apps").rglob("*.py"))
    violations = []
    for f in prod_py:
        # Exclude validation/debug scripts (they may intentionally cross-check model_lab)
        if "scripts" in f.parts:
            continue
        try:
            content = f.read_text()
            if "import model_lab" in content or "from model_lab" in content:
                violations.append(str(f.relative_to(REPO_ROOT)))
        except Exception:
            pass
    if violations:
        print(f"  FAIL — {len(violations)} file(s) import model_lab:")
        for v in violations:
            print(f"    {v}")
    else:
        print(f"  PASS — {len(prod_py)} files, 0 model_lab imports")
    print()


# ---------------------------------------------------------------------------
# 2. Graph generator smoke test
# ---------------------------------------------------------------------------

def make_square_parcel(acres: float) -> Polygon:
    side_ft = math.sqrt(acres * 43560.0)
    h = side_ft / 2
    return Polygon([(-h, -h), (h, -h), (h, h), (-h, h)])


def test_graph_generator():
    print("[2] Graph generator smoke test")
    print("─" * 60)
    from services.layout_engine.graph_generator import generate_candidates

    parcel = make_square_parcel(10.0)
    area_sqft = parcel.area

    t0 = time.perf_counter()
    candidates = generate_candidates(parcel, area_sqft, n=30, seed=42)
    elapsed = time.perf_counter() - t0

    types_seen = {c.generator_type for c in candidates}
    print(f"  Generated:    {len(candidates)} candidates in {elapsed*1000:.0f} ms")
    print(f"  Types seen:   {sorted(types_seen)}")
    print(f"  Lines range:  {min(len(c.centerlines) for c in candidates)}–"
          f"{max(len(c.centerlines) for c in candidates)} centerlines")

    all_types = {"spine", "loop_custom", "grid", "herringbone", "radial", "t_junction"}
    missing = all_types - types_seen
    if missing:
        print(f"  WARN — missing types: {missing}")
    else:
        print(f"  PASS — all 6 topology types represented")
    print()
    return candidates, parcel, area_sqft


# ---------------------------------------------------------------------------
# 3. Lot subdivision smoke test
# ---------------------------------------------------------------------------

def test_lot_subdivision(candidates, parcel, area_sqft):
    print("[3] Lot subdivision smoke test")
    print("─" * 60)
    from services.layout_engine.lot_subdivision import run_subdivision, score_subdivision

    results = []
    for c in candidates[:10]:
        r = run_subdivision(c.centerlines, parcel)
        if r:
            score = score_subdivision(r)
            results.append((score, c.generator_type, r))

    if not results:
        print("  FAIL — no subdivision results produced")
        return []

    results.sort(reverse=True)
    print(f"  Subdivided:   {len(results)}/10 candidates produced valid results")
    print(f"  Score range:  {results[-1][0]:.4f}–{results[0][0]:.4f}")
    print()
    print(f"  {'Rank':>4}  {'Type':16}  {'Lots':>4}  {'Score':>7}  {'DevRatio':>9}")
    print(f"  {'─'*4}  {'─'*16}  {'─'*4}  {'─'*7}  {'─'*9}")
    for i, (score, gt, r) in enumerate(results[:5], 1):
        m = r.metrics
        print(f"  {i:4d}  {gt:16}  {m['lot_count']:4d}  {score:7.4f}  "
              f"{m['dev_area_ratio']:9.4f}")
    print()
    return results


# ---------------------------------------------------------------------------
# 4. Graph prior inference smoke test
# ---------------------------------------------------------------------------

def test_prior_inference(candidates, parcel, area_sqft):
    print("[4] Graph prior inference smoke test")
    print("─" * 60)

    from services.layout_engine.graph_prior_inference import get_prior
    prior = get_prior()
    if prior is None:
        print("  SKIP — model not found at apps/python-api/models/graph_prior.pkl")
        print()
        return

    t0 = time.perf_counter()
    scored = prior.rank_networks(candidates[:20], parcel, area_sqft)
    elapsed = time.perf_counter() - t0

    print(f"  Scored:       {len(scored)} networks in {elapsed*1000:.1f} ms")
    print(f"  Score range:  {scored[-1].predicted_score:.4f}–{scored[0].predicted_score:.4f}")
    print(f"  Top types:    {[s.network.generator_type for s in scored[:5]]}")
    print(f"  PASS")
    print()


# ---------------------------------------------------------------------------
# 5. Full layout search smoke test
# ---------------------------------------------------------------------------

def test_layout_search(parcel, area_sqft):
    print("[5] Full layout search smoke test")
    print("─" * 60)

    from services.layout_engine.layout_search import run_layout_search

    def dummy_to_lnglat(x_ft, y_ft):
        # Convert from local feet back to approximate WGS84 (using Utah center)
        # For validation: just use identity (result coords in feet, not degrees)
        return [x_ft / 364000.0, y_ft / 364000.0]

    t0 = time.perf_counter()
    results = run_layout_search(
        parcel_polygon=parcel,
        area_sqft=area_sqft,
        to_lnglat=dummy_to_lnglat,
        n_candidates=12,
        n_top=3,
        seed=0,
    )
    elapsed = time.perf_counter() - t0

    if not results:
        print("  FAIL — no layout results")
        return

    print(f"  Generated:    {len(results)} layout candidates in {elapsed*1000:.0f} ms")
    for r in results:
        m = r.result.metrics
        geojson_features = len(r.geojson.get("features", []))
        print(f"  Rank {r.rank}: {r.network.generator_type:16} "
              f"score={r.score:.4f}  lots={m['lot_count']}  "
              f"geojson_features={geojson_features}")
    print(f"  PASS")
    print()


# ---------------------------------------------------------------------------
# 6. Cross-check vs model_lab (optional — only if model_lab importable)
# ---------------------------------------------------------------------------

def test_model_lab_comparison(parcel, area_sqft):
    print("[6] model_lab cross-check (optional)")
    print("─" * 60)
    try:
        sys.path.insert(0, str(REPO_ROOT))
        from model_lab.subdivision.subdivision_engine import run_subdivision as ml_run_sub, score_subdivision_result
        from model_lab.graph_models.graph_generator import generate_graph_candidates
        import json

        parcel_geojson = {
            "type": "Polygon",
            "coordinates": [[list(pt) for pt in parcel.exterior.coords]],
        }
        ml_candidates = generate_graph_candidates(
            parcel_geojson=parcel_geojson,
            parcel_area_sqft=area_sqft,
            n=6,
            seed=42,
        )
        ml_scores = []
        for c in ml_candidates:
            r = ml_run_sub(c, parcel)
            if r:
                ml_scores.append(score_subdivision_result(r))

        from services.layout_engine.graph_generator import generate_candidates
        from services.layout_engine.lot_subdivision import run_subdivision as prod_run_sub, score_subdivision

        prod_candidates = generate_candidates(parcel, area_sqft, n=6, seed=42)
        prod_scores = []
        for c in prod_candidates:
            r = prod_run_sub(c.centerlines, parcel)
            if r:
                prod_scores.append(score_subdivision(r))

        if ml_scores and prod_scores:
            ml_avg  = sum(ml_scores) / len(ml_scores)
            prod_avg = sum(prod_scores) / len(prod_scores)
            diff = abs(prod_avg - ml_avg) / max(ml_avg, 1e-9)
            print(f"  model_lab avg score: {ml_avg:.4f} (n={len(ml_scores)})")
            print(f"  production avg score:{prod_avg:.4f} (n={len(prod_scores)})")
            print(f"  Score difference:    {diff:.1%}")
            if diff < 0.30:
                print(f"  PASS — within 30% tolerance (expected: different generators + scoring)")
            else:
                print(f"  WARN — difference exceeds 30%; verify pipeline parity")
        else:
            print(f"  SKIP — insufficient results for comparison")
    except ImportError as e:
        print(f"  SKIP — model_lab not importable: {e}")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("PRODUCTION LAYOUT ENGINE VALIDATION")
    print("=" * 60)
    print()

    check_isolation()
    candidates, parcel, area_sqft = test_graph_generator()
    test_lot_subdivision(candidates, parcel, area_sqft)
    test_prior_inference(candidates, parcel, area_sqft)
    test_layout_search(parcel, area_sqft)
    test_model_lab_comparison(parcel, area_sqft)

    print("=" * 60)
    print("Validation complete.")
    print("=" * 60)
