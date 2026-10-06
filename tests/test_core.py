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
            record = make_record("ii", "III", "status", "D01", {"value": "synthetic"})
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
                spool.commit(make_record("ii", "III", "status", "D01", {"huge": "x" * 3000}))
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
            replay_line = line_for_record(previous)
            measurement_and_tags, fields = replay_line.split(" ", 1)
            self.assertTrue(measurement_and_tags.startswith("musashi_iv,"))
            self.assertIn("source=/v1/export/log", measurement_and_tags)
            self.assertIn("record_type=export", measurement_and_tags)
            self.assertNotIn("record_id=", measurement_and_tags)
            self.assertIn("record_id=", fields)
            self.assertIn("body=", fields)
            spool.close()
            reopened = Spool(Path(directory) / "spool.sqlite3")
            self.assertEqual(line_for_record(reopened.list_records(limit=2)[1]), replay_line)
            reopened.close()

    def test_quota_evicts_oldest_pending_records_and_accepts_new_data(self):
        with tempfile.TemporaryDirectory() as directory:
            spool = Spool(Path(directory) / "spool.sqlite3", max_record_bytes=2048,
                          max_spool_bytes=400_000)
            for counter in range(500):
                spool.commit(make_record("ii", "III", "status", "D05",
                                         {"counter": counter, "padding": "x" * 200}))
            self.assertLess(spool.stats()["records"], 500)
            self.assertIsNone(spool.stats()["fault"])
            target = spool.register_target("mqtt", {"id": "synthetic"})
            for counter in range(500, 1000):
                spool.commit(make_record("ii", "III", "status", "D05",
                                         {"counter": counter, "padding": "x" * 500}), [target])
                self.assertLessEqual(spool.stats()["disk_bytes"], spool.max_spool_bytes)
            self.assertGreater(spool.stats()["pending"], 0)
            pending = spool.pending(target, limit=2000)
            counters = [r["values"]["counter"] for r in pending]
            self.assertEqual(counters, list(range(counters[0], 1000)))
            self.assertGreater(counters[0], 500)
            self.assertIsNone(spool.stats()["fault"])
            evicted = spool.stats()["evicted_record_count"]
            self.assertEqual(evicted + spool.stats()["records"], 1000)
            spool.close()
            spool = Spool(Path(directory) / "spool.sqlite3")
            self.assertEqual(spool.stats()["evicted_record_count"], evicted)
            self.assertEqual([r["values"]["counter"] for r in spool.pending(target, 2000)], counters)
            spool.close()

    def test_quota_eviction_cleans_all_lanes_and_preserves_scan_outcomes(self):
        with tempfile.TemporaryDirectory() as directory:
            spool = Spool(Path(directory) / "spool.sqlite3", max_record_bytes=20_000,
                          max_spool_bytes=300_000)
            spool.db.execute("PRAGMA foreign_keys=ON")
            first = spool.register_target("mqtt", {"host": "first"})
            second = spool.register_target("mqtt", {"host": "second"})
            old = make_record("ii", "III", "inventory", "D01", {"padding": "x" * 10_000})
            spool.commit(old, [first, second])
            scan = spool.begin_scan("ii", "inventory", expected_items=["D01:1", "D02:1"])
            spool.record_scan_item(scan, "D01:1", old["record_id"])
            for counter in range(50):
                spool.commit(make_record("ii", "III", "status", "D05",
                                         {"counter": counter, "padding": "x" * 10_000}), [first, second])
            self.assertEqual(spool.scan_items(scan)[0],
                             {"item_key": "D01:1", "record_id": None, "outcome": "ok"})
            self.assertEqual(spool.scan_items(scan)[1]["outcome"], None)
            self.assertEqual(len(spool.incomplete_scans()), 1)
            self.assertEqual(spool.pending(first), spool.pending(second))
            self.assertNotIn(old["record_id"], [r["record_id"] for r in spool.pending(first)])
            # A sender may confirm an already fetched record after eviction.
            spool.ack(first, old["record_id"])
            self.assertEqual(spool.db.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertIsNone(spool.stats()["fault"])
            spool.close()

    def test_clear_spool_removes_local_history_and_preserves_point_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            spool = Spool(Path(directory) / "spool.sqlite3")
            target = spool.register_target("mqtt", {"host": "synthetic"})
            record = make_record("ii", "III", "status", "D01", {"value": "synthetic"})
            spool.commit(record, [target])
            scan = spool.begin_scan("ii", "inventory", expected_items=["D01:1"])
            spool.record_scan_item(scan, "D01:1", record["record_id"])
            spool._fault("synthetic fault")
            stored = spool.list_records(limit=1)[0]

            result = spool.clear_all()

            self.assertEqual(result["records"], 1)
            self.assertEqual(result["pending_deliveries"], 1)
            self.assertEqual(result["scans"], 1)
            self.assertEqual(result["faults"], 1)
            self.assertEqual(result["destination_identities"], 1)
            self.assertEqual(spool.stats()["records"], 0)
            self.assertEqual(spool.stats()["pending"], 0)
            self.assertEqual(spool.list_scans(), [])
            self.assertIsNone(spool.stats()["fault"])
            self.assertEqual(spool.db.execute("SELECT count(*) FROM targets").fetchone()[0], 0)
            next_record = make_record("ii", "III", "status", "D01", {"value": "next"},
                                      observed_at=record["observed_at"])
            spool.commit(next_record)
            stored_next = spool.list_records(limit=1)[0]
            self.assertEqual(stored_next["installation_id"], stored["installation_id"])
            self.assertGreater(stored_next["point_time_ns"], stored["point_time_ns"])
            spool.close()


if __name__ == "__main__":
    unittest.main()
