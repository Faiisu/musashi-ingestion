"""Process-level simulated read, authorization, and restart check."""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ApiTests(unittest.TestCase):
    def test_mock_read_survives_restart_and_anonymous_access_is_denied(self):
        with tempfile.TemporaryDirectory() as directory:
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            env = os.environ.copy()
            env.update(OPERATOR_TOKEN="synthetic-test-token", MUSASHI_PORT=str(port), MUSASHI_DATA_DIR=directory)
            base = f"http://127.0.0.1:{port}"

            def request(path, *, token=False, body=None):
                headers = {"Authorization": "Bearer synthetic-test-token"} if token else {}
                if body is not None:
                    headers["Content-Type"] = "application/json"
                raw = None if body is None else json.dumps(body).encode()
                method = "POST" if body is not None else "GET"
                return urlopen(Request(base + path, data=raw, headers=headers, method=method), timeout=2)

            def start():
                process = subprocess.Popen([sys.executable, "-m", "musashi_ingestion"], env=env,
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                for _ in range(50):
                    try:
                        with request("/health") as response:
                            if json.load(response)["process"] == "ok":
                                return process
                    except (URLError, OSError):
                        time.sleep(0.05)
                process.terminate()
                process.wait(timeout=5)
                self.fail("service did not start")

            process = start()
            try:
                with request("/health") as response:
                    health = json.load(response)
                self.assertFalse(health["acquisition"])
                self.assertFalse(health["fault"])
                with self.assertRaises(HTTPError) as denied:
                    request("/api/config")
                self.assertEqual(denied.exception.code, 401)
                with self.assertRaises(HTTPError) as denied_start:
                    request("/api/control/start", body={})
                self.assertEqual(denied_start.exception.code, 401)
                with request("/api/mock-read", token=True, body={}) as response:
                    record_id = json.load(response)["record_id"]
                with request("/api/records", token=True) as response:
                    self.assertEqual(json.load(response)["records"][0]["record_id"], record_id)
            finally:
                process.terminate()
                process.wait(timeout=5)

            blank = dict(env, OPERATOR_TOKEN="")
            failed = subprocess.run([sys.executable, "-m", "musashi_ingestion"], env=blank,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    timeout=5, check=False)
            self.assertNotEqual(failed.returncode, 0)

            process = start()
            try:
                with request("/api/records", token=True) as response:
                    self.assertEqual(json.load(response)["records"][0]["record_id"], record_id)
            finally:
                process.terminate()
                process.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
