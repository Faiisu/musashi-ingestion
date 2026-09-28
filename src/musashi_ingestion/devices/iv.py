"""Exact read-only HTTP catalog for Super Sigma CM IV."""
from __future__ import annotations

from dataclasses import dataclass
import http.client
import ipaddress
import json
from threading import Lock

STATUS = ("main", "channel", "recipe", "error", "alarm", "totalCounter",
          "userCounter", "supply", "autoInc", "interval", "stopWatch",
          "tempUnit", "sigma", "remain", "dsubio/in", "dsubio/out")
COMMON = ("interval", "correction", "rs232c", "ethernet", "dsubio", "configure")
DIAGNOSIS = ("dispense", "vacuum", "valve")
STATIC = {
    "machine": "/v1/info/machine/data", "time": "/v1/time",
    "recipe_all": "/v1/info/recipe/data/all", "recipe_range": "/v1/info/recipe/range",
    "channel_all": "/v1/info/channel/data/all", "channel_range": "/v1/info/channel/range",
    "export_data": "/v1/export/data", "export_log": "/v1/export/log",
}


class IVReadError(Exception):
    pass


@dataclass(frozen=True)
class IVResponse:
    path: str
    status: int
    raw: bytes
    value: object


def path_for(kind: str, *, item_id: int | None = None, option: str | None = None) -> str:
    """Construct paths from known variants; callers cannot provide a path or URL."""
    if kind in STATIC and item_id is None and option is None:
        return STATIC[kind]
    if kind == "status" and item_id is None and option in STATUS:
        return "/v1/status/" + option
    if kind in ("common_data", "common_range") and item_id is None and option in COMMON:
        return f"/v1/info/common/{option}/{'data' if kind == 'common_data' else 'range'}"
    if kind == "diagnosis_result" and item_id is None and option in DIAGNOSIS:
        return f"/v1/diagnosis/{option}/result"
    if kind in ("recipe_item", "channel_item") and option is None:
        limit = 100 if kind == "recipe_item" else 400
        if type(item_id) is int and 1 <= item_id <= limit:
            family = "recipe" if kind == "recipe_item" else "channel"
            return f"/v1/info/{family}/data/{item_id}"
    raise ValueError("unsupported IV read request")


def status_requests():
    for option in STATUS:
        yield ("status", None, option)


def inventory_requests(*, include_exports: bool = True):
    """One request per work unit; caller schedules slices around status reads."""
    for kind in ("machine", "time", "recipe_all", "recipe_range", "channel_all", "channel_range"):
        yield (kind, None, None)
    for option in COMMON:
        for kind in ("common_data", "common_range"):
            yield (kind, None, option)
    for option in DIAGNOSIS:
        yield ("diagnosis_result", None, option)
    if include_exports:
        yield ("export_data", None, None)
        yield ("export_log", None, None)


class IVReader:
    def __init__(self, host: str, port: int = 1024, timeout: float = 2.0,
                 max_bytes: int = 1_048_576, connection_factory=None):
        # IP literals prevent DNS rebinding and URL syntax from changing the target.
        try:
            address = ipaddress.ip_address(host)
        except ValueError as exc:
            raise ValueError("host must be an IP address") from exc
        if address.version != 4 or type(port) is not int or port not in (1024, 1025, 1026):
            raise ValueError("invalid IV endpoint")
        if not 0 < timeout <= 30 or type(max_bytes) is not int or not 1 <= max_bytes <= 64_000_000:
            raise ValueError("invalid HTTP bounds")
        self.host, self.port, self.timeout, self.max_bytes = host, port, timeout, max_bytes
        self._factory = connection_factory or http.client.HTTPConnection
        self._lock = Lock()

    def read(self, kind: str, *, item_id: int | None = None,
             option: str | None = None) -> IVResponse:
        path = path_for(kind, item_id=item_id, option=option)
        with self._lock:
            connection = self._factory(self.host, self.port, timeout=self.timeout)
            try:
                connection.request("GET", path, headers={"Accept": "application/json, text/tab-separated-values"})
                response = connection.getresponse()
                # Redirects and errors are returned as faults, never followed.
                if response.status != 200:
                    raise IVReadError(f"HTTP {response.status} for {path}")
                content_length = response.getheader("Content-Length")
                if content_length is not None:
                    try:
                        declared = int(content_length)
                    except ValueError as exc:
                        raise IVReadError("invalid Content-Length") from exc
                    if declared > self.max_bytes:
                        raise IVReadError("response exceeds byte limit")
                raw = response.read(self.max_bytes + 1)
                if len(raw) > self.max_bytes:
                    raise IVReadError("response exceeds byte limit")
                if kind == "export_log":
                    try:
                        value = raw.decode("utf-8")
                    except UnicodeError as exc:
                        raise IVReadError("invalid TSV encoding") from exc
                else:
                    try:
                        value = json.loads(raw.decode("utf-8"))
                    except (UnicodeError, json.JSONDecodeError) as exc:
                        raise IVReadError("invalid JSON response") from exc
                return IVResponse(path, response.status, raw, value)
            except (OSError, TimeoutError, http.client.HTTPException) as exc:
                raise IVReadError(f"transport failed for {path}: {exc}") from exc
            finally:
                connection.close()
