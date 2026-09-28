"""Session login, authorization, CSRF, restart, and expiry checks."""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from http.cookies import SimpleCookie
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from musashi_ingestion.api.auth import ABSOLUTE_SECONDS, IDLE_SECONDS, SessionStore
from musashi_ingestion.api.server import validate_allowed_origin, validate_public_origin


class ApiTests(unittest.TestCase):
    def test_auth_route_table_and_restart_invalidation(self):
        with tempfile.TemporaryDirectory() as directory:
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            env = os.environ.copy()
            env["OPERATOR_TOKEN"] = "legacy-token-must-not-work"
            env.update(OPERATOR_USERNAME="console", OPERATOR_PASSWORD="synthetic password",
                       MUSASHI_PORT=str(port), MUSASHI_DATA_DIR=directory)
            base = f"http://127.0.0.1:{port}"
            origin = base

            def request(path, *, method="GET", body=None, cookie=None, csrf=None, req_origin=None,
                        host=None, bearer=False):
                headers = {}
                if body is not None:
                    headers["Content-Type"] = "application/json"
                if cookie:
                    headers["Cookie"] = cookie
                if csrf:
                    headers["X-CSRF-Token"] = csrf
                if req_origin is not None:
                    headers["Origin"] = req_origin
                if host is not None:
                    headers["Host"] = host
                if bearer:
                    headers["Authorization"] = "Bearer synthetic-test-token"
                raw = None if body is None else json.dumps(body).encode()
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
                security_headers = {
                    "Cache-Control": "no-store",
                    "X-Content-Type-Options": "nosniff",
                    "X-Frame-Options": "DENY",
                    "Referrer-Policy": "no-referrer",
                    "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
                }
                with request("/health") as response:
                    for name, value in security_headers.items():
                        self.assertEqual(response.headers[name], value)
                    health = json.load(response)
                self.assertFalse(health["acquisition"])
                self.assertFalse(health["fault"])

                with request("/") as response:
                    for name, value in security_headers.items():
                        self.assertEqual(response.headers[name], value)

                with request("/api/auth/session") as response:
                    self.assertEqual(json.load(response), {"authenticated": False})
                with self.assertRaises(HTTPError) as unknown_session_host:
                    request("/api/auth/session", host="unconfigured.example")
                self.assertEqual(unknown_session_host.exception.code, 403)
                unknown_session_host.exception.close()
                with self.assertRaises(HTTPError) as denied:
                    request("/api/config")
                self.assertEqual(denied.exception.code, 401)
                denied.exception.close()
                with self.assertRaises(HTTPError) as old_bearer:
                    request("/api/config", bearer=True)
                self.assertEqual(old_bearer.exception.code, 401)
                old_bearer.exception.close()

                with self.assertRaises(HTTPError) as bad_origin:
                    request("/api/auth/login", method="POST", body={"username": "console", "password": "synthetic password"},
                            req_origin="https://attacker.example")
                self.assertEqual(bad_origin.exception.code, 403)
                bad_origin.exception.close()
                with self.assertRaises(HTTPError) as bad_credentials:
                    request("/api/auth/login", method="POST", body={"username": "console", "password": "wrong"},
                            req_origin=origin)
                self.assertEqual(bad_credentials.exception.code, 401)
                self.assertEqual(json.load(bad_credentials.exception), {"error": "invalid credentials"})
                bad_credentials.exception.close()

                with request("/api/auth/login", method="POST",
                             body={"username": "console", "password": "synthetic password"},
                             req_origin=origin) as response:
                    login = json.load(response)
                    self.assertEqual(response.headers["Cache-Control"], "no-store")
                    cookie = SimpleCookie()
                    cookie.load(response.headers["Set-Cookie"])
                    session_cookie = cookie["musashi_session"].value
                    set_cookie = response.headers["Set-Cookie"]
                    self.assertIn("HttpOnly", set_cookie)
                    self.assertIn("SameSite=Strict", set_cookie)
                    self.assertIn("Path=/", set_cookie)
                    self.assertNotIn("Secure", set_cookie)
                    self.assertNotIn(session_cookie, json.dumps(login))
                    self.assertNotIn("synthetic password", json.dumps(login))
                self.assertTrue(login["authenticated"])

                with request("/api/auth/session", cookie=f"musashi_session={session_cookie}") as response:
                    restored = json.load(response)
                self.assertEqual(restored, login)
                with self.assertRaises(HTTPError) as unknown_api_host:
                    request("/api/config", cookie=f"musashi_session={session_cookie}", host="unconfigured.example")
                self.assertEqual(unknown_api_host.exception.code, 403)
                unknown_api_host.exception.close()
                with request("/api/config", cookie=f"musashi_session={session_cookie}") as response:
                    self.assertEqual(response.status, 200)

                with self.assertRaises(HTTPError) as no_origin:
                    request("/api/mock-read", method="POST", body={}, cookie=f"musashi_session={session_cookie}",
                            csrf=login["csrf_token"])
                self.assertEqual(no_origin.exception.code, 403)
                no_origin.exception.close()
                with self.assertRaises(HTTPError) as no_csrf:
                    request("/api/mock-read", method="POST", body={}, cookie=f"musashi_session={session_cookie}",
                            req_origin=origin)
                self.assertEqual(no_csrf.exception.code, 403)
                no_csrf.exception.close()
                with request("/api/mock-read", method="POST", body={}, cookie=f"musashi_session={session_cookie}",
                             csrf=login["csrf_token"], req_origin=origin) as response:
                    record_id = json.load(response)["record_id"]
                with request("/api/records", cookie=f"musashi_session={session_cookie}") as response:
                    self.assertEqual(json.load(response)["records"][0]["record_id"], record_id)

                with self.assertRaises(HTTPError) as no_delete_csrf:
                    request("/api/spool", method="DELETE", cookie=f"musashi_session={session_cookie}",
                            req_origin=origin)
                self.assertEqual(no_delete_csrf.exception.code, 403)
                no_delete_csrf.exception.close()
                with request("/api/spool", method="DELETE", cookie=f"musashi_session={session_cookie}",
                             csrf=login["csrf_token"], req_origin=origin) as response:
                    cleared = json.load(response)
                    self.assertEqual(response.status, 200)
                self.assertEqual(cleared["records"], 1)
                self.assertEqual(cleared["pending_deliveries"], 0)
                with request("/api/records", cookie=f"musashi_session={session_cookie}") as response:
                    self.assertEqual(json.load(response)["records"], [])

                with request("/api/auth/logout", method="POST", cookie=f"musashi_session={session_cookie}",
                             csrf=login["csrf_token"], req_origin=origin) as response:
                    self.assertEqual(response.status, 204)
                    self.assertIn("Max-Age=0", response.headers["Set-Cookie"])
                with self.assertRaises(HTTPError) as logged_out:
                    request("/api/config", cookie=f"musashi_session={session_cookie}")
                self.assertEqual(logged_out.exception.code, 401)
                logged_out.exception.close()

                with request("/api/auth/login", method="POST",
                             body={"username": "console", "password": "synthetic password"},
                             req_origin=origin) as response:
                    cookie = SimpleCookie()
                    cookie.load(response.headers["Set-Cookie"])
                    session_cookie = cookie["musashi_session"].value
                process.terminate()
                process.wait(timeout=5)
                process = start()
                with self.assertRaises(HTTPError) as restarted:
                    request("/api/config", cookie=f"musashi_session={session_cookie}")
                self.assertEqual(restarted.exception.code, 401)
                restarted.exception.close()
            finally:
                process.terminate()
                process.wait(timeout=5)

    def test_explicit_blank_credentials_fail_startup(self):
        for blank in ("OPERATOR_USERNAME", "OPERATOR_PASSWORD"):
            with self.subTest(blank=blank), tempfile.TemporaryDirectory() as directory:
                env = os.environ.copy()
                env.update(OPERATOR_USERNAME="user", OPERATOR_PASSWORD="secret", MUSASHI_DATA_DIR=directory)
                env[blank] = ""
                result = subprocess.run([sys.executable, "-m", "musashi_ingestion"], env=env,
                                        capture_output=True, text=True, timeout=5, check=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("OPERATOR_USERNAME and OPERATOR_PASSWORD must be nonempty", result.stderr)
                self.assertNotIn("secret", result.stderr)

    def test_defaults_and_legacy_bearer_are_not_an_auth_method(self):
        with tempfile.TemporaryDirectory() as directory:
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            env = os.environ.copy()
            env.pop("OPERATOR_USERNAME", None)
            env.pop("OPERATOR_PASSWORD", None)
            env["OPERATOR_TOKEN"] = "old-secret"
            env.update(MUSASHI_PORT=str(port), MUSASHI_DATA_DIR=directory)
            process = subprocess.Popen([sys.executable, "-m", "musashi_ingestion"], env=env,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            base = f"http://127.0.0.1:{port}"
            try:
                for _ in range(50):
                    try:
                        with urlopen(base + "/health", timeout=2):
                            break
                    except (URLError, OSError):
                        time.sleep(0.05)
                with self.assertRaises(HTTPError) as legacy:
                    urlopen(Request(base + "/api/config", headers={"Authorization": "Bearer old-secret"}), timeout=2)
                self.assertEqual(legacy.exception.code, 401)
                legacy.exception.close()
                request = Request(base + "/api/auth/login", data=json.dumps(
                    {"username": "admin", "password": "00000000"}).encode(),
                    headers={"Origin": base, "Content-Type": "application/json"}, method="POST")
                with urlopen(request, timeout=2) as response:
                    self.assertEqual(response.status, 200)
            finally:
                process.terminate()
                process.wait(timeout=5)

    def test_trusted_https_origin_sets_secure_cookie_and_rejects_backend_origin(self):
        with tempfile.TemporaryDirectory() as directory:
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            env = os.environ.copy()
            env.update(OPERATOR_USERNAME="admin", OPERATOR_PASSWORD="secret",
                       MUSASHI_PUBLIC_ORIGIN="https://console.example:8443",
                       MUSASHI_PORT=str(port), MUSASHI_DATA_DIR=directory)
            process = subprocess.Popen([sys.executable, "-m", "musashi_ingestion"], env=env,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            base = f"http://127.0.0.1:{port}"
            try:
                for _ in range(50):
                    try:
                        with urlopen(base + "/health", timeout=2):
                            break
                    except (URLError, OSError):
                        time.sleep(0.05)
                direct = Request(base + "/api/auth/login", data=json.dumps(
                    {"username": "admin", "password": "secret"}).encode(),
                    headers={"Origin": base, "Content-Type": "application/json"}, method="POST")
                with self.assertRaises(HTTPError) as denied:
                    urlopen(direct, timeout=2)
                self.assertEqual(denied.exception.code, 403)
                denied.exception.close()

                proxied = Request(base + "/api/auth/login", data=json.dumps(
                    {"username": "admin", "password": "secret"}).encode(),
                    headers={"Host": "console.example:8443", "Origin": "https://console.example:8443",
                             "Content-Type": "application/json"}, method="POST")
                with urlopen(proxied, timeout=2) as response:
                    self.assertIn("Secure", response.headers["Set-Cookie"])
            finally:
                process.terminate()
                process.wait(timeout=5)

    def test_explicit_private_lan_origin_and_https_origin_can_both_login(self):
        with tempfile.TemporaryDirectory() as directory:
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            env = os.environ.copy()
            lan_origin = f"http://192.168.50.10:{port}"
            env.update(OPERATOR_USERNAME="admin", OPERATOR_PASSWORD="secret",
                       MUSASHI_ALLOWED_ORIGINS=f"{lan_origin},https://console.example",
                       MUSASHI_PORT=str(port), MUSASHI_DATA_DIR=directory)
            process = subprocess.Popen([sys.executable, "-m", "musashi_ingestion"], env=env,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            base = f"http://127.0.0.1:{port}"
            try:
                for _ in range(50):
                    try:
                        with urlopen(base + "/health", timeout=2):
                            break
                    except (URLError, OSError):
                        time.sleep(0.05)
                lan_request = Request(base + "/api/auth/login", data=json.dumps(
                    {"username": "admin", "password": "secret"}).encode(),
                    headers={"Host": f"192.168.50.10:{port}", "Origin": lan_origin,
                             "Content-Type": "application/json"}, method="POST")
                with urlopen(lan_request, timeout=2) as response:
                    self.assertNotIn("Secure", response.headers["Set-Cookie"])
                    cookie = SimpleCookie()
                    cookie.load(response.headers["Set-Cookie"])
                    session_id = cookie["musashi_session"].value
                    self.assertTrue(json.load(response)["authenticated"])
                read = Request(base + "/api/config", headers={
                    "Host": f"192.168.50.10:{port}", "Cookie": f"musashi_session={session_id}"})
                with urlopen(read, timeout=2) as response:
                    self.assertEqual(response.status, 200)

                https_request = Request(base + "/api/auth/login", data=json.dumps(
                    {"username": "admin", "password": "secret"}).encode(),
                    headers={"Host": "console.example", "Origin": "https://console.example",
                             "Content-Type": "application/json"}, method="POST")
                with urlopen(https_request, timeout=2) as response:
                    self.assertIn("Secure", response.headers["Set-Cookie"])

                denied = Request(base + "/api/auth/login", data=json.dumps(
                    {"username": "admin", "password": "secret"}).encode(),
                    headers={"Host": f"192.168.50.10:{port}", "Origin": f"http://192.168.50.11:{port}",
                             "Content-Type": "application/json"}, method="POST")
                with self.assertRaises(HTTPError) as mismatch:
                    urlopen(denied, timeout=2)
                self.assertEqual(mismatch.exception.code, 403)
                mismatch.exception.close()
            finally:
                process.terminate()
                process.wait(timeout=5)

    def test_wildcard_origins_allow_any_matching_host_and_keep_https_cookie_secure(self):
        with tempfile.TemporaryDirectory() as directory:
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            env = os.environ.copy()
            env.update(OPERATOR_USERNAME="admin", OPERATOR_PASSWORD="secret",
                       MUSASHI_ALLOWED_ORIGINS="*", MUSASHI_PORT=str(port), MUSASHI_DATA_DIR=directory)
            process = subprocess.Popen([sys.executable, "-m", "musashi_ingestion"], env=env,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            base = f"http://127.0.0.1:{port}"
            try:
                for _ in range(50):
                    try:
                        with urlopen(base + "/health", timeout=2):
                            break
                    except (URLError, OSError):
                        time.sleep(0.05)
                host = f"console.anywhere.example:{port}"
                origin = f"http://{host}"
                login_request = Request(base + "/api/auth/login", data=json.dumps(
                    {"username": "admin", "password": "secret"}).encode(),
                    headers={"Host": host, "Origin": origin, "Content-Type": "application/json"}, method="POST")
                with urlopen(login_request, timeout=2) as response:
                    self.assertEqual(response.status, 200)
                    self.assertNotIn("Secure", response.headers["Set-Cookie"])

                secure_host = "console.anywhere.example"
                secure_request = Request(base + "/api/auth/login", data=json.dumps(
                    {"username": "admin", "password": "secret"}).encode(),
                    headers={"Host": secure_host, "Origin": f"https://{secure_host}",
                             "Content-Type": "application/json"}, method="POST")
                with urlopen(secure_request, timeout=2) as response:
                    self.assertIn("Secure", response.headers["Set-Cookie"])

                mismatch = Request(base + "/api/auth/login", data=json.dumps(
                    {"username": "admin", "password": "secret"}).encode(),
                    headers={"Host": host, "Origin": "http://other.example", "Content-Type": "application/json"},
                    method="POST")
                with self.assertRaises(HTTPError) as denied:
                    urlopen(mismatch, timeout=2)
                self.assertEqual(denied.exception.code, 403)
                denied.exception.close()
            finally:
                process.terminate()
                process.wait(timeout=5)

    def test_expiry_uses_idle_and_absolute_limits(self):
        now = [1000.0]
        store = SessionStore("admin", "password", clock=lambda: now[0])
        session = store.create()
        now[0] += IDLE_SECONDS - 1
        self.assertIsNotNone(store.get(session.session_id))
        now[0] += IDLE_SECONDS
        self.assertIsNone(store.get(session.session_id))

        now[0] = 1000.0
        session = store.create()
        for _ in range(3):
            now[0] += 7 * 60 * 60
            self.assertIsNotNone(store.get(session.session_id))
        now[0] += 3 * 60 * 60 - 1
        self.assertIsNotNone(store.get(session.session_id))
        now[0] += 1
        self.assertIsNone(store.get(session.session_id))

    def test_public_origin_validation(self):
        self.assertIsNone(validate_public_origin(None))
        self.assertEqual(validate_public_origin("https://console.example:8443"), "https://console.example:8443")
        for invalid in ("http://console.example", "https://user@console.example", "https://console.example/",
                        "https://console.example/path", "https://console.example?x=1", "https://console.example#x"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_public_origin(invalid)

    def test_allowed_origin_validation_requires_exact_origin_and_restricted_http_host(self):
        self.assertEqual(validate_allowed_origin("*"), "*")
        self.assertEqual(validate_allowed_origin("http://127.0.0.1:8080"), "http://127.0.0.1:8080")
        self.assertEqual(validate_allowed_origin("http://192.168.50.10:8080"), "http://192.168.50.10:8080")
        self.assertEqual(validate_allowed_origin("http://100.85.124.109:8080"), "http://100.85.124.109:8080")
        self.assertEqual(validate_allowed_origin("https://console.example"), "https://console.example")
        for invalid in ("https://console.example/path", "http://console.example", "http://8.8.8.8:8080",
                        "https://user@console.example", "https://console.example/"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_allowed_origin(invalid)


if __name__ == "__main__":
    unittest.main()
