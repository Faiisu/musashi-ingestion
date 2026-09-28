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
        responses = {path: Response(200, json.dumps(value).encode())
                     for path, value in fixture["responses"].items()}
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
