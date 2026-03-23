"""
Parcel Loader — model_lab

Provides parcel geometry + metadata to the dataset generator via three sources:

  1. PostGIS  — live DB query (requires DATABASE_URL env var)
  2. Local JSON cache — apps/python-api/data/parcels.json
  3. Synthetic — procedurally generated parcels for high-volume runs

Returns ParcelSample dataclasses.  No production code is modified.
Backend modules are imported read-only where convenient.
"""

from __future__ import annotations

import asyncio
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Optional

# ---------------------------------------------------------------------------
# Repo layout
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
LOCAL_CACHE_PATH = REPO_ROOT / "apps" / "python-api" / "data" / "parcels.json"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MIN_AREA_SQFT_FOR_SUBDIVISION = 87120.0  # 2 acres — below this, subdivision is not meaningful
FEET_PER_DEGREE_LAT = 364000.0


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ParcelSample:
    """Minimal parcel representation for layout simulation."""

    parcel_id: str
    county: Optional[str]
    apn: Optional[str]
    area_sqft: float
    # GeoJSON geometry dict — may be in lng/lat degrees OR local feet
    geometry_geojson: dict
    # True when coordinates are in WGS84 degrees (requires projection to feet)
    is_geographic: bool = True
    source: str = "unknown"  # "postgis" | "local_cache" | "synthetic"


# ---------------------------------------------------------------------------
# Source 1: PostGIS
# ---------------------------------------------------------------------------

async def _query_postgis(database_url: str, limit: int, min_area_sqft: float, county: Optional[str]) -> List[ParcelSample]:
    """Async PostGIS query — run via asyncio.run() from sync callers."""
    try:
        import asyncpg  # type: ignore
    except ImportError:
        raise RuntimeError("asyncpg is required for PostGIS loading. Install it or use a different source.")

    county_clause = "AND LOWER(county) = LOWER($3)" if county else ""
    params: list = [limit, min_area_sqft]
    if county:
        params.append(county)

    conn = await asyncpg.connect(dsn=database_url)
    rows = await conn.fetch(
        f"""
        SELECT
            id,
            county,
            apn,
            area_sqft,
            ST_AsGeoJSON(geometry)::json AS geometry_geojson
        FROM parcels
        WHERE area_sqft >= $2
        {county_clause}
        ORDER BY RANDOM()
        LIMIT $1
        """,
        *params,
    )
    await conn.close()

    samples = []
    for row in rows:
        geom = row["geometry_geojson"]
        if isinstance(geom, str):
            geom = json.loads(geom)
        samples.append(
            ParcelSample(
                parcel_id=row["id"],
                county=row["county"],
                apn=row["apn"],
                area_sqft=float(row["area_sqft"] or 0.0),
                geometry_geojson=geom,
                is_geographic=True,
                source="postgis",
            )
        )
    return samples


def load_parcels_from_postgis(
    database_url: str,
    limit: int = 100,
    min_area_sqft: float = MIN_AREA_SQFT_FOR_SUBDIVISION,
    county: Optional[str] = None,
) -> List[ParcelSample]:
    """Synchronous wrapper around the async PostGIS loader."""
    return asyncio.run(_query_postgis(database_url, limit, min_area_sqft, county))


# ---------------------------------------------------------------------------
# Source 2: Local JSON cache
# ---------------------------------------------------------------------------

def load_parcels_from_local_cache(
    min_area_sqft: float = MIN_AREA_SQFT_FOR_SUBDIVISION,
    limit: Optional[int] = None,
    shuffle: bool = True,
) -> List[ParcelSample]:
    """Load parcels from the production JSON cache file (read-only)."""
    if not LOCAL_CACHE_PATH.exists():
        raise FileNotFoundError(f"Local parcel cache not found: {LOCAL_CACHE_PATH}")

    raw: dict = json.loads(LOCAL_CACHE_PATH.read_text(encoding="utf-8"))
    records = list(raw.values())
    if shuffle:
        random.shuffle(records)

    samples = []
    for record in records:
        area = float(record.get("areaSqft") or 0.0)
        if area < min_area_sqft:
            continue
        geom = record.get("geometryGeoJSON")
        if not geom:
            continue
        samples.append(
            ParcelSample(
                parcel_id=record["id"],
                county=record.get("county"),
                apn=record.get("apn"),
                area_sqft=area,
                geometry_geojson=geom if isinstance(geom, dict) else json.loads(geom),
                is_geographic=True,
                source="local_cache",
            )
        )
        if limit and len(samples) >= limit:
            break

    return samples


# ---------------------------------------------------------------------------
# Source 3: Synthetic parcel generator
# ---------------------------------------------------------------------------

