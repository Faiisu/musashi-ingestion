"""Synthetic supervisor behavior without serial hardware or network access."""

import json
import tempfile
import time
import unittest
from pathlib import Path

from musashi_ingestion.config.store import ConfigStore
from musashi_ingestion.devices.ii import IIResponse
from musashi_ingestion.pipeline.spool import Spool
from musashi_ingestion.runtime.supervisor import Supervisor


class FakeII:
    def __init__(self, port, *, changed=False, fail_code=None):
        self.payloads = {entry["code"]: entry["payload"] for entry in
                         json.loads((Path(__file__).parent / "fixtures" / "ii_uploads.json").read_text())["uploads"]}
        self.changed = changed
        self.fail_code = fail_code
        self.calls = []
        self.d06_reads = 0

    def upload(self, code, channel=1):
        self.calls.append((code, channel))
        if code == self.fail_code:
            raise TimeoutError("synthetic timeout")
        payload = self.payloads[code]
        if code == "D06":
            self.d06_reads += 1
            if self.changed and self.d06_reads == 2:
                payload = "DA06CH021"
        return IIResponse(code, channel if code in ("D01", "D02", "D03", "D04") else None,
                          payload, b"synthetic")

    def close(self):
        pass


class RuntimeTests(unittest.TestCase):
    def test_machine_worker_keeps_reading_when_spool_quota_fills(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ConfigStore(Path(directory) / "config.json")
            store.save(0, {"version": 1, "machines": [
                {"id": "ii-1", "model": "III", "port": "/dev/serial/by-id/synthetic",
                 "channel_count": 1, "poll_interval_seconds": 1}], "destinations": []})
            spool = Spool(Path(directory) / "spool.sqlite3", max_record_bytes=50_000,
                          max_spool_bytes=400_000)

            class LargeFakeII(FakeII):
                def upload(self, code, channel=1):
                    response = super().upload(code, channel)
                    return IIResponse(response.code, response.channel, response.payload, b"x" * 10_000)

            supervisor = Supervisor(store, spool, ii_factory=LargeFakeII)
            try:
                supervisor.start()
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    status = supervisor.status()
                    machine = status["machines"]["ii-1"]
                    if (status["spool"]["evicted_record_count"] > 0 and machine["last_success"]
                            or machine["state"] == "fault"):
                        break
                    time.sleep(0.02)
                self.assertGreater(status["spool"]["evicted_record_count"], 0)
                self.assertIsNotNone(machine["last_success"])
                self.assertEqual(machine["state"], "running")
                self.assertTrue(machine["worker_alive"])
                self.assertTrue(status["running"])
                self.assertIsNone(status["acquisition_fault"])
            finally:
                supervisor.stop()
                spool.close()

    def test_current_channel_changes_mark_all_affected_reads_incomplete(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ConfigStore(Path(directory) / "config.json")
            spool = Spool(Path(directory) / "spool.sqlite3")
            supervisor = Supervisor(store, spool)
            machine = {"id": "ii-1", "model": "III"}
            fake = FakeII("/dev/serial/by-id/synthetic", changed=True)
            failures = supervisor._poll(machine, fake)
            self.assertTrue(any("channel changed" in item for item in failures))
            channel_records = [record for record in spool.list_records(limit=10)
                               if record["source"] in ("D01", "D02", "D03", "D04")]
            self.assertEqual(len(channel_records), 4)
            self.assertTrue(all(record["channel_id"] == 20 and record["values"]["quality"] == "incomplete"
                                for record in channel_records))
            self.assertEqual([code for code, _ in fake.calls],
                             ["D06", "D05", "D07", "D08", "D09", "D01", "D02", "D03", "D04", "D06"])
            spool.close()

    def test_failed_upload_creates_durable_error_record(self):
        with tempfile.TemporaryDirectory() as directory:
            spool = Spool(Path(directory) / "spool.sqlite3")
            supervisor = Supervisor(ConfigStore(Path(directory) / "config.json"), spool)
            failures = supervisor._poll({"id": "ii-1", "model": "III"},
                                        FakeII("/dev/serial/by-id/synthetic", fail_code="D07"))
            self.assertTrue(any(item.startswith("D07") for item in failures))
            self.assertTrue(any(record["record_type"] == "error" and record["source"] == "D07"
                                for record in spool.list_records(limit=10)))
            spool.close()


if __name__ == "__main__":
    unittest.main()
