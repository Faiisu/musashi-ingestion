"""Structured Influx line protocol encoding with a lossless record field."""

import json
import re


class MissingPointIdentity(ValueError):
    """A persisted record predates the spool-assigned Influx identity."""

    def __init__(self, record_id):
        self.record_id = record_id
        super().__init__(f"record {record_id} lacks durable Influx point identity")


def _escape_tag(value):
    return str(value).replace("\\", "\\\\").replace(" ", "\\ ").replace(",", "\\,").replace("=", "\\=")


def _escape_key(value):
    return str(value).replace("\\", "\\\\").replace(" ", "\\ ").replace(",", "\\,").replace("=", "\\=")


def _escape_field(value):
    return json.dumps(value, ensure_ascii=False)


def _field_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        if -(2**63) <= value < 2**63:
            # Parsed device values may be integer on one endpoint and float on
            # another. A shared Influx field requires one numeric type.
            return repr(float(value))
        return _escape_field(str(value))
    if isinstance(value, float):
        return repr(value)
    return _escape_field(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False,
                                                                          sort_keys=True,
                                                                          separators=(",", ":")))


def _flatten_fields(prefix, value):
    """Map nested values to stable scalar field names; nulls remain in body."""
    if value is None:
        return []
    if isinstance(value, dict) and value:
        fields = []
        for key, child in sorted(value.items()):
            fields.extend(_flatten_fields(f"{prefix}_{key}", child))
        return fields
    if isinstance(value, list):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return [(prefix, _field_value(value))]


def _value_field_prefix(record):
    source = record.get("source", "")
    record_type = record.get("record_type", "record")
    if record_type == "scan":
        source = "scan"
    else:
        source = re.sub(r":\d+$", "", str(source))
        source = re.sub(r"/\d+$", "/id", source)
    label = re.sub(r"[^A-Za-z0-9_]+", "_", source).strip("_").lower() or "unknown"
    return f"value_{label}"


def line_for_record(record: dict) -> str:
    # The spool allocates a stable unique point time. II is retained as a legacy
    # envelope alias because the connected serial machine was initially mislabeled.
    model = {"II": "III"}.get(record.get("model"), record.get("model"))
    if model not in ("III", "IV"):
        raise ValueError("record model must be III or IV")
    installation_id = record.get("installation_id")
    point_time_ns = record.get("point_time_ns")
    if (not isinstance(installation_id, str) or not installation_id
            or type(point_time_ns) is not int or not 0 <= point_time_ns < 2**63):
        raise MissingPointIdentity(record.get("record_id", "<unknown>"))
    tag_values = {
        "installation_id": installation_id,
        "machine_id": record.get("machine_id"),
        "record_type": record.get("record_type"),
        "source": "inventory" if record.get("record_type") == "scan" else record.get("source"),
    }
    values = record.get("values")
    if isinstance(values, dict):
        for key in ("scope", "quality"):
            if isinstance(values.get(key), str):
                tag_values[key] = values[key]
    if record.get("channel_id") is not None:
        tag_values["channel_id"] = record["channel_id"]
    tags = ",".join(f"{_escape_key(key)}={_escape_tag(value)}"
                     for key, value in tag_values.items() if value is not None)
    body = json.dumps(record, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)
    fields = [("record_id", _field_value(record.get("record_id", ""))),
              ("observed_at", _field_value(record.get("observed_at", ""))),
              ("version", f"{record.get('version', 1)}i"),
              ("body", _field_value(body))]
    if isinstance(values, dict):
        fields.extend(_flatten_fields(_value_field_prefix(record), values.get("value")))
        if isinstance(values.get("raw"), str):
            fields.append(("raw", _field_value(values["raw"])))
        for key, value in values.items():
            if key not in {"value", "raw", "scope", "quality"}:
                fields.extend(_flatten_fields(f"data_{key}", value))
    encoded_fields = ",".join(f"{_escape_key(key)}={value}" for key, value in fields)
    return f"musashi_{model.lower()},{tags} {encoded_fields} {point_time_ns}"


def ensure_bucket(client, bucket: str, org: str) -> None:
    """Ensure the configured bucket exists within the configured organization."""
    from influxdb_client.rest import ApiException

    api = client.buckets_api()
    def exists():
        return any(item.name == bucket for item in api.find_buckets(name=bucket, org=org).buckets)

    if exists():
        return
    try:
        # An empty retention rule list creates a bucket with no expiration.
        api.create_bucket(bucket_name=bucket, org=org, retention_rules=[])
    except ApiException as exc:
        # Another ingestion instance may have created it after our lookup.
        if exc.status not in (409, 422) or not exists():
            raise


class InfluxDestination:
    def __init__(self, write_api, bucket: str, org: str, *, max_payload_bytes: int = 8_388_608):
        self.write_api = write_api
        self.bucket = bucket
        self.org = org
        self.max_payload_bytes = max_payload_bytes

    def send(self, record: dict) -> None:
        line = line_for_record(record)
        if len(line.encode("utf-8")) > self.max_payload_bytes:
            raise ValueError("Influx payload exceeds byte limit")
        # The provided write API must use synchronous writes; return implies
        # server acceptance. Asynchronous write APIs are unsuitable here.
        self.write_api.write(bucket=self.bucket, org=self.org, record=line)

    def close(self) -> None:
        if hasattr(self, "client"):
            self.client.close()
