"""Atomic configuration storage. Secrets are preserved across redacted edits."""

import copy
import json
import math
import os
import tempfile
from pathlib import Path


REDACTED = "********"


class ConfigError(ValueError):
    def __init__(self, errors: dict[str, str]):
        self.errors = errors
        super().__init__(str(errors))


class RevisionConflict(RuntimeError):
    pass


def _redact(value):
    if isinstance(value, dict):
        return {k: (REDACTED if k in {"password", "token", "secret", "dsn", "secret_ref"} and v else _redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


def _preserve_secret(new, old):
    if isinstance(new, dict):
        for key, value in list(new.items()):
            prior = old.get(key) if isinstance(old, dict) else None
            if key in {"password", "token", "secret", "dsn", "secret_ref"} and value == REDACTED:
                if prior is None:
                    raise ConfigError({key: "redacted placeholder has no existing secret"})
                new[key] = prior
            else:
                _preserve_secret(value, prior)
    elif isinstance(new, list):
        prior_by_id = {item.get("id"): item for item in old if isinstance(item, dict) and item.get("id")} if isinstance(old, list) else {}
        for item in new:
            _preserve_secret(item, prior_by_id.get(item.get("id")) if isinstance(item, dict) else None)


def validate_config(document: dict) -> None:
    errors = {}
    if not isinstance(document, dict):
        raise ConfigError({"$": "must be an object"})
    if document.get("version") != 1:
        errors["version"] = "must be 1"
    if document.get("auto_start", False) is not False:
        errors["auto_start"] = "automatic start is not supported in this release"
    if isinstance(document.get("machines", []), list) and len(document.get("machines", [])) > 8:
        errors["machines"] = "at most 8 machines"
    for name in ("machines", "destinations"):
        if name not in document:
            errors[name] = "required list"
            continue
        entries = document[name]
        if not isinstance(entries, list):
            errors[name] = "must be a list"
            continue
        seen = set()
        for i, entry in enumerate(entries):
            p = f"{name}[{i}]"
            if not isinstance(entry, dict):
                errors[p] = "must be an object"
                continue
            ident = entry.get("id")
            if not isinstance(ident, str) or not ident.strip():
                errors[p + ".id"] = "required nonempty string"
            elif ident in seen:
                errors[p + ".id"] = "duplicate ID"
            seen.add(ident)
            if name == "machines":
                model = entry.get("model")
                if model not in ("III", "IV"):
                    errors[p + ".model"] = "must be III or IV"
                interval = entry.get("poll_interval_seconds", 1)
                if isinstance(interval, bool) or not isinstance(interval, (int, float)) or not math.isfinite(interval) or interval < 1:
                    errors[p + ".poll_interval_seconds"] = "must be finite and at least 1"
                refresh = entry.get("inventory_interval_seconds", 3600)
                if isinstance(refresh, bool) or not isinstance(refresh, (int, float)) or not math.isfinite(refresh) or refresh < 60:
                    errors[p + ".inventory_interval_seconds"] = "must be finite and at least 60"
                if model == "III":
                    port = entry.get("port")
                    if not isinstance(port, str) or not port.startswith("/dev/serial/by-id/"):
                        errors[p + ".port"] = "select a /dev/serial/by-id device"
                    count = entry.get("channel_count")
                    if type(count) is not int or not 1 <= count <= 100:
                        errors[p + ".channel_count"] = "evidenced count 1–100 required"
                if model == "IV":
                    import ipaddress
                    try:
                        if ipaddress.ip_address(entry.get("host")).version != 4:
                            raise ValueError()
                    except (ValueError, TypeError):
                        errors[p + ".host"] = "IPv4 address required"
                    port = entry.get("port", 1024)
                    if type(port) is not int or port not in (1024, 1025, 1026):
                        errors[p + ".port"] = "must be 1024, 1025, or 1026"
                    for field, limit in (("channel_count", 400), ("recipe_count", 100)):
                        count = entry.get(field)
                        if type(count) is not int or not 1 <= count <= limit:
                            errors[p + "." + field] = f"evidenced count 1–{limit} required"
            else:
                if entry.get("kind") not in ("mqtt", "postgres", "influxdb"):
                    errors[p + ".kind"] = "unsupported destination"
                kind = entry.get("kind")
                if not isinstance(entry.get("secret_ref"), str) or not entry.get("secret_ref"):
                    errors[p + ".secret_ref"] = "secret file reference required"
                if kind == "mqtt":
                    if not isinstance(entry.get("host"), str) or not entry.get("host"):
                        errors[p + ".host"] = "broker host required"
                    if not isinstance(entry.get("topic"), str) or not entry.get("topic"):
                        errors[p + ".topic"] = "topic required"
                    size = entry.get("max_payload_bytes", 262144)
                    if type(size) is not int or not 1024 <= size <= 262144:
                        errors[p + ".max_payload_bytes"] = "must be 1024–262144"
                if kind == "influxdb":
                    for key in ("url", "org", "bucket"):
                        if not isinstance(entry.get(key), str) or not entry.get(key):
                            errors[p + "." + key] = "required"
                    size = entry.get("max_payload_bytes", 8388608)
                    if type(size) is not int or size < 8388608:
                        errors[p + ".max_payload_bytes"] = "must be at least 8388608 to preserve accepted records"
                for secret_key in ("password", "token", "secret", "dsn"):
                    if secret_key in entry and entry[secret_key] not in (None, ""):
                        errors[p + "." + secret_key] = "use a secret_ref instead of an inline secret"
                if "secret_ref" in entry and (not isinstance(entry["secret_ref"], str) or not entry["secret_ref"].strip()):
                    errors[p + ".secret_ref"] = "must be a nonempty reference"
    ports = {}
    iv_endpoints = set()
    for i, machine in enumerate(document.get("machines", []) if isinstance(document.get("machines", []), list) else []):
        if isinstance(machine, dict) and machine.get("model") == "III":
            port = machine.get("port")
            if port in ports:
                errors[f"machines[{i}].port"] = "duplicate serial port"
            ports[port] = i
        if isinstance(machine, dict) and machine.get("model") == "IV":
            endpoint = (machine.get("host"), machine.get("port", 1024))
            if endpoint in iv_endpoints:
                errors[f"machines[{i}].port"] = "duplicate IV endpoint"
            iv_endpoints.add(endpoint)
    if errors:
        raise ConfigError(errors)


class ConfigStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _raw(self):
        if not self.path.exists():
            return {"version": 1, "revision": 0, "auto_start": False, "machines": [], "destinations": []}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def load(self) -> dict:
        return _redact(self._raw())

    def load_runtime(self) -> dict:
        """Internal configuration with secret references; never return through API."""
        return copy.deepcopy(self._raw())

    def save(self, expected_revision: int, document: dict) -> dict:
        import fcntl

        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        with lock_path.open("a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            old = self._raw()
            if expected_revision != old["revision"]:
                raise RevisionConflict(f"expected {expected_revision}, current {old['revision']}")
            new = copy.deepcopy(document)
            _preserve_secret(new, old)
            validate_config(new)
            new["revision"] = old["revision"] + 1
            new.setdefault("auto_start", False)
            data = json.dumps(new, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()
            fd, tmp = tempfile.mkstemp(prefix=".config-", dir=self.path.parent)
            try:
                os.fchmod(fd, 0o600)
                with os.fdopen(fd, "wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(tmp, self.path)
                dir_fd = os.open(self.path.parent, os.O_DIRECTORY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)
            return _redact(new)
