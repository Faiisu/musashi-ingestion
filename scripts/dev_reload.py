"""Run the dev service and restart it when a source file changes."""

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from urllib.parse import quote


SOURCE_DIR = Path("/app/src")
POLL_SECONDS = 0.5


def _write_secret(path: Path, value: str):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(value)
        stream.write("\n")


def _save_config(path: Path, document: dict):
    fd, temporary = tempfile.mkstemp(prefix=".config-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(document, stream, ensure_ascii=False, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def seed_dev_config():
    """Seed simulator machines and local destination services once per volume."""
    if os.environ.get("MUSASHI_DEV_DEFAULTS") != "1":
        return

    data_dir = Path(os.environ.get("MUSASHI_DATA_DIR", "/data"))
    config_path = data_dir / "config.json"
    data_dir.mkdir(parents=True, exist_ok=True)
    marker = data_dir / ".dev-defaults-v1"
    if marker.exists():
        return

    secrets_dir = data_dir / "secrets"
    mqtt_user = os.environ.get("DEV_MQTT_USER", "musashi")
    mqtt_password = os.environ.get("DEV_MQTT_PASSWORD", "dev-mqtt-password")
    postgres_user = os.environ.get("DEV_POSTGRES_USER", "musashi")
    postgres_password = os.environ.get("DEV_POSTGRES_PASSWORD", "dev-postgres-password")
    postgres_db = os.environ.get("DEV_POSTGRES_DB", "musashi_dev")
    influx_token = os.environ.get("DEV_INFLUX_TOKEN", "dev-influx-token-change-me")
    _write_secret(secrets_dir / "mqtt.json", json.dumps({"username": mqtt_user, "password": mqtt_password}))
    dsn = (f"postgresql://{quote(postgres_user, safe='')}:{quote(postgres_password, safe='')}"
           f"@postgres:5432/{quote(postgres_db, safe='')}")
    _write_secret(secrets_dir / "postgres-dsn", dsn)
    _write_secret(secrets_dir / "influx-token", influx_token)

    if config_path.exists():
        document = json.loads(config_path.read_text(encoding="utf-8"))
        destinations = document.setdefault("destinations", [])
        existing_ids = {item.get("id") for item in destinations if isinstance(item, dict)}
        revision = document.get("revision", 0)
        changed = False
    else:
        document = {
            "version": 1,
            "revision": 0,
            "auto_start": False,
            "machines": [
                {"id": "sim-iii", "model": "III", "port": "socket://musashi-iii:9000",
                 "channel_count": 4, "poll_interval_seconds": 1,
                 "inventory_interval_seconds": 3600, "simulated": True},
                {"id": "sim-iv", "model": "IV", "host": "172.30.200.3", "port": 1024,
                 "recipe_count": 100, "channel_count": 400, "poll_interval_seconds": 1,
                 "inventory_interval_seconds": 3600, "simulated": True},
            ],
            "destinations": [],
        }
        destinations = document["destinations"]
        existing_ids = set()
        revision = 0
        changed = True

    defaults = [
        {"id": "dev-mqtt", "kind": "mqtt", "host": "mqtt", "port": 1883,
         "topic": "musashi/dev", "tls": False, "secret_ref": str(secrets_dir / "mqtt.json")},
        {"id": "dev-postgres", "kind": "postgres", "secret_ref": str(secrets_dir / "postgres-dsn")},
        {"id": "dev-influxdb", "kind": "influxdb", "url": "http://influxdb:8086",
         "org": os.environ.get("DEV_INFLUX_ORG", "musashi-dev"),
         "bucket": os.environ.get("DEV_INFLUX_BUCKET", "musashi-dev"),
         "verify_ssl": False, "secret_ref": str(secrets_dir / "influx-token")},
    ]
    for destination in defaults:
        if destination["id"] not in existing_ids:
            destinations.append(destination)
            changed = True
    if changed:
        document["revision"] = revision + 1
        _save_config(config_path, document)

    try:
        fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write("seeded\n")


def source_snapshot():
    return {
        path.relative_to(SOURCE_DIR): (path.stat().st_mtime_ns, path.stat().st_size)
        for path in SOURCE_DIR.rglob("*")
        if path.is_file()
    }


def main():
    seed_dev_config()
    child = None
    stopping = False

    def stop(signum, frame):
        nonlocal stopping
        stopping = True
        if child is not None and child.poll() is None:
            child.send_signal(signal.SIGINT)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    snapshot = source_snapshot()
    while not stopping:
        child = subprocess.Popen([sys.executable, "-m", "musashi_ingestion"])
        while not stopping and child.poll() is None:
            time.sleep(POLL_SECONDS)
            updated = source_snapshot()
            if updated != snapshot:
                print("Source changed; restarting dev service.", flush=True)
                snapshot = updated
                child.send_signal(signal.SIGINT)
                break

        try:
            child.wait()
        except KeyboardInterrupt:
            stop(signal.SIGINT, None)
            child.wait()
        child = None

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
