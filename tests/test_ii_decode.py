"""Manual-derived II fixtures. These are synthetic, not captured responses."""

import json
import unittest
from pathlib import Path

from musashi_ingestion.devices.ii import IIProtocolError
from musashi_ingestion.devices.ii_decode import parse_upload


class IIDecodeTests(unittest.TestCase):
    def test_all_upload_layouts(self):
        fixture = json.loads((Path(__file__).parent / "fixtures" / "ii_uploads.json").read_text())
        self.assertIn("synthetic", fixture["evidence"])
        self.assertEqual([entry["code"] for entry in fixture["uploads"]], [f"D{i:02}" for i in range(1, 10)])
        for entry in fixture["uploads"]:
            with self.subTest(entry["code"]):
                self.assertEqual(parse_upload(entry["code"], entry["payload"]), entry["expected"])

    def test_blank_numeric_fixture_is_unavailable(self):
        fixture = json.loads((Path(__file__).parent / "fixtures" / "ii_uploads.json").read_text())
        case = next(item for item in fixture["faults"] if item["name"] == "blank_numeric")
        self.assertEqual(parse_upload(case["code"], case["payload"]), case["expected"])

    def test_d01_fixture_matches_retained_reader_fields(self):
        """Compare shared fields without importing the example's missing DB dependency."""
        fixture = json.loads((Path(__file__).parent / "fixtures" / "ii_uploads.json").read_text())
        d01 = next(item for item in fixture["uploads"] if item["code"] == "D01")
        decoded = parse_upload(d01["code"], d01["payload"])
        # These correspond to the retained parse_da01_parameters return keys.
        retained_fields = {
            "pressure_kpa": decoded["pressure_kpa"],
            "time_ms": decoded["dispense_time_ms"],
            "vacuum_kpa": decoded["vacuum_kpa_magnitude"],
            "mode_code": decoded["mode_code"],
            "product_name": decoded["product_name"],
        }
        self.assertEqual(retained_fields, {
            "pressure_kpa": 98.7, "time_ms": 654, "vacuum_kpa": 3.21,
            "mode_code": 2, "product_name": "SIGMA",
        })

    def test_unavailable_shape_is_not_invented(self):
        with self.assertRaises(IIProtocolError):
            parse_upload("D06", "DA06CH000")
        with self.assertRaises(IIProtocolError):
            parse_upload("D01", "DA01PUNKNOWN")


if __name__ == "__main__":
    unittest.main()
