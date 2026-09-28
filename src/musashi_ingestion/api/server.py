"""Small loopback-first HTTP management surface."""

from __future__ import annotations

import hmac
import json
import mimetypes
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from musashi_ingestion.config.store import ConfigError, RevisionConflict
from musashi_ingestion.pipeline.spool import SpoolError, make_record


def serve(bind, port, token, config_store, spool, supervisor):
    if not token:
        raise ValueError("OPERATOR_TOKEN must be nonempty")
    operation_lock = threading.RLock()
    web_root = Path(__file__).resolve().parent.parent / "web"

    class Handler(BaseHTTPRequestHandler):
        server_version = "MusashiManagement/1"

        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def log_message(self, format, *args):
            # Request paths and headers can contain operational details; avoid access logs.
            pass

        def _send(self, status, body):
            data = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
            self.end_headers()
            self.wfile.write(data)

        def _static(self):
            route = urlsplit(self.path).path
            relative = "index.html" if route == "/" else route.removeprefix("/ui/")
            if route != "/" and not route.startswith("/ui/"):
                return False
            candidate = (web_root / relative).resolve()
            if web_root not in candidate.parents and candidate != web_root:
                self.send_error(404)
                return True
            if not candidate.is_file():
                self.send_error(404)
                return True
            data = candidate.read_bytes()
            content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", content_type + ("; charset=utf-8" if content_type.startswith("text/") or content_type in ("application/javascript", "application/json") else ""))
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
            self.end_headers()
            self.wfile.write(data)
            return True

        def _authorized(self):
            supplied = self.headers.get("Authorization", "")
            return supplied.startswith("Bearer ") and hmac.compare_digest(supplied[7:], token)

        def _body(self):
            raw_size = self.headers.get("Content-Length", "")
            if not raw_size.isdigit() or int(raw_size) > 1_048_576:
                raise ValueError("body length must be at most 1048576 bytes")
            data = self.rfile.read(int(raw_size))
            if len(data) != int(raw_size):
                raise ValueError("incomplete body")
            value = json.loads(data)
            if not isinstance(value, dict):
                raise ValueError("body must be a JSON object")
            return value

        def do_GET(self):
            if self.path == "/" or self.path.startswith("/ui/"):
                self._static()
                return
            if self.path == "/health":
                self._send(200, {"process": "ok", "acquisition": supervisor.status()["running"],
                                 "fault": bool(supervisor.status()["acquisition_fault"])})
                return
            if not self._authorized():
                self._send(401, {"error": "unauthorized"})
                return
            if self.path == "/api/config":
                self._send(200, config_store.load())
            elif self.path == "/api/status":
                self._send(200, supervisor.status())
            elif self.path == "/api/records":
                self._send(200, {"records": spool.list_records(limit=10)})
            elif self.path == "/api/scans":
                self._send(200, {"scans": spool.list_scans(limit=10)})
            else:
                self._send(404, {"error": "not found"})

        def do_PUT(self):
            if not self._authorized():
                self._send(401, {"error": "unauthorized"})
                return
            if self.path != "/api/config":
                self._send(404, {"error": "not found"})
                return
            try:
                body = self._body()
                expected = body.pop("revision", None)
                if type(expected) is not int:
                    raise ValueError("revision must be an integer")
                with operation_lock:
                    state = supervisor.status()
                    if any(item["worker_alive"] for item in (*state["machines"].values(), *state["destinations"].values())):
                        self._send(409, {"error": "stop acquisition before changing configuration"})
                        return
                    result = config_store.save(expected, body)
                    self._send(200, result)
            except ConfigError as exc:
                self._send(422, {"errors": exc.errors})
            except RevisionConflict:
                self._send(409, {"error": "stale revision"})
            except (ValueError, json.JSONDecodeError) as exc:
                self._send(400, {"error": str(exc)})

        def do_POST(self):
            if not self._authorized():
                self._send(401, {"error": "unauthorized"})
                return
            try:
                if self.path == "/api/control/start":
                    with operation_lock:
                        self._send(200, supervisor.start())
                elif self.path == "/api/control/stop":
                    with operation_lock:
                        self._send(200, supervisor.stop())
                elif self.path == "/api/mock-read":
                    body = self._body()
                    machine_id = body.get("machine_id", "mock-ii")
                    if not isinstance(machine_id, str) or not machine_id or len(machine_id) > 64:
                        raise ValueError("invalid machine_id")
                    record = make_record(machine_id, "II", "status", "D01",
                                         {"synthetic": True, "pressure_kpa": 100},
                                         channel_id=1, evidence_type="simulated")
                    spool.commit(record)
                    self._send(201, {"record_id": record["record_id"]})
                else:
                    self._send(404, {"error": "not found"})
            except SpoolError as exc:
                self._send(507, {"error": str(exc)})
            except ConfigError as exc:
                self._send(422, {"errors": exc.errors})
            except (ValueError, json.JSONDecodeError) as exc:
                self._send(400, {"error": str(exc)})

    server = ThreadingHTTPServer((bind, port), Handler)
    try:
        server.serve_forever()
    finally:
        supervisor.stop()
        server.server_close()
