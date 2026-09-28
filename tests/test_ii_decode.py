"""Manual-derived II fixtures. These are synthetic, not captured responses."""

import json
import ast
import re
import unittest
from pathlib import Path

from musashi_ingestion.devices.ii import IIProtocolError, checksum
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
        """Run the retained parser method without importing its missing DB dependency."""
        fixture = json.loads((Path(__file__).parent / "fixtures" / "ii_uploads.json").read_text())
        d01 = next(item for item in fixture["uploads"] if item["code"] == "D01")
        decoded = parse_upload(d01["code"], d01["payload"])

        example_path = Path(__file__).parents[1] / "examples" / "musashi_II_example" / "read_musashi.py"
        tree = ast.parse(example_path.read_text())
        regex_assignment = next(
            node for node in tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "DA01_REGEX" for target in node.targets)
        )
        dispenser = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "MusashiDispenser"
        )
        parser = next(
            node for node in dispenser.body
            if isinstance(node, ast.FunctionDef) and node.name == "parse_da01_parameters"
        )
        isolated_class = ast.ClassDef(name="MusashiDispenser", bases=[], keywords=[], body=[parser], decorator_list=[])
        module = ast.fix_missing_locations(ast.Module(body=[regex_assignment, isolated_class], type_ignores=[]))
        namespace = {"re": re}
        exec(compile(module, str(example_path), "exec"), namespace)
        payload = d01["payload"].encode("ascii")
        framed_payload = f"{len(payload):02X}".encode("ascii") + payload
        retained_frame = (framed_payload + checksum(framed_payload)).decode("ascii")
        retained = namespace["MusashiDispenser"]().parse_da01_parameters(retained_frame)

        # Compare every shared semantic field, including parsed units and trimming.
        retained_fields = {
            "pressure_kpa": retained["pressure_kpa"],
            "dispense_time_ms": retained["time_ms"],
            "vacuum_kpa_magnitude": retained["vacuum_kpa"],
            "mode_code": retained["mode_code"],
            "product_name": retained["product_name"],
        }
        self.assertEqual(retained_fields, decoded)

    def test_unavailable_shape_is_not_invented(self):
        with self.assertRaises(IIProtocolError):
            parse_upload("D06", "DA06CH000")
        with self.assertRaises(IIProtocolError):
            parse_upload("D01", "DA01PUNKNOWN")


if __name__ == "__main__":
    unittest.main()
