"""Lossless Influx line protocol encoding using complete JSON as a string field."""

import json


class MissingPointIdentity(ValueError):
    """A persisted record predates the spool-assigned Influx identity."""

    def __init__(self, record_id):
        self.record_id = record_id
        super().__init__(f"record {record_id} lacks durable Influx point identity")


def _escape_tag(value):
    return str(value).replace("\\", "\\\\").replace(" ", "\\ ").replace(",", "\\,").replace("=", "\\=")


def _escape_field(value):
    return json.dumps(value, ensure_ascii=False)


def line_for_record(record: dict) -> str:
    # The spool allocates a stable unique point time; only the installation is a tag.
    installation_id = record.get("installation_id")
    point_time_ns = record.get("point_time_ns")
    if (not isinstance(installation_id, str) or not installation_id
            or type(point_time_ns) is not int or not 0 <= point_time_ns < 2**63):
        raise MissingPointIdentity(record.get("record_id", "<unknown>"))
    tags = f"installation_id={_escape_tag(installation_id)}"
    body = json.dumps(record, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)
    return f"musashi_record,{tags} body={_escape_field(body)} {point_time_ns}"


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
