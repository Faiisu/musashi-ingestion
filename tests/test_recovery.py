"""Hardware-free recovery checks using a real SQLite file and a killed process."""

import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from musashi_ingestion.config.store import ConfigStore
from musashi_ingestion.destinations import DeliveryWorker
from musashi_ingestion.pipeline.spool import Spool, SpoolError, make_record


class RecoveryTests(unittest.TestCase):
    def test_sqlite_full_rejects_write_and_reports_fault(self):
        with tempfile.TemporaryDirectory() as directory:
            spool = Spool(Path(directory) / "spool.sqlite3", max_record_bytes=1_000_000,
                          max_spool_bytes=10_000_000)
            target = spool.register_target("mqtt", {"host": "old"})
            pages = spool.db.execute("PRAGMA page_count").fetchone()[0]
            spool.db.execute(f"PRAGMA max_page_count={pages}")
            with self.assertRaises(SpoolError):
                spool.commit(make_record("ii", "III", "status", "D01", {"value": "x" * 300_000}), [target])
            self.assertEqual(spool.stats()["records"], 0)
            self.assertEqual(spool.stats()["pending"], 0)
            self.assertIn("commit failed", spool.stats()["fault"])
            spool.close()

    def test_sqlite_full_still_raises_spool_fault_when_fault_row_cannot_be_written(self):
        with tempfile.TemporaryDirectory() as directory:
            spool = Spool(Path(directory) / "spool.sqlite3", max_record_bytes=1_000_000,
                          max_spool_bytes=10_000_000)
            pages = spool.db.execute("PRAGMA page_count").fetchone()[0]
            spool.db.execute(f"PRAGMA max_page_count={pages}")
            with patch.object(spool, "_fault", side_effect=sqlite3.OperationalError("database or disk is full")):
                with self.assertRaisesRegex(SpoolError, "spool commit failed"):
                    spool.commit(make_record("ii", "III", "status", "D01",
                                             {"value": "x" * 300_000}))
            self.assertEqual(spool.stats()["records"], 0)
            spool.close()

    def test_kill_during_transaction_preserves_only_committed_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "spool.sqlite3"
            marker = root / "in-transaction"
            child = r'''
import json
import sys
import time
from pathlib import Path
from musashi_ingestion.pipeline.spool import Spool, make_record

database, marker = map(Path, sys.argv[1:])
spool = Spool(database)
target = spool.register_target("mqtt", {"host": "old"})
record = make_record("ii", "III", "status", "D01", {"value": 1}, record_id="committed")
spool.commit(record, [target])
scan = spool.begin_scan("ii", "inventory", scan_id="partial-scan", expected_items=["D01:1", "D02:1"])
spool.record_scan_item(scan, "D01:1", record["record_id"])
spool.db.execute("BEGIN IMMEDIATE")
spool.db.execute("INSERT INTO records VALUES(?,?,?,?)", ("uncommitted", b"{}", 2, spool._now()))
marker.write_text(target)
time.sleep(30)
'''
            env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
            process = subprocess.Popen([sys.executable, "-c", child, str(database), str(marker)], env=env)
            try:
                deadline = time.monotonic() + 5
                while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(marker.exists(), "child never reached the open transaction")
            finally:
                process.kill()
                process.wait(timeout=5)

            target = marker.read_text()
            spool = Spool(database)
            self.assertEqual([record["record_id"] for record in spool.pending(target)], ["committed"])
            self.assertEqual(spool.stats()["records"], 1)
            self.assertEqual(spool.scan_items("partial-scan"), [
                {"item_key": "D01:1", "record_id": "committed", "outcome": "ok"},
                {"item_key": "D02:1", "record_id": None, "outcome": None},
            ])
            self.assertEqual(len(spool.incomplete_scans()), 1)
            spool.close()

    def test_outage_lost_ack_and_target_change(self):
        with tempfile.TemporaryDirectory() as directory:
            spool = Spool(Path(directory) / "spool.sqlite3")
            old = spool.register_target("postgres", {"host": "old"})
            record = make_record("ii", "III", "status", "D01", {"value": 2})
            spool.commit(record, [old])
            new = spool.register_target("postgres", {"host": "new"})
            self.assertEqual(spool.pending(new), [])

            class FailedDestination:
                def send(self, record):
                    raise ConnectionError("synthetic outage")

            with self.assertRaises(ConnectionError):
                DeliveryWorker(spool, old, FailedDestination()).drain()
            self.assertEqual(len(spool.pending(old)), 1)
            spool.close()
            spool = Spool(Path(directory) / "spool.sqlite3")

            delivered_ids = set()
            attempts = []

            class LostAckDestination:
                def send(self, item):
                    attempts.append(item["record_id"])
                    delivered_ids.add(item["record_id"])
                    raise TimeoutError("acceptance happened but acknowledgment was lost")

            with self.assertRaises(TimeoutError):
                DeliveryWorker(spool, old, LostAckDestination()).drain()
            self.assertEqual(len(spool.pending(old)), 1)

            class RecoveredDestination:
                def send(self, item):
                    attempts.append(item["record_id"])
                    delivered_ids.add(item["record_id"])

            self.assertEqual(DeliveryWorker(spool, old, RecoveredDestination()).drain(), 1)
            self.assertEqual(attempts, [record["record_id"], record["record_id"]])
            self.assertEqual(delivered_ids, {record["record_id"]})
            self.assertEqual(spool.pending(old), [])
            self.assertEqual(spool.pending(new), [])
            spool.close()

    def test_live_sqlite_backup_restores_pending_scan_and_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            restored = root / "restored"
            source.mkdir()
            restored.mkdir()
            store = ConfigStore(source / "config.json")
            store.save(0, {"version": 1, "machines": [], "destinations": []})
            spool = Spool(source / "spool.sqlite3")
            target = spool.register_target("mqtt", {"host": "old"})
            record = make_record("ii", "III", "status", "D01", {"value": 3})
            spool.commit(record, [target])
            scan = spool.begin_scan("ii", "inventory", expected_items=["D01:1", "D02:1"])
            spool.record_scan_item(scan, "D01:1", record["record_id"])
            shutil.copy2(source / "config.json", restored / "config.json")
            with sqlite3.connect(restored / "spool.sqlite3") as backup:
                spool.db.backup(backup)
            spool.close()

            self.assertEqual(ConfigStore(restored / "config.json").load_runtime()["version"], 1)
            recovered = Spool(restored / "spool.sqlite3")
            self.assertEqual(recovered.pending(target)[0]["record_id"], record["record_id"])
            self.assertEqual(recovered.scan_items(scan)[1]["outcome"], None)
            self.assertEqual(recovered.stats()["incomplete_scans"], 1)
            self.assertEqual(recovered.register_target("mqtt", {"host": "old"}), target)
            recovered.close()


if __name__ == "__main__":
    unittest.main()
