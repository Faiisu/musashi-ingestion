"""Hardware-free regression checks for the rebuild's durable core."""

import tempfile
import unittest
from pathlib import Path

from musashi_ingestion.config.store import ConfigError, ConfigStore, RevisionConflict
from musashi_ingestion.devices.ii import request_frame
from musashi_ingestion.devices.iv import path_for
from musashi_ingestion.destinations.influx import line_for_record
from musashi_ingestion.destinations.mqtt import chunk_record
from musashi_ingestion.pipeline.spool import Spool, SpoolError, make_record


class CoreTests(unittest.TestCase):
    def test_config_revision_validation_and_redaction(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ConfigStore(Path(directory) / "config.json")
            document = {"version": 1, "machines": [{"id": "iv-1", "model": "IV",
                        "host": "127.0.0.1", "port": 1024, "channel_count": 1,
                        "recipe_count": 1, "poll_interval_seconds": 1}],
                        "destinations": [{"id": "broker", "kind": "mqtt", "host": "127.0.0.1",
                                          "topic": "synthetic", "secret_ref": "/tmp/synthetic-secret"}]}
            saved = store.save(0, document)
            self.assertEqual(saved["destinations"][0]["secret_ref"], "********")
            self.assertEqual(store.load_runtime()["destinations"][0]["secret_ref"], "/tmp/synthetic-secret")
            with self.assertRaises(RevisionConflict):
                store.save(0, document)
            document["machines"][0]["poll_interval_seconds"] = float("nan")
            with self.assertRaises(ConfigError):
                store.save(1, document)

    def test_spool_restart_identity_limits_and_scan_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "spool.sqlite3"
            spool = Spool(path, max_record_bytes=2048, max_spool_bytes=10_000_000)
            old = spool.register_target("mqtt", {"host": "old"})
            new = spool.register_target("mqtt", {"host": "new"})
            record = make_record("ii", "II", "status", "D01", {"value": "synthetic"})
            spool.commit(record, [old])
            scan = spool.begin_scan("ii", "inventory", expected_items=["D01:1", "D02:1"])
            spool.record_scan_item(scan, "D01:1", record["record_id"])
            spool.close()
            spool = Spool(path, max_record_bytes=2048, max_spool_bytes=10_000_000)
            self.assertEqual(spool.pending(old)[0]["record_id"], record["record_id"])
            self.assertEqual(spool.pending(new), [])
            self.assertEqual(spool.scan_items(scan)[1]["outcome"], None)
            with self.assertRaises(SpoolError):
                spool.finish_scan(scan)
            with self.assertRaises(SpoolError):
                spool.commit(make_record("ii", "II", "status", "D01", {"huge": "x" * 3000}))
            self.assertIsNotNone(spool.stats()["fault"])
            spool.close()

    def test_safe_request_catalog_and_destination_encoding(self):
        self.assertIn(b"UL001D01", request_frame("D01"))
        with self.assertRaises(ValueError):
            request_frame("START")
        with self.assertRaises(ValueError):
            path_for("status", option="current/dispense")
        with self.assertRaises(ValueError):
            path_for("channel_item", item_id=401)
        record = make_record("iv", "IV", "export", "/v1/export/log", {"text": "ทดสอบ" * 1000})
        messages = chunk_record(record, 1024)
        self.assertGreater(len(messages), 1)
        self.assertTrue(all(len(message) <= 1024 for message in messages))
        with tempfile.TemporaryDirectory() as directory:
            spool = Spool(Path(directory) / "spool.sqlite3")
            other = dict(record, record_id="another-id")
            spool.commit(record)
            spool.commit(other)
            newest, previous = spool.list_records(limit=2)
            self.assertEqual(newest["installation_id"], previous["installation_id"])
            self.assertNotEqual(newest["point_time_ns"], previous["point_time_ns"])
            self.assertNotEqual(line_for_record(newest), line_for_record(previous))
            self.assertIn("ทดสอบ", line_for_record(previous))
            self.assertNotIn("record_id=", line_for_record(previous).split(" body=")[0])
            replay_line = line_for_record(previous)
            spool.close()
            reopened = Spool(Path(directory) / "spool.sqlite3")
            self.assertEqual(line_for_record(reopened.list_records(limit=2)[1]), replay_line)
            reopened.close()

    def test_quota_prunes_delivered_history_but_faults_on_pending(self):
        with tempfile.TemporaryDirectory() as directory:
            spool = Spool(Path(directory) / "spool.sqlite3", max_record_bytes=2048,
                          max_spool_bytes=2_000_000)
            for counter in range(1500):
                spool.commit(make_record("ii", "II", "status", "D05",
                                         {"counter": counter, "padding": "x" * 200}))
            self.assertLess(spool.stats()["records"], 1500)
            self.assertIsNone(spool.stats()["fault"])
            target = spool.register_target("mqtt", {"id": "synthetic"})
            with self.assertRaises(SpoolError):
                for counter in range(5000):
                    spool.commit(make_record("ii", "II", "status", "D05",
                                             {"counter": counter, "padding": "x" * 500}), [target])
            self.assertGreater(spool.stats()["pending"], 0)
            self.assertIsNotNone(spool.stats()["fault"])
            spool.close()


if __name__ == "__main__":
    unittest.main()
