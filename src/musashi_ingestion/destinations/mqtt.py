"""MQTT QoS 1 JSON envelopes with byte-bounded UTF-8 chunks.

The injected client follows paho's publish API. ``wait_for_publish`` must
complete successfully before the spool can acknowledge the record.
"""

import base64
import json


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def chunk_record(record: dict, max_payload_bytes: int) -> list[bytes]:
    if max_payload_bytes <= 0:
        raise ValueError("max_payload_bytes must be positive")
    body = _json_bytes(record)
    # Base64 guarantees that every fragment is valid UTF-8 JSON even when a
    # split falls inside a multibyte code point. Reassembly decodes after join.
    encoded = base64.b64encode(body).decode("ascii")
    record_id = record["record_id"]

    def pack(parts):
        count = len(parts)
        return [_json_bytes({"version": 1, "record_id": record_id,
                             "index": index, "count": count,
                             "encoding": "base64-json-utf8", "data": part})
                for index, part in enumerate(parts)]

    parts = [encoded]
    while True:
        messages = pack(parts)
        if all(len(message) <= max_payload_bytes for message in messages):
            return messages
        changed = False
        next_parts = []
        for part, message in zip(parts, messages):
            if len(message) <= max_payload_bytes:
                next_parts.append(part)
            elif len(part) > 1:
                middle = len(part) // 2
                next_parts.extend((part[:middle], part[middle:]))
                changed = True
            else:
                raise ValueError("max_payload_bytes cannot fit MQTT envelope")
        if not changed:
            raise ValueError("max_payload_bytes cannot fit MQTT envelope")
        parts = next_parts


class MQTTDestination:
    def __init__(self, client, topic: str, *, max_payload_bytes: int = 262144,
                 ack_timeout_seconds: float = 30):
        self.client = client
        self.topic = topic
        self.max_payload_bytes = max_payload_bytes
        self.ack_timeout_seconds = ack_timeout_seconds

    def send(self, record: dict) -> None:
        for payload in chunk_record(record, self.max_payload_bytes):
            info = self.client.publish(self.topic, payload, qos=1)
            if getattr(info, "rc", 0) != 0:
                raise RuntimeError("MQTT publish rejected")
            info.wait_for_publish(timeout=self.ack_timeout_seconds)
            if not info.is_published():
                raise TimeoutError("MQTT PUBACK not received")

    def close(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()
