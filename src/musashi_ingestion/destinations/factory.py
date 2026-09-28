"""Build external destination clients from validated, private configuration.

``secret_ref`` names a UTF-8 file. PostgreSQL files contain a DSN, Influx
files contain a token, and MQTT files contain JSON with username/password.
Errors intentionally omit connection strings, paths, and secret values.
"""

import json
from pathlib import Path

from .influx import InfluxDestination
from .mqtt import MQTTDestination
from .postgres import PostgresDestination
from .postgres import MIGRATION_001


class DestinationSetupError(RuntimeError):
    """A target could not be configured or connected."""


def _secret(config: dict) -> str:
    reference = config.get("secret_ref")
    if not isinstance(reference, str) or not reference or reference == "********":
        raise DestinationSetupError("destination secret_ref is required")
    try:
        secret = Path(reference).read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as exc:
        raise DestinationSetupError("destination secret file is unreadable") from None
    if not secret:
        raise DestinationSetupError("destination secret file is empty")
    return secret


def create_destination(config: dict):
    """Return a connected adapter exposing ``send(record)`` and ``close()``.

    Pass the unredacted stored configuration, not ``ConfigStore.load()``.
    Optional packages: paho-mqtt, psycopg[binary], influxdb-client.
    """
    kind = config.get("kind")
    if kind == "mqtt":
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            raise DestinationSetupError("paho-mqtt is required for MQTT") from None
        try:
            credentials = json.loads(_secret(config))
            if not isinstance(credentials, dict) or not isinstance(credentials.get("username"), str) or not isinstance(credentials.get("password"), str):
                raise ValueError()
        except (ValueError, TypeError):
            raise DestinationSetupError("MQTT secret must be username/password JSON") from None
        host = config.get("host") or config.get("broker_host")
        topic = config.get("topic")
        if not isinstance(host, str) or not host or not isinstance(topic, str) or not topic:
            raise DestinationSetupError("MQTT host and topic are required")
        try:
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
            client.username_pw_set(credentials["username"], credentials["password"])
            if config.get("tls", False):
                client.tls_set(ca_certs=config.get("ca_file"))
            client.connect(host, int(config.get("port", 8883 if config.get("tls") else 1883)), keepalive=60)
            client.loop_start()
            return MQTTDestination(client, topic, max_payload_bytes=int(config.get("max_payload_bytes", 262144)))
        except Exception:
            raise DestinationSetupError("MQTT connection failed") from None
    if kind == "postgres":
        try:
            import psycopg
        except ImportError:
            raise DestinationSetupError("psycopg is required for PostgreSQL") from None
        try:
            connection = psycopg.connect(_secret(config), connect_timeout=int(config.get("connect_timeout_seconds", 10)))
            with connection.cursor() as cursor:
                cursor.execute(MIGRATION_001)
            connection.commit()
            return PostgresDestination(connection)
        except DestinationSetupError:
            raise
        except Exception:
            raise DestinationSetupError("PostgreSQL connection failed") from None
    if kind == "influxdb":
        try:
            from influxdb_client import InfluxDBClient
            from influxdb_client.client.write_api import SYNCHRONOUS
        except ImportError:
            raise DestinationSetupError("influxdb-client is required for InfluxDB") from None
        url, org, bucket = (config.get(name) for name in ("url", "org", "bucket"))
        if not all(isinstance(value, str) and value for value in (url, org, bucket)):
            raise DestinationSetupError("InfluxDB url, org, and bucket are required")
        try:
            client = InfluxDBClient(url=url, token=_secret(config), org=org,
                                    timeout=int(config.get("timeout_ms", 10000)),
                                    verify_ssl=config.get("verify_ssl", True))
            if not client.ping():
                client.close()
                raise DestinationSetupError("InfluxDB connection failed")
            destination = InfluxDestination(client.write_api(write_options=SYNCHRONOUS), bucket, org,
                                            max_payload_bytes=int(config.get("max_payload_bytes", 8388608)))
            destination.client = client
            return destination
        except DestinationSetupError:
            raise
        except Exception:
            raise DestinationSetupError("InfluxDB connection failed") from None
    raise DestinationSetupError("unsupported destination kind")
