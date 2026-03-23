from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.layout_models import LayoutResult, ParcelInput, ZoningInput
from services.layout_service import search_layout


class LayoutServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.parcel = ParcelInput(
            parcel_id="test-parcel",
            geometry={
                "type": "Polygon",
                "coordinates": [[
                    [0.0, 0.0],
                    [0.0, 660.0],
                    [660.0, 660.0],
                    [660.0, 0.0],
                    [0.0, 0.0],
                ]],
            },
            area_sqft=660.0 * 660.0,
        )
        self.zoning = ZoningInput(
            district="R-1",
            min_lot_size_sqft=6000.0,
            max_units_per_acre=5.0,
            setbacks={"front": 25.0, "side": 8.0, "rear": 20.0},
        )

    def test_models_load(self) -> None:
        self.assertEqual(self.parcel.parcel_id, "test-parcel")
        self.assertEqual(self.zoning.district, "R-1")

    def test_service_returns_layout_result(self) -> None:
        result = search_layout(self.parcel, self.zoning, max_candidates=12)
        self.assertIsInstance(result, LayoutResult)

    def test_subdivision_returns_valid_layout(self) -> None:
        result = search_layout(self.parcel, self.zoning, max_candidates=12)
        self.assertGreater(result.units, 0)
        self.assertGreaterEqual(result.road_length, 0.0)
        self.assertTrue(result.lot_geometries)
        self.assertTrue(result.road_geometries)

    def test_output_schema_matches_layout_result(self) -> None:
        result = search_layout(self.parcel, self.zoning, max_candidates=12)
        payload = result.model_dump()
        self.assertIn("layout_id", payload)
        self.assertIn("units", payload)
        self.assertIn("score", payload)
        self.assertIn("metadata", payload)


if __name__ == "__main__":
    unittest.main()
