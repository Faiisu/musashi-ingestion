"""Synthetic delivery retry and acknowledgment checks."""

import tempfile
import hashlib
import unittest
from pathlib import Path
from unittest.mock import patch

from musashi_ingestion.config.store import ConfigStore
from musashi_ingestion.destinations import DeliveryWorker
from musashi_ingestion.destinations.mqtt import MQTTDestination
from musashi_ingestion.pipeline.spool import Spool, make_record
from musashi_ingestion.runtime.supervisor import Supervisor


class PublishInfo:
    rc = 0

    def __init__(self, acknowledged):
        self.acknowledged = acknowledged

    def wait_for_publish(self, timeout):
        return None

    def is_published(self):
        return self.acknowledged


class MQTTClient:
    def __init__(self, acknowledged):
        self.acknowledged = acknowledged
        self.messages = []

    def publish(self, topic, payload, qos):
        self.messages.append((topic, payload, qos))
        return PublishInfo(self.acknowledged)


class DeliveryTests(unittest.TestCase):
    def test_lost_puback_leaves_row_pending(self):
        with tempfile.TemporaryDirectory() as directory:
            spool = Spool(Path(directory) / "spool.sqlite3")
            target = spool.register_target("mqtt", {"host": "synthetic"})
            record = make_record("ii", "III", "status", "D01", {"text": "ทดสอบ" * 100})
            spool.commit(record, [target])
            lost = MQTTClient(False)
            with self.assertRaises(TimeoutError):
                DeliveryWorker(spool, target, MQTTDestination(lost, "synthetic", max_payload_bytes=1024)).drain()
            self.assertEqual(len(spool.pending(target)), 1)
            received = MQTTClient(True)
            self.assertEqual(DeliveryWorker(spool, target,
                             MQTTDestination(received, "synthetic", max_payload_bytes=1024)).drain(), 1)
            self.assertFalse(spool.pending(target))
            self.assertTrue(all(qos == 1 and len(payload) <= 1024 for _, payload, qos in received.messages))
            spool.close()

    def test_failed_close_does_not_stop_delivery_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            secret = root / "secret.txt"
            secret.write_text("synthetic")
            digest = hashlib.sha256(secret.read_bytes()).hexdigest()
            spool = Spool(root / "spool.sqlite3")
            target = spool.register_target("mqtt", {"host": "synthetic"})
            spool.commit(make_record("ii", "III", "status", "D01", {"value": 1}), [target])
            supervisor = Supervisor(ConfigStore(root / "config.json"), spool)
            supervisor._delivery_states[target] = {"state": "starting", "error": None, "last_success": None}

            class FastStop:
                stopped = False
                def is_set(self): return self.stopped
                def wait(self, seconds): return False

            stop = FastStop()

            class Broken:
                def send(self, record): raise RuntimeError("synthetic failure")
                def close(self): raise RuntimeError("close failed")

            class Healthy:
                def send(self, record): stop.stopped = True
                def close(self): pass

            clients = iter((Broken(), Healthy()))
            with patch("musashi_ingestion.runtime.supervisor.create_destination", side_effect=lambda config: next(clients)):
                supervisor._run_delivery(target, {"secret_ref": str(secret)}, digest, stop)
            self.assertFalse(spool.pending(target))
            spool.close()


if __name__ == "__main__":
    unittest.main()
