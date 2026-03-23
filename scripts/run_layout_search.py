from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.layout_models import ParcelInput, ZoningInput
from services.layout_service import search_layout


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python scripts/run_layout_search.py parcel.json zoning.json")
        return 1

    parcel_data = json.loads(Path(sys.argv[1]).read_text())
    zoning_data = json.loads(Path(sys.argv[2]).read_text())

    parcel = ParcelInput.model_validate(parcel_data)
    zoning = ZoningInput.model_validate(zoning_data)
    result = search_layout(parcel, zoning)

    print(f"layout_id: {result.layout_id}")
    print(f"units: {result.units}")
    print(f"road_length: {result.road_length:.2f}")
    print(f"score: {result.score:.4f}")
    print(f"road_geometries: {len(result.road_geometries)}")
    print(f"lot_geometries: {len(result.lot_geometries)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
