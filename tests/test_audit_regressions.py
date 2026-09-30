"""Synthetic regression checks for collection and destination audit findings."""

import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from musashi_ingestion.config.store import ConfigStore
from musashi_ingestion.destinations.influx import line_for_record
from musashi_ingestion.devices.iv import IVReader, IVReadError
from musashi_ingestion.pipeline.spool import Spool, make_record
from musashi_ingestion.runtime.supervisor import Supervisor
from test_iv_contract import Connection, Response
from test_runtime import FakeII


class AuditRegressions(unittest.TestCase):
    def test_lane_reroutes_only_pending_and_backfills_retained_history(self):
        with tempfile.TemporaryDirectory() as directory:
            spool = Spool(Path(directory) / "s.db")
            spool.commit(make_record("iv", "IV", "status", "status", {"value": 1}, record_id="before"))
            old = spool.register_target("influxdb", {"url": "old"}, lane_id="main")
            other = spool.register_target("mqtt", {"host": "other"}, lane_id="other")
            spool.ack(old, "before")
            spool.commit(make_record("iv", "IV", "status", "status", {"value": 2}, record_id="pending"), [old, other])
            new = spool.register_target("influxdb", {"url": "new"}, lane_id="main")
            self.assertEqual([r["record_id"] for r in spool.pending(new)], ["pending"])
            self.assertEqual(spool.pending(old), [])
            self.assertEqual(len(spool.pending(other)), 2)
            self.assertIsNotNone(spool.db.execute("SELECT acknowledged_at FROM deliveries WHERE record_id='before' AND target_id=?", (old,)).fetchone()[0])
            self.assertEqual(spool.db.execute("SELECT moved_pending FROM reroute_audit ORDER BY id DESC LIMIT 1").fetchone()[0], 1)
            spool.close()

    def test_legacy_queue_migration_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            spool = Spool(Path(directory) / "s.db")
            legacy = {"id": "main", "url": "old", "max_payload_bytes": 123}
            old = spool.register_target("influxdb", legacy)
            spool.commit(make_record("iv", "IV", "status", "status", {"value": 1}), [old])
            new = spool.register_target("influxdb", {"id": "main", "url": "old"},
                                        lane_id="main", legacy_settings=legacy)
            spool.register_target("influxdb", {"id": "main", "url": "old"},
                                  lane_id="main", legacy_settings=legacy)
            self.assertEqual(spool.stats()["pending"], 1)
            self.assertEqual(len(spool.pending(new)), 1)
            self.assertEqual(spool.pending(old), [])
            spool.close()

    def test_scan_series_are_bounded_and_replay_is_stable(self):
        with tempfile.TemporaryDirectory() as directory:
            spool = Spool(Path(directory) / "s.db")
            for scan in ("one", "two"):
                spool.commit(make_record("iv", "IV", "scan", "inventory:" + scan, {"value": {"scan_id": scan}}))
            records = spool.list_records(2)
            lines = [line_for_record(r) for r in records]
            self.assertEqual(lines[0].split(" ")[0], lines[1].split(" ")[0])
            self.assertNotEqual(lines[0], lines[1])
            self.assertEqual(lines[0], line_for_record(records[0]))
            spool.close()

    def test_nested_ranges_and_plain_text_clock(self):
        machine = {"channel_count": 1, "recipe_count": 100}
        for kind, family, maximum in (("channel_range", "ch", 399), ("recipe_range", "recipe", 99)):
            Supervisor._validate_iv_inventory(machine, (kind, None, None),
                                              {family: {"no": {"min": 0, "max": maximum}}})
        Supervisor._validate_iv_inventory(machine, ("channel_all", None, None),
                                          {"ch": [{"no": 0}, {"no": 399}]})
        for text, valid in (("2026-09-30T09:16:19+09:00", True), ("invalid", False)):
            responses = {"/v1/time": Response(200, text.encode())}
            reader = IVReader("127.0.0.1", connection_factory=lambda *a, **k: Connection([], responses))
            if valid:
                self.assertEqual(reader.read("time").value, text)
            else:
                with self.assertRaises(IVReadError):
                    reader.read("time")

    def test_shutdown_cancels_remaining_status_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spool = Spool(root / "s.db")
            supervisor = Supervisor(ConfigStore(root / "config.json"), spool)
            stop = threading.Event()
            stop.set()
            fake = FakeII("synthetic")
            supervisor._poll({"id": "iii", "model": "III"}, fake, stop=stop)
            self.assertEqual(fake.calls, [])
            self.assertEqual(spool.stats()["records"], 0)
            spool.close()

    def test_inventory_advances_before_next_status_poll_and_stop_drains_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            secret = root / "secret"
            secret.write_text("synthetic")
            store = ConfigStore(root / "config.json")
            config = {"version": 1, "machines": [{"id": "iii", "model": "III",
                      "port": "/dev/serial/by-id/synthetic", "channel_count": 1,
                      "poll_interval_seconds": 60, "inventory_interval_seconds": 60}],
                      "destinations": [{"id": "main", "kind": "influxdb", "url": "http://127.0.0.1:8086",
                      "org": "synthetic", "bucket": "synthetic", "secret_ref": str(secret)}]}
            store.save(0, config)
            spool = Spool(root / "s.db")
            fake = FakeII("synthetic")
            supervisor = Supervisor(store, spool, ii_factory=lambda port: fake)
            sent = []
            class Sink:
                def send(self, record): sent.append(record)
                def close(self): pass
            with patch("musashi_ingestion.runtime.supervisor.create_destination", return_value=Sink()):
                try:
                    supervisor.start()
                    deadline = time.monotonic() + 2
                    while time.monotonic() < deadline:
                        if any(scan["completed_at"] for scan in spool.list_scans()):
                            break
                        time.sleep(0.01)
                    self.assertTrue(any(scan["completed_at"] for scan in spool.list_scans()))
                    # Change a tuning setting; the destination's lane identity stays.
                    before = supervisor._target_ids
                    supervisor.stop(timeout=3)
                    config["destinations"][0]["max_payload_bytes"] = 16777216
                    store.save(1, config)
                    supervisor.start()
                    self.assertEqual(supervisor._target_ids, before)
                    supervisor.stop(timeout=3)
                    self.assertEqual(spool.stats()["pending"], 0)
                    self.assertTrue(any(r["record_type"] == "scan" for r in sent))
                    self.assertFalse(any(t.is_alive() for t in supervisor._delivery_threads.values()))
                finally:
                    supervisor.stop(timeout=3)
                    spool.close()


if __name__ == "__main__":
    unittest.main()
