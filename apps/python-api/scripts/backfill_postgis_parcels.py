from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.arcgis_parcel_client import ArcGISParcelClient
from services.persistence import PersistenceLayer


DEFAULT_BATCH_SIZE = 1000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill parcel geometries into PostGIS.")
    parser.add_argument(
        "--county",
        action="append",
        dest="counties",
        help="County name to ingest from UGRC. Repeat for multiple counties.",
    )
    parser.add_argument(
        "--from-cache",
        action="store_true",
        help="Seed PostGIS from apps/python-api/data/parcels.json instead of UGRC.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="Rows per insert batch.",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    persistence = PersistenceLayer()
    if not persistence.database_enabled:
        raise SystemExit("DATABASE_URL is required to backfill PostGIS parcels.")

    source_client = ArcGISParcelClient(timeout=60.0, allow_fallback=False)
    batch_size = max(1, args.batch_size)

    if args.from_cache:
        await backfill_from_cache(persistence, source_client, batch_size)
        return

    counties = args.counties or []
    if not counties:
        raise SystemExit("Pass --county <name> to ingest from UGRC, or --from-cache to seed from local cache.")

    for county in counties:
        await backfill_county(persistence, source_client, county, batch_size)


async def backfill_from_cache(
    persistence: PersistenceLayer,
    source_client: ArcGISParcelClient,
    batch_size: int,
) -> None:
    parcels = persistence.list_local_parcels()
    if not parcels:
        raise SystemExit("No local cached parcels found in apps/python-api/data/parcels.json.")

    print(f"Backfilling {len(parcels)} cached parcels into PostGIS...")
    started_at = perf_counter()
    inserted = 0
    for batch_index, start in enumerate(range(0, len(parcels), batch_size), start=1):
        batch = parcels[start : start + batch_size]
        source = source_client.parcel_source(batch[0].county) if batch else None
        await persistence.save_parcel_batch(batch, source=source, update_json=False)
        inserted += len(batch)
        print(f"Inserted batch {batch_index} ({len(batch)} rows)")
    report_rate(inserted, started_at)


async def backfill_county(
    persistence: PersistenceLayer,
    source_client: ArcGISParcelClient,
    county: str,
    batch_size: int,
) -> None:
    total_remote = await source_client.count_county_records(county)
    print(f"Starting county ingest for {county} ({total_remote} upstream parcels)...")
    started_at = perf_counter()
    inserted = 0
    batch_index = 0
    async for batch in source_client.stream_county_records(county, batch_size=batch_size):
        batch_index += 1
        await persistence.save_parcel_batch(batch, source=source_client.parcel_source(county), update_json=False)
        inserted += len(batch)
        print(f"Inserted batch {batch_index} ({len(batch)} rows)")
    report_rate(inserted, started_at)


def report_rate(inserted: int, started_at: float) -> None:
    elapsed = max(perf_counter() - started_at, 0.001)
    rows_per_minute = round(inserted / elapsed * 60, 2)
    print(f"PostGIS parcel backfill complete: {inserted} rows in {elapsed:.2f}s ({rows_per_minute} rows/min)")


if __name__ == "__main__":
    asyncio.run(main())