def _rect_boundary(width_ft: float, height_ft: float) -> list:
    hw, hh = width_ft / 2.0, height_ft / 2.0
    return [[-hw, -hh], [hw, -hh], [hw, hh], [-hw, hh]]


def _irregular_boundary(width_ft: float, height_ft: float, rng: random.Random) -> list:
    """Generate a random irregular polygon by perturbing a rectangle."""
    hw, hh = width_ft / 2.0, height_ft / 2.0
    base = [
        [-hw, -hh],
        [hw, -hh],
        [hw, hh],
        [-hw, hh],
    ]
    jitter = min(hw, hh) * 0.25
    perturbed = [
        [x + rng.uniform(-jitter, jitter), y + rng.uniform(-jitter, jitter)]
        for x, y in base
    ]
    return perturbed


def generate_synthetic_parcels(
    count: int,
    seed: Optional[int] = None,
    min_acres: float = 3.0,
    max_acres: float = 40.0,
) -> List[ParcelSample]:
    """
    Procedurally generate `count` synthetic parcels with varied geometry.

    Coordinates are in local feet centred on the origin — no projection needed.
    These are ideal for high-volume training runs without requiring PostGIS.
    """
    rng = random.Random(seed)
    samples = []

    shapes = ["rectangle", "rectangle", "rectangle", "irregular"]  # bias toward rect
    aspect_ratios = [1.0, 1.2, 1.5, 1.8, 2.0, 2.5, 3.0]

    for i in range(count):
        area_acres = rng.uniform(min_acres, max_acres)
        area_sqft = area_acres * 43560.0
        aspect = rng.choice(aspect_ratios)
        width_ft = math.sqrt(area_sqft * aspect)
        height_ft = area_sqft / width_ft

        shape = rng.choice(shapes)
        if shape == "rectangle":
            boundary = _rect_boundary(width_ft, height_ft)
        else:
            boundary = _irregular_boundary(width_ft, height_ft, rng)

        geom = {
            "type": "Polygon",
            "coordinates": [boundary + [boundary[0]]],  # closed ring
        }

        samples.append(
            ParcelSample(
                parcel_id=f"synthetic-{i:05d}",
                county=None,
                apn=None,
                area_sqft=round(area_sqft, 2),
                geometry_geojson=geom,
                is_geographic=False,  # already in feet — no projection needed
                source="synthetic",
            )
        )

    return samples


# ---------------------------------------------------------------------------
# Public facade — auto-selects source
# ---------------------------------------------------------------------------

def load_parcels(
    source: str = "auto",
    count: int = 50,
    min_area_sqft: float = MIN_AREA_SQFT_FOR_SUBDIVISION,
    county: Optional[str] = None,
    database_url: Optional[str] = None,
    synthetic_seed: Optional[int] = None,
) -> List[ParcelSample]:
    """
    Load parcels from the best available source.

    source:
      "auto"         — PostGIS if DATABASE_URL set, else local cache, else synthetic
      "postgis"      — PostGIS only (requires database_url)
      "local_cache"  — Local JSON cache only
      "synthetic"    — Procedurally generated parcels
      "mixed"        — Combine all available real parcels + synthetic fill-up to count
    """
    if source == "postgis":
        return load_parcels_from_postgis(
            database_url=database_url or "",
            limit=count,
            min_area_sqft=min_area_sqft,
            county=county,
        )

    if source == "local_cache":
        return load_parcels_from_local_cache(min_area_sqft=min_area_sqft, limit=count)

    if source == "synthetic":
        return generate_synthetic_parcels(count=count, seed=synthetic_seed)

    if source == "mixed":
        real: List[ParcelSample] = []
        if database_url:
            try:
                real = load_parcels_from_postgis(database_url, limit=count, min_area_sqft=min_area_sqft, county=county)
            except Exception:
                pass
        if len(real) < count and LOCAL_CACHE_PATH.exists():
            cached = load_parcels_from_local_cache(min_area_sqft=min_area_sqft, limit=count)
            ids_seen = {p.parcel_id for p in real}
            real += [p for p in cached if p.parcel_id not in ids_seen]
        shortfall = count - len(real)
        if shortfall > 0:
            synthetic = generate_synthetic_parcels(count=shortfall, seed=synthetic_seed)
            real += synthetic
        return real[:count]

    # "auto"
    if database_url:
        try:
            parcels = load_parcels_from_postgis(database_url, limit=count, min_area_sqft=min_area_sqft, county=county)
            if parcels:
                return parcels
        except Exception:
            pass
    if LOCAL_CACHE_PATH.exists():
        parcels = load_parcels_from_local_cache(min_area_sqft=min_area_sqft, limit=count)
        if parcels:
            return parcels
    return generate_synthetic_parcels(count=count, seed=synthetic_seed)
