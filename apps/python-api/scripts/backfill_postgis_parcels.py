from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.arcgis_parcel_client import ArcGISParcelClient
from services.persistence import PersistenceLayer


async def main() -> None:
    persistence = PersistenceLayer()
    if not persistence.database_enabled:
        raise SystemExit("DATABASE_URL is required to backfill PostGIS parcels.")

    source_client = ArcGISParcelClient()
    parcels = persistence.list_local_parcels()
    if not parcels:
        raise SystemExit("No local cached parcels found in apps/python-api/data/parcels.json.")

    print(f"Backfilling {len(parcels)} cached parcels into PostGIS...")
    for index, parcel in enumerate(parcels, start=1):
        await persistence.save_parcel(parcel, source=source_client.parcel_source(parcel.county))
        if index % 50 == 0 or index == len(parcels):
            print(f"  saved {index}/{len(parcels)}")

    print("PostGIS parcel backfill complete.")


if __name__ == "__main__":
    asyncio.run(main())
