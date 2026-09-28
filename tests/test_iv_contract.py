"""Synthetic IV responses and exact safe read boundary."""

import json
import unittest
from pathlib import Path

from musashi_ingestion.devices.iv import IVReadError, IVReader, inventory_requests, path_for, status_requests
from musashi_ingestion.runtime.supervisor import Supervisor


class Response:
    def __init__(self, status, body):
        self.status = status
        self.body = body

    def getheader(self, key):
        return str(len(self.body)) if key == "Content-Length" else None

    def read(self, count):
        return self.body[:count]


class Connection:
    def __init__(self, trace, responses):
        self.trace = trace
        self.responses = responses
        self.path = None

    def request(self, method, path, headers=None):
        self.trace.append((method, path))
        self.path = path

    def getresponse(self):
        if self.path not in self.responses:
            raise TimeoutError("synthetic timeout")
        return self.responses[self.path]

    def close(self):
        pass


class IVContractTests(unittest.TestCase):
    def test_partial_all_and_per_id_fallback_are_distinct(self):
        fixture = json.loads((Path(__file__).parent / "fixtures" / "iv_responses.json").read_text())
        self.assertIn("synthetic", fixture["evidence"])
        responses = {path: Response(200, (entry["body"] if entry["kind"] == "tsv"
                                           else json.dumps(entry["body"]).encode()))
                     for path, entry in fixture["responses"].items()}
        trace = []
        reader = IVReader("127.0.0.1", connection_factory=lambda host, port, timeout: Connection(trace, responses))
        machine = {"recipe_count": 2, "channel_count": 2}
        for kind, item_id, option in (("recipe_all", None, None), ("recipe_range", None, None),
                                      ("recipe_item", 2, None), ("channel_all", None, None),
                                      ("channel_range", None, None), ("channel_item", 2, None)):
            result = reader.read(kind, item_id=item_id, option=option)
            Supervisor._validate_iv_inventory(machine, (kind, item_id, option), result.value)
        self.assertEqual(trace[2], ("GET", "/v1/info/recipe/data/2"))
        self.assertEqual(len(trace), 6)

    def test_manifest_covers_the_complete_catalog_and_typed_templates(self):
        fixture = json.loads((Path(__file__).parent / "fixtures" / "iv_responses.json").read_text())
        catalog = fixture["catalog"]
        expected = set(catalog["status_paths"] + catalog["machine_time_paths"]
                       + catalog["common_paths"] + catalog["inventory_paths"]
                       + catalog["export_paths"] + catalog["diagnosis_result_paths"])
        for typed in catalog["typed_id_templates"].values():
            expected.update(typed["fixtures"])
        self.assertEqual(expected, set(fixture["responses"]))
        self.assertEqual(len(catalog["status_paths"]), 16)
        self.assertEqual(len(catalog["common_paths"]), 12)
        self.assertEqual(len(catalog["inventory_paths"]), 4)
        self.assertEqual(len(catalog["diagnosis_result_paths"]), 3)
        self.assertEqual(catalog["typed_id_templates"]["recipe"]["range"], "1–100")
        self.assertEqual(catalog["typed_id_templates"]["channel"]["range"], "1–400")
        generated = {path_for(kind, item_id=item_id, option=option)
                     for kind, item_id, option in list(status_requests()) + list(inventory_requests())}
        generated.update(path_for("recipe_item", item_id=value) for value in (1, 2, 100))
        generated.update(path_for("channel_item", item_id=value) for value in (1, 2, 400))
        self.assertEqual(expected, generated)

        requests = list(status_requests()) + list(inventory_requests())
        requests += [("recipe_item", value, None) for value in (1, 2, 100)]
        requests += [("channel_item", value, None) for value in (1, 2, 400)]
        for option in ("interval", "correction", "rs232c", "ethernet", "dsubio", "configure"):
            requests.extend((kind, None, option) for kind in ("common_data", "common_range"))
        encoded = {path: Response(200, entry["body"].encode() if entry["kind"] == "tsv"
                                  else json.dumps(entry["body"]).encode())
                   for path, entry in fixture["responses"].items()}
        trace = []
        reader = IVReader("127.0.0.1", connection_factory=lambda host, port, timeout: Connection(trace, encoded))
        for kind, item_id, option in requests:
            result = reader.read(kind, item_id=item_id, option=option)
            entry = fixture["responses"][result.path]
            self.assertEqual(result.value, entry["body"], result.path)
        self.assertEqual(len(trace), len(requests))

    def test_failure_fixtures_reject_once_without_followup_or_forbidden_request(self):
        fixture = json.loads((Path(__file__).parent / "fixtures" / "iv_responses.json").read_text())
        cases = fixture["fault_cases"]
        for name in ("forbidden-control-get", "screen", "post", "out-of-range-id", "user-supplied-path"):
            case = cases[name]
            trace = []
            reader = IVReader("127.0.0.1", connection_factory=lambda host, port, timeout: Connection(trace, {}))
            request = case.get("request")
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, case["expected_error"]):
                if name == "post":
                    reader.read(case["path"])
                else:
                    reader.read(request[0], item_id=request[1], option=request[2])
            self.assertEqual(len(trace), case["followup_requests"])
            self.assertEqual(trace, [])
            self.assertFalse(any(path.encode() in b" ".join(p.encode() for _, p in trace)
                                 for path in case.get("forbidden_path_bytes", [])))

        for name, kind, option, status, body, expected_error in (
                ("timeout", "status", "alarm", 200, b"", "transport failed"),
                ("redirect", "time", None, 302, b"", "HTTP 302"),
                ("malformed-json", "status", "main", 200, b"{not-json", "invalid JSON response"),
                ("oversized-json", "export_data", None, 200, b"x" * 33, "response exceeds byte limit"),
                ("oversized-tsv", "export_log", None, 200, b"x" * 33, "response exceeds byte limit")):
            trace = []
            fake_responses = {} if name == "timeout" else {
                path_for(kind, option=option): Response(status, body)}
            reader = IVReader("127.0.0.1", max_bytes=32,
                              connection_factory=lambda host, port, timeout: Connection(trace, fake_responses))
            with self.subTest(name=name), self.assertRaisesRegex(IVReadError, expected_error):
                reader.read(kind, option=option)
            self.assertEqual(len(trace), 1)
            self.assertEqual(trace[0][0], "GET")
            self.assertNotIn("/v1/current/", " ".join(path for _, path in trace))
            self.assertNotIn("/v1/screen", " ".join(path for _, path in trace))

        machine = {"recipe_count": 2, "channel_count": 2}
        for name, request, response, expected_error in (
                ("missing-id", ("channel_all", None, None), {"ch": [{"disPress": 35.5}]}, "invalid channel item shape"),
                ("malformed-range", ("recipe_range", None, None), {"min": 0, "max": 99}, "recipe range conflicts with configured count")):
            kind, item_id, option = request
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, expected_error):
                Supervisor._validate_iv_inventory(machine, request, response)

    def test_null_malformed_oversize_redirect_and_timeout(self):
        responses = {
            "/v1/status/error": Response(200, b"null"),
            "/v1/status/main": Response(200, b"{not-json"),
            "/v1/export/data": Response(200, b"x" * 100),
            "/v1/time": Response(302, b""),
        }
        trace = []
        reader = IVReader("127.0.0.1", max_bytes=32,
                          connection_factory=lambda host, port, timeout: Connection(trace, responses))
        self.assertIsNone(reader.read("status", option="error").value)
        for kind, option in (("status", "main"), ("export_data", None), ("time", None)):
            with self.subTest(kind):
                with self.assertRaises(IVReadError):
                    reader.read(kind, option=option)
        with self.assertRaises(IVReadError):
            reader.read("status", option="alarm")

    def test_full_generated_catalog_contains_no_control_path(self):
        requests = list(status_requests()) + list(inventory_requests())
        requests += [("recipe_item", 1, None), ("recipe_item", 100, None),
                     ("channel_item", 1, None), ("channel_item", 400, None)]
        paths = [path_for(kind, item_id=item_id, option=option) for kind, item_id, option in requests]
        self.assertEqual(len(paths), len(set(paths)))
        self.assertTrue(all(path.startswith("/v1/") and "/screen" not in path
                            and "/current/" not in path and "/clear/" not in path
                            and "/calibrate/" not in path for path in paths))
        for kind, item_id, option in (("screen", None, None), ("channel_item", 401, None),
                                      ("recipe_item", 0, None), ("status", None, "current/dispense")):
            with self.assertRaises(ValueError):
                path_for(kind, item_id=item_id, option=option)


if __name__ == "__main__":
    unittest.main()
