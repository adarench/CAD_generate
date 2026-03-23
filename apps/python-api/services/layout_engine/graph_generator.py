"""
Production Road Graph Generator

Generates candidate road centerline networks directly from a parcel polygon.
Production strategies include grid, spine-road, and cul-de-sac.
Additional topology types are retained for fallback diversity.

All coordinates are in local feet (origin at parcel centroid, as produced by
parcel_adapter.adapt_parcel_geometry).

No model_lab imports — self-contained production implementation.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from shapely.geometry import LineString, Polygon

BBox = Tuple[float, float, float, float]  # (minx, miny, maxx, maxy)


@dataclass
class RoadNetwork:
    """A candidate road network for a parcel."""
    centerlines:    List[LineString]
    generator_type: str
    params:         dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Bbox helpers
# ---------------------------------------------------------------------------

def _bbox(poly: Polygon) -> BBox:
    return poly.bounds  # (minx, miny, maxx, maxy)


def _clamp(lines: List[LineString], poly: Polygon) -> List[LineString]:
    """Clip centerlines to parcel + small buffer to avoid edge artifacts."""
    clipped = []
    buf = poly.buffer(2.0)
    for line in lines:
        try:
            inter = line.intersection(buf)
            if inter.is_empty:
                continue
            if inter.geom_type == "LineString" and inter.length >= 10.0:
                clipped.append(inter)
            elif inter.geom_type == "MultiLineString":
                for seg in inter.geoms:
                    if seg.length >= 10.0:
                        clipped.append(seg)
        except Exception:
            if line.length >= 10.0:
                clipped.append(line)
    return clipped


def _polygon_profile(poly: Polygon) -> dict:
    minx, miny, maxx, maxy = _bbox(poly)
    width = max(maxx - minx, 1.0)
    height = max(maxy - miny, 1.0)
    bbox_area = width * height
    area = max(poly.area, 1.0)
    convexity = area / max(poly.convex_hull.area, 1.0)
    bbox_fill = area / max(bbox_area, 1.0)
    aspect_ratio = max(width / height, height / width)
    return {
        "width": width,
        "height": height,
        "min_dim": min(width, height),
        "max_dim": max(width, height),
        "convexity": convexity,
        "bbox_fill": bbox_fill,
        "aspect_ratio": aspect_ratio,
        "is_narrow": aspect_ratio >= 2.25,
        "is_irregular": convexity < 0.82 or bbox_fill < 0.62,
    }


def _candidate_is_viable(network: RoadNetwork, poly: Polygon, profile: dict) -> bool:
    if not network.centerlines:
        return False

    total_length = sum(line.length for line in network.centerlines)
    if total_length < max(60.0, profile["min_dim"] * 0.3):
        return False

    try:
        inside_length = sum(line.intersection(poly.buffer(4.0)).length for line in network.centerlines)
    except Exception:
        inside_length = total_length

    if inside_length / max(total_length, 1.0) < 0.65:
        return False

    if len(network.centerlines) >= 3 and network.generator_type in {"radial", "loop_custom", "grid"}:
        try:
            road_union = network.centerlines[0]
            for line in network.centerlines[1:]:
                road_union = road_union.union(line)
            if road_union.intersection(poly).length < max(50.0, profile["min_dim"] * 0.25):
                return False
        except Exception:
            pass

    return True


def _weighted_types(profile: dict) -> Tuple[List[str], List[float]]:
    types = list(_GENERATORS.keys())
    base_weights = dict(zip(types, _TYPE_WEIGHTS))

    if profile["is_narrow"]:
        base_weights["spine"] += 0.14
        base_weights["herringbone"] += 0.08
        base_weights["grid"] -= 0.08
        base_weights["radial"] -= 0.06
    if profile["is_irregular"]:
        base_weights["loop_custom"] += 0.12
        base_weights["t_junction"] += 0.08
        base_weights["grid"] -= 0.05
        base_weights["radial"] -= 0.05
    if profile["convexity"] > 0.93 and profile["bbox_fill"] > 0.85:
        base_weights["grid"] += 0.08
        base_weights["parallel"] = base_weights.get("parallel", 0.0)

    weights = [max(0.01, base_weights[name]) for name in types]
    return types, weights


# ---------------------------------------------------------------------------
# 1. Spine (fishbone)
# ---------------------------------------------------------------------------

def _gen_spine(poly: Polygon, rng: random.Random, **kw) -> RoadNetwork:
    minx, miny, maxx, maxy = _bbox(poly)
    w, h = maxx - minx, maxy - miny
    offset = kw.get("offset_ft", 40.0)
    spacing = kw.get("branch_spacing_ft", max(100.0, min(w, h) / 4))
    entry_side = kw.get("entry_side", rng.choice(["south", "north", "east", "west"]))

    lines = []
    if entry_side in ("south", "north"):
        cx = (minx + maxx) / 2.0
        y0 = miny + offset
        y1 = maxy - offset
        if y1 <= y0:
            y0, y1 = miny + h * 0.1, maxy - h * 0.1
        spine = LineString([(cx, y0), (cx, y1)])
        lines.append(spine)
        n = max(2, int((y1 - y0) / spacing))
        blen = (w / 2 - offset) * kw.get("branch_depth_fraction", 0.8)
        for i in range(1, n + 1):
            y = y0 + i * (y1 - y0) / (n + 1)
            lines.append(LineString([(minx + offset, y), (cx - 5, y)]))
            lines.append(LineString([(cx + 5, y), (maxx - offset, y)]))
    else:
        cy = (miny + maxy) / 2.0
        x0 = minx + offset
        x1 = maxx - offset
        if x1 <= x0:
            x0, x1 = minx + w * 0.1, maxx - w * 0.1
        lines.append(LineString([(x0, cy), (x1, cy)]))
        n = max(2, int((x1 - x0) / spacing))
        blen = (h / 2 - offset) * 0.8
        for i in range(1, n + 1):
            x = x0 + i * (x1 - x0) / (n + 1)
            lines.append(LineString([(x, miny + offset), (x, cy - 5)]))
            lines.append(LineString([(x, cy + 5), (x, maxy - offset)]))

    return RoadNetwork(
        centerlines=_clamp(lines, poly),
        generator_type="spine",
        params={"offset_ft": offset, "entry_side": entry_side},
    )


# ---------------------------------------------------------------------------
# 2. Loop
# ---------------------------------------------------------------------------

def _gen_loop(poly: Polygon, rng: random.Random, **kw) -> RoadNetwork:
    minx, miny, maxx, maxy = _bbox(poly)
    w, h = maxx - minx, maxy - miny
    offset = kw.get("offset_ft", min(w, h) * 0.12)
    add_cross = kw.get("add_cross", rng.random() < 0.4)

    lx0, ly0 = minx + offset, miny + offset
    lx1, ly1 = maxx - offset, maxy - offset
    if lx1 <= lx0 or ly1 <= ly0:
        offset = min(w, h) * 0.08
        lx0, ly0 = minx + offset, miny + offset
        lx1, ly1 = maxx - offset, maxy - offset

    lines = [
        LineString([(lx0, ly0), (lx1, ly0)]),
        LineString([(lx1, ly0), (lx1, ly1)]),
        LineString([(lx1, ly1), (lx0, ly1)]),
        LineString([(lx0, ly1), (lx0, ly0)]),
    ]

    # Entry stub
    mid_x = (lx0 + lx1) / 2
    lines.append(LineString([(mid_x, miny), (mid_x, ly0)]))

    if add_cross:
        mid_y = (ly0 + ly1) / 2
        lines.append(LineString([(lx0, mid_y), (lx1, mid_y)]))
        lines.append(LineString([(mid_x, ly0), (mid_x, ly1)]))

    return RoadNetwork(
        centerlines=_clamp(lines, poly),
        generator_type="loop_custom",
        params={"offset_ft": offset, "add_cross": add_cross},
    )


# ---------------------------------------------------------------------------
# 3. Grid (novel — not in production templates)
# ---------------------------------------------------------------------------

def _gen_grid(poly: Polygon, rng: random.Random, **kw) -> RoadNetwork:
    minx, miny, maxx, maxy = _bbox(poly)
    w, h = maxx - minx, maxy - miny
    offset = kw.get("offset_ft", 40.0)
    n_x = kw.get("n_x", max(2, min(5, int(w / 150))))
    n_y = kw.get("n_y", max(2, min(6, int(h / 120))))

    gx0, gy0 = minx + offset, miny + offset
    gx1, gy1 = maxx - offset, maxy - offset
    if gx1 <= gx0 or gy1 <= gy0:
        offset = min(w, h) * 0.08
        gx0, gy0 = minx + offset, miny + offset
        gx1, gy1 = maxx - offset, maxy - offset

    xs = [gx0 + i * (gx1 - gx0) / (n_x - 1) for i in range(n_x)] if n_x > 1 else [gx0]
    ys = [gy0 + j * (gy1 - gy0) / (n_y - 1) for j in range(n_y)] if n_y > 1 else [gy0]

    lines = []
    for x in xs:
        lines.append(LineString([(x, gy0), (x, gy1)]))
    for y in ys:
        lines.append(LineString([(gx0, y), (gx1, y)]))

    # Entry stub
    mid_x = xs[len(xs) // 2]
    lines.append(LineString([(mid_x, miny), (mid_x, gy0)]))

    return RoadNetwork(
        centerlines=_clamp(lines, poly),
        generator_type="grid",
        params={"n_x": n_x, "n_y": n_y, "offset_ft": offset},
    )


# ---------------------------------------------------------------------------
# 4. Herringbone (novel)
# ---------------------------------------------------------------------------

def _gen_herringbone(poly: Polygon, rng: random.Random, **kw) -> RoadNetwork:
    minx, miny, maxx, maxy = _bbox(poly)
    w, h = maxx - minx, maxy - miny
    angle_deg = kw.get("angle_deg", rng.uniform(30.0, 60.0))
    spacing = kw.get("spacing_ft", max(100.0, min(w, h) / 4))
    offset = min(w, h) * 0.08
    rad = math.radians(angle_deg)
    branch_len = min(w, h) * 0.35

    cx = (minx + maxx) / 2.0
    y0, y1 = miny + offset, maxy - offset

    lines = [LineString([(cx, y0), (cx, y1)])]

    spine_len = y1 - y0
    n = max(2, int(spine_len / spacing))
    for i in range(1, n + 1):
        y = y0 + i * spine_len / (n + 1)
        # Left branch (angle from spine direction)
        dx = -branch_len * math.cos(rad)
        dy = branch_len * math.sin(rad)
        lines.append(LineString([(cx, y), (cx + dx, y + dy)]))
        # Right branch
        lines.append(LineString([(cx, y), (cx - dx, y + dy)]))

    lines.append(LineString([(cx, miny), (cx, y0)]))

    return RoadNetwork(
        centerlines=_clamp(lines, poly),
        generator_type="herringbone",
        params={"angle_deg": angle_deg, "spacing_ft": spacing},
    )


# ---------------------------------------------------------------------------
# 5. Radial (novel)
# ---------------------------------------------------------------------------

def _gen_radial(poly: Polygon, rng: random.Random, **kw) -> RoadNetwork:
    minx, miny, maxx, maxy = _bbox(poly)
    w, h = maxx - minx, maxy - miny
    n_spokes = kw.get("n_spokes", rng.randint(4, 8))
    n_rings = kw.get("n_rings", rng.randint(1, 2))
    hub_x = kw.get("hub_x", (minx + maxx) / 2.0)
    hub_y = kw.get("hub_y", (miny + maxy) / 2.0)
    max_r = min(w, h) / 2.0 * 0.85

    lines = []
    angle_step = 2 * math.pi / n_spokes

    for k in range(n_spokes):
        angle = k * angle_step + kw.get("rotation_rad", 0.0)
        dx, dy = math.cos(angle), math.sin(angle)
        lines.append(LineString([(hub_x, hub_y), (hub_x + dx * max_r, hub_y + dy * max_r)]))

    for ring_idx in range(1, n_rings + 1):
        r = max_r * ring_idx / (n_rings + 1)
        ring_pts = [
            (hub_x + r * math.cos(k * angle_step), hub_y + r * math.sin(k * angle_step))
            for k in range(n_spokes + 1)
        ]
        lines.append(LineString(ring_pts))

    # Entry stub
    entry_angle = math.pi * 1.5  # south
    lines.append(LineString([
        (hub_x + math.cos(entry_angle) * max_r, miny),
        (hub_x + math.cos(entry_angle) * max_r, hub_y + math.sin(entry_angle) * max_r),
    ]))

    return RoadNetwork(
        centerlines=_clamp(lines, poly),
        generator_type="radial",
        params={"n_spokes": n_spokes, "n_rings": n_rings},
    )


# ---------------------------------------------------------------------------
# 6. T-junction
# ---------------------------------------------------------------------------

def _gen_t_junction(poly: Polygon, rng: random.Random, **kw) -> RoadNetwork:
    minx, miny, maxx, maxy = _bbox(poly)
    w, h = maxx - minx, maxy - miny
    offset = kw.get("offset_ft", 40.0)

    cx = (minx + maxx) / 2.0
    cy = (miny + maxy) / 2.0

    lines = [
        LineString([(minx + offset, cy), (maxx - offset, cy)]),
        LineString([(cx, miny + offset), (cx, cy)]),
    ]
    lines.append(LineString([(cx, miny), (cx, miny + offset)]))

    return RoadNetwork(
        centerlines=_clamp(lines, poly),
        generator_type="t_junction",
        params={"offset_ft": offset},
    )


# ---------------------------------------------------------------------------
# 7. Cul-de-sac (production strategy)
# ---------------------------------------------------------------------------

def _gen_cul_de_sac(poly: Polygon, rng: random.Random, **kw) -> RoadNetwork:
    minx, miny, maxx, maxy = _bbox(poly)
    w, h = maxx - minx, maxy - miny
    vertical = h >= w
    stem_offset = kw.get("stem_offset_ft", max(28.0, min(w, h) * 0.08))
    bulb_radius = kw.get("bulb_radius_ft", max(28.0, min(w, h) * 0.12))

    lines: List[LineString] = []
    if vertical:
        cx = (minx + maxx) / 2.0
        stem_y0 = miny + stem_offset
        stem_y1 = min(maxy - stem_offset, stem_y0 + max(120.0, h * 0.55))
        lines.append(LineString([(cx, miny), (cx, stem_y0)]))
        lines.append(LineString([(cx, stem_y0), (cx, stem_y1)]))
        cy = min(stem_y1 + bulb_radius * 0.6, maxy - stem_offset)
        circle_pts = [
            (cx + bulb_radius * math.cos(theta), cy + bulb_radius * math.sin(theta))
            for theta in [2.0 * math.pi * i / 16.0 for i in range(17)]
        ]
        lines.append(LineString(circle_pts))
    else:
        cy = (miny + maxy) / 2.0
        stem_x0 = minx + stem_offset
        stem_x1 = min(maxx - stem_offset, stem_x0 + max(120.0, w * 0.55))
        lines.append(LineString([(minx, cy), (stem_x0, cy)]))
        lines.append(LineString([(stem_x0, cy), (stem_x1, cy)]))
        cx = min(stem_x1 + bulb_radius * 0.6, maxx - stem_offset)
        circle_pts = [
            (cx + bulb_radius * math.cos(theta), cy + bulb_radius * math.sin(theta))
            for theta in [2.0 * math.pi * i / 16.0 for i in range(17)]
        ]
        lines.append(LineString(circle_pts))

    return RoadNetwork(
        centerlines=_clamp(lines, poly),
        generator_type="cul_de_sac",
        params={"bulb_radius_ft": bulb_radius, "stem_offset_ft": stem_offset},
    )


# ---------------------------------------------------------------------------
# Dispatcher + candidate pool generator
# ---------------------------------------------------------------------------

_GENERATORS = {
    "spine":       _gen_spine,
    "cul_de_sac":  _gen_cul_de_sac,
    "loop_custom": _gen_loop,
    "grid":        _gen_grid,
    "herringbone": _gen_herringbone,
    "radial":      _gen_radial,
    "t_junction":  _gen_t_junction,
}

_TYPE_WEIGHTS = [0.19, 0.15, 0.18, 0.19, 0.11, 0.09, 0.09]

_PRODUCTION_STRATEGY_MAP: Dict[str, str] = {
    "grid": "grid",
    "spine-road": "spine",
    "spine": "spine",
    "cul-de-sac": "cul_de_sac",
    "cul_de_sac": "cul_de_sac",
}


def generate_candidates(
    parcel_polygon: Polygon,
    area_sqft:      float,
    n:              int = 30,
    seed:           int = 0,
) -> List[RoadNetwork]:
    """
    Generate n road network candidates for a parcel polygon.

    Candidates are drawn proportionally from all 6 topology types.
    Each call with the same seed produces the same candidates.

    Args:
        parcel_polygon: shapely Polygon in local feet
        area_sqft:      parcel area in sqft (used for parameter scaling)
        n:              number of candidates to generate
        seed:           random seed

    Returns:
        List of RoadNetwork objects.
    """
    rng = random.Random(seed)
    profile = _polygon_profile(parcel_polygon)
    types, weights = _weighted_types(profile)
    candidates: List[RoadNetwork] = []

    # Ensure at least 1 of each type
    for gt in types:
        fn = _GENERATORS[gt]
        try:
            net = fn(parcel_polygon, rng)
            if _candidate_is_viable(net, parcel_polygon, profile):
                candidates.append(net)
        except Exception:
            pass

    # Fill remainder proportionally
    remaining = n - len(candidates)
    if remaining > 0:
        chosen_types = rng.choices(types, weights=weights, k=remaining * 2)
        for gt in chosen_types:
            fn = _GENERATORS[gt]
            try:
                net = fn(parcel_polygon, rng)
                if _candidate_is_viable(net, parcel_polygon, profile):
                    candidates.append(net)
                if len(candidates) >= n:
                    break
            except Exception:
                pass

    if not candidates:
        for gt in ("spine", "loop_custom", "t_junction"):
            fn = _GENERATORS[gt]
            try:
                net = fn(parcel_polygon, rng)
                if net.centerlines:
                    candidates.append(net)
            except Exception:
                continue

    rng.shuffle(candidates)
    return candidates[:n]


def generate_candidates_multi_strategy(
    parcel_polygon: Polygon,
    area_sqft: float,
    n: int = 30,
    seed: int = 0,
    *,
    strategies: Optional[List[str]] = None,
) -> List[RoadNetwork]:
    """Generate and aggregate candidates independently per strategy.

    Production strategy names:
      - grid
      - spine-road
      - cul-de-sac
    """
    selected_strategies = strategies or ["grid", "spine-road", "cul-de-sac"]
    canonical: List[str] = []
    for strategy in selected_strategies:
        mapped = _PRODUCTION_STRATEGY_MAP.get(strategy, strategy)
        if mapped in _GENERATORS and mapped not in canonical:
            canonical.append(mapped)
    if not canonical:
        canonical = ["grid", "spine", "cul_de_sac"]

    base_rng = random.Random(seed)
    profile = _polygon_profile(parcel_polygon)
    per_strategy = max(1, math.ceil(n / max(len(canonical), 1)))
    aggregated: List[RoadNetwork] = []

    for index, strategy in enumerate(canonical):
        fn = _GENERATORS[strategy]
        local_rng = random.Random(base_rng.randint(0, 10_000_000) + index)
        produced = 0
        attempts = per_strategy * 3
        for _ in range(attempts):
            try:
                network = fn(parcel_polygon, local_rng)
            except Exception:
                continue
            if not _candidate_is_viable(network, parcel_polygon, profile):
                continue
            aggregated.append(network)
            produced += 1
            if produced >= per_strategy:
                break

    if len(aggregated) < n:
        fallback = generate_candidates(parcel_polygon, area_sqft, n=n, seed=seed + 97)
        aggregated.extend(fallback)

    deduped: List[RoadNetwork] = []
    seen = set()
    for network in aggregated:
        signature = (
            network.generator_type,
            len(network.centerlines),
            round(sum(line.length for line in network.centerlines), 1),
        )
        if signature in seen:
            continue
        seen.add(signature)
        deduped.append(network)
        if len(deduped) >= n:
            break

    if not deduped:
        return generate_candidates(parcel_polygon, area_sqft, n=n, seed=seed + 193)
    return deduped[:n]
