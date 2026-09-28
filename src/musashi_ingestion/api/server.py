"""Small loopback-first HTTP management surface."""

from __future__ import annotations

import ipaddress
import json
import mimetypes
import threading
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from musashi_ingestion.api.auth import COOKIE_NAME, SessionStore
from musashi_ingestion.config.store import ConfigError, RevisionConflict
from musashi_ingestion.pipeline.spool import SpoolError, make_record


def validate_public_origin(value):
    """Validate the exact trusted browser origin used behind a TLS proxy."""
    if value is None:
        return None
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except (TypeError, ValueError):
        raise ValueError("MUSASHI_PUBLIC_ORIGIN must be an HTTPS origin without path, query, or fragment") from None
    if (parsed.scheme != "https" or not parsed.netloc or parsed.username is not None
            or parsed.password is not None or parsed.path or parsed.query or parsed.fragment
            or "@" in parsed.netloc or any(char.isspace() for char in value)
            or parsed.hostname is None or parsed.netloc.endswith(":")
            or (port is not None and not 1 <= port <= 65535)):
        raise ValueError("MUSASHI_PUBLIC_ORIGIN must be an HTTPS origin without path, query, or fragment")
    return value


def validate_allowed_origin(value):
    """Validate an exact browser origin; plain HTTP is limited to private hosts."""
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except (TypeError, ValueError):
        raise ValueError("MUSASHI_ALLOWED_ORIGINS entries must be exact origins") from None
    if (parsed.scheme not in ("http", "https") or not parsed.netloc
            or parsed.username is not None or parsed.password is not None
            or parsed.path or parsed.query or parsed.fragment
            or "@" in parsed.netloc or any(char.isspace() for char in value)
            or parsed.hostname is None or parsed.netloc.endswith(":")
            or (port is not None and not 1 <= port <= 65535)):
        raise ValueError("MUSASHI_ALLOWED_ORIGINS entries must be exact origins")
    if parsed.scheme == "http" and parsed.hostname != "localhost":
        try:
            address = ipaddress.ip_address(parsed.hostname)
        except ValueError:
            raise ValueError("HTTP origins must use localhost or a private IP address") from None
        if not (address.is_private or address.is_loopback):
            raise ValueError("HTTP origins must use localhost or a private IP address")
    return value


def serve(bind, port, username, password, config_store, spool, supervisor, public_origin=None,
          allowed_origins=()):
    sessions = SessionStore(username, password)
    public_origin = validate_public_origin(public_origin)
    expected_origin = public_origin or f"http://127.0.0.1:{port}"
    origins = {validate_allowed_origin(origin) for origin in allowed_origins if origin}
    origins.add(validate_allowed_origin(expected_origin))
    origin_authorities = {origin: urlsplit(origin).netloc for origin in origins}
    allowed_authorities = set(origin_authorities.values())
    operation_lock = threading.RLock()
    web_root = Path(__file__).resolve().parent.parent / "web"

    class Handler(BaseHTTPRequestHandler):
        server_version = "MusashiManagement/1"

        def _send_security_headers(self):
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")

        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def log_message(self, format, *args):
            # Request paths and headers can contain operational details; avoid access logs.
            pass

        def _send(self, status, body=None, headers=()):
            data = b"" if body is None else json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(status)
            if body is not None:
                self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self._send_security_headers()
            for name, value in headers:
                self.send_header(name, value)
            self.end_headers()
            if data:
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
            self._send_security_headers()
            self.end_headers()
            self.wfile.write(data)
            return True

        def _session(self, *, touch=True):
            cookie = SimpleCookie()
            try:
                cookie.load(self.headers.get("Cookie", ""))
            except Exception:
                return None
            morsel = cookie.get(COOKIE_NAME)
            return sessions.get(morsel.value if morsel else None, touch=touch)

        def _host_is_valid(self):
            hosts = self.headers.get_all("Host", [])
            return len(hosts) == 1 and hosts[0] in allowed_authorities

        def _origin_is_valid(self):
            origins = self.headers.get_all("Origin", [])
            if not self._host_is_valid() or len(origins) != 1:
                return False
            origin = origins[0]
            try:
                parsed = urlsplit(origin)
            except ValueError:
                return False
            return (origin in origins and parsed.scheme in ("http", "https")
                    and parsed.netloc == origin_authorities[origin] and self.headers.get("Host") == parsed.netloc and not parsed.path
                    and not parsed.query and not parsed.fragment and parsed.username is None)

        def _cookie_is_secure(self):
            origin = self.headers.get("Origin", "")
            return origin in origins and urlsplit(origin).scheme == "https"

        def _csrf_is_valid(self, session):
            return sessions.csrf_valid(session, self.headers.get("X-CSRF-Token"))

        def _session_cookie(self, session):
            secure = "; Secure" if self._cookie_is_secure() else ""
            return (f"{COOKIE_NAME}={session.session_id}; Path=/; HttpOnly; SameSite=Strict; "
                    f"Max-Age=86400{secure}")

        def _clear_session_cookie(self):
            secure = "; Secure" if self._cookie_is_secure() else ""
            return f"{COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0{secure}"

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
            if self.path == "/api/auth/session":
                if not self._host_is_valid():
                    self._send(403, {"error": "forbidden"})
                    return
                session = self._session()
                if session is None:
                    self._send(200, {"authenticated": False})
                else:
                    self._send(200, {"authenticated": True, "csrf_token": session.csrf_token})
                return
            if self._session() is None:
                self._send(401, {"error": "unauthorized"})
                return
            if not self._host_is_valid():
                self._send(403, {"error": "forbidden"})
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
            session = self._session(touch=False)
            if session is None:
                self._send(401, {"error": "unauthorized"})
                return
            if not self._origin_is_valid() or not self._csrf_is_valid(session):
                self._send(403, {"error": "forbidden"})
                return
            sessions.touch(session)
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
            if self.path == "/api/auth/login":
                if not self._origin_is_valid():
                    self._send(403, {"error": "forbidden"})
                    return
                try:
                    body = self._body()
                except (ValueError, json.JSONDecodeError):
                    self._send(400, {"error": "invalid request"})
                    return
                if not sessions.credentials_valid(body.get("username"), body.get("password")):
                    self._send(401, {"error": "invalid credentials"})
                    return
                session = sessions.create()
                self._send(200, {"authenticated": True, "csrf_token": session.csrf_token},
                           (("Set-Cookie", self._session_cookie(session)),))
                return
            session = self._session(touch=False)
            if session is None:
                self._send(401, {"error": "unauthorized"})
                return
            if not self._origin_is_valid() or not self._csrf_is_valid(session):
                self._send(403, {"error": "forbidden"})
                return
            sessions.touch(session)
            if self.path == "/api/auth/logout":
                sessions.discard(session)
                self._send(204, headers=(("Set-Cookie", self._clear_session_cookie()),))
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
