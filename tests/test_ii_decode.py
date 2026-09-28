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
        for entry in fixture["uploads"]:
            with self.subTest(entry["code"]):
                self.assertEqual(parse_upload(entry["code"], entry["payload"]), entry["expected"])

    def test_unavailable_shape_is_not_invented(self):
        with self.assertRaises(IIProtocolError):
            parse_upload("D06", "DA06CH000")
        with self.assertRaises(IIProtocolError):
            parse_upload("D01", "DA01PUNKNOWN")


if __name__ == "__main__":
    unittest.main()
