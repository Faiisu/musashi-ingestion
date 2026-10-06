"""SQLite spool with immutable records and target-specific acknowledgments."""

import hashlib
import json
import sqlite3
import threading
import uuid
from functools import wraps
from datetime import datetime, timezone
from pathlib import Path


class SpoolError(RuntimeError):
    pass


def make_record(machine_id: str, model: str, record_type: str, source: str, values: dict,
                *, channel_id=None, observed_at=None, evidence_type="simulated", record_id=None) -> dict:
    if not machine_id or not source or model not in ("III", "IV"):
        raise ValueError("machine_id, supported model and source required")
    observed_at = observed_at or datetime.now(timezone.utc).isoformat()
    timestamp = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    if timestamp.tzinfo is None or timestamp.utcoffset().total_seconds() != 0:
        raise ValueError("observed_at must be UTC")
    if evidence_type not in ("simulated", "documented", "hardware-verified"):
        raise ValueError("invalid evidence type")
    return {"version": 1, "record_id": record_id or str(uuid.uuid4()), "machine_id": machine_id,
            "model": model, "record_type": record_type, "source": source,
            "observed_at": observed_at, "channel_id": channel_id, "values": values,
            "evidence_type": evidence_type}


class Spool:
    def __init__(self, path: str | Path, *, max_record_bytes: int = 2_097_152,
                 max_spool_bytes: int = 1_073_741_824):
        if max_record_bytes <= 0 or max_spool_bytes <= max_record_bytes:
            raise ValueError("invalid spool limits")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_record_bytes = max_record_bytes
        self.max_spool_bytes = max_spool_bytes
        self._lock = threading.RLock()
        self.db = sqlite3.connect(self.path, timeout=30, isolation_level=None, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA busy_timeout=30000")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS records(record_id TEXT PRIMARY KEY, body BLOB NOT NULL,
          bytes INTEGER NOT NULL, committed_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS targets(target_id TEXT PRIMARY KEY, kind TEXT NOT NULL,
          config_hash TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS deliveries(record_id TEXT NOT NULL REFERENCES records(record_id),
          target_id TEXT NOT NULL REFERENCES targets(target_id), acknowledged_at TEXT,
          PRIMARY KEY(record_id,target_id));
        CREATE INDEX IF NOT EXISTS deliveries_pending ON deliveries(target_id,acknowledged_at);
        CREATE TABLE IF NOT EXISTS scans(scan_id TEXT PRIMARY KEY, machine_id TEXT NOT NULL,
          group_name TEXT NOT NULL, started_at TEXT NOT NULL, completed_at TEXT);
        CREATE TABLE IF NOT EXISTS scan_items(scan_id TEXT NOT NULL REFERENCES scans(scan_id),
          item_key TEXT NOT NULL, record_id TEXT REFERENCES records(record_id),
          PRIMARY KEY(scan_id,item_key));
        CREATE TABLE IF NOT EXISTS scan_expected(scan_id TEXT NOT NULL REFERENCES scans(scan_id),
          item_key TEXT NOT NULL, PRIMARY KEY(scan_id,item_key));
        CREATE TABLE IF NOT EXISTS scan_outcomes(scan_id TEXT NOT NULL REFERENCES scans(scan_id),
          item_key TEXT NOT NULL, outcome TEXT NOT NULL,
          PRIMARY KEY(scan_id,item_key));
        CREATE TABLE IF NOT EXISTS faults(id INTEGER PRIMARY KEY AUTOINCREMENT,
          occurred_at TEXT NOT NULL, detail TEXT NOT NULL, cleared_at TEXT);
        CREATE TABLE IF NOT EXISTS destination_lanes(lane_id TEXT PRIMARY KEY, target_id TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS reroute_audit(id INTEGER PRIMARY KEY AUTOINCREMENT,
          lane_id TEXT NOT NULL, old_target_id TEXT, new_target_id TEXT NOT NULL,
          moved_pending INTEGER NOT NULL, occurred_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS spool_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        PRAGMA user_version=2;
        """)
        self.db.execute("INSERT OR IGNORE INTO spool_meta VALUES('installation_id',?)", (str(uuid.uuid4()),))
        self.db.execute("INSERT OR IGNORE INTO spool_meta VALUES('last_point_ns','0')")
        self.db.execute("INSERT OR IGNORE INTO spool_meta VALUES('evicted_record_count','0')")
        self.db.execute("CREATE TEMP TABLE IF NOT EXISTS delivered_cleanup(record_id TEXT PRIMARY KEY)")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self._delete_fully_delivered_records()
            self.db.execute("COMMIT")
        except Exception:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    def _delete_fully_delivered_records(self, record_id=None):
        """Remove acknowledged record bodies without discarding scan outcomes."""
        self.db.execute("DELETE FROM delivered_cleanup")
        scope = "WHERE d.record_id=?" if record_id is not None else ""
        params = (record_id,) if record_id is not None else ()
        self.db.execute(f"""INSERT INTO delivered_cleanup
          SELECT d.record_id FROM deliveries d JOIN records r USING(record_id)
          {scope} GROUP BY d.record_id
          HAVING SUM(CASE WHEN d.acknowledged_at IS NULL THEN 1 ELSE 0 END)=0""", params)
        self.db.execute("""UPDATE scan_items SET record_id=NULL
          WHERE record_id IN (SELECT record_id FROM delivered_cleanup)""")
        self.db.execute("DELETE FROM deliveries WHERE record_id IN (SELECT record_id FROM delivered_cleanup)")
        self.db.execute("DELETE FROM records WHERE record_id IN (SELECT record_id FROM delivered_cleanup)")
        self.db.execute("DELETE FROM delivered_cleanup")

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()

    def close(self):
        self.db.close()

    def register_target(self, kind: str, settings: dict, *, lane_id=None, legacy_settings=None) -> str:
        if kind not in ("mqtt", "postgres", "influxdb"):
            raise ValueError("unsupported target kind")
        canonical = json.dumps({"kind": kind, "settings": settings}, sort_keys=True,
                               separators=(",", ":"), allow_nan=False)
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        target_id = f"{kind}:{digest}"
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.db.execute("INSERT OR IGNORE INTO targets VALUES(?,?,?,?)",
                            (target_id, kind, digest, self._now()))
            if lane_id is not None:
                row = self.db.execute("SELECT target_id FROM destination_lanes WHERE lane_id=?",
                                      (lane_id,)).fetchone()
                old_id = row[0] if row else None
                if old_id is None and legacy_settings is not None:
                    legacy = json.dumps({"kind": kind, "settings": legacy_settings}, sort_keys=True,
                                        separators=(",", ":"), allow_nan=False)
                    candidate = f"{kind}:{hashlib.sha256(legacy.encode()).hexdigest()}"
                    if self.db.execute("SELECT 1 FROM targets WHERE target_id=?", (candidate,)).fetchone():
                        old_id = candidate
                moved = 0
                if old_id is not None and old_id != target_id:
                    moved = self.db.execute("""SELECT count(*) FROM deliveries
                      WHERE target_id=? AND acknowledged_at IS NULL""", (old_id,)).fetchone()[0]
                    self.db.execute("""INSERT OR IGNORE INTO deliveries(record_id,target_id)
                      SELECT record_id, ? FROM deliveries
                      WHERE target_id=? AND acknowledged_at IS NULL""", (target_id, old_id))
                    self.db.execute("DELETE FROM deliveries WHERE target_id=? AND acknowledged_at IS NULL",
                                    (old_id,))
                elif old_id is None:
                    self.db.execute("""INSERT OR IGNORE INTO deliveries(record_id,target_id)
                      SELECT record_id, ? FROM records""", (target_id,))
                if old_id != target_id:
                    self.db.execute("INSERT INTO reroute_audit(lane_id,old_target_id,new_target_id,moved_pending,occurred_at) VALUES(?,?,?,?,?)",
                                    (lane_id, old_id, target_id, moved, self._now()))
                self.db.execute("INSERT OR REPLACE INTO destination_lanes VALUES(?,?)", (lane_id, target_id))
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise
        return target_id

    def _disk_bytes(self):
        return sum(p.stat().st_size for p in (self.path, Path(str(self.path) + "-wal"), Path(str(self.path) + "-shm")) if p.exists())

    def _fault(self, detail):
        self.db.execute("INSERT INTO faults(occurred_at,detail) VALUES(?,?)", (self._now(), detail))

    def _write_failure(self, detail, exc=None):
        # A full filesystem may have no room left for the fault row. The
        # supervisor still needs a SpoolError so acquisition stops visibly.
        try:
            self._fault(detail)
        except sqlite3.Error:
            pass
        raise SpoolError(detail) from exc

    def _prune_completed_scans(self):
        old_scans = [row[0] for row in self.db.execute("""SELECT scan_id FROM scans s
          WHERE completed_at IS NOT NULL AND scan_id NOT IN
            (SELECT scan_id FROM scans latest WHERE latest.machine_id=s.machine_id
             AND latest.completed_at IS NOT NULL ORDER BY latest.completed_at DESC LIMIT 1)""")]
        for scan_id in old_scans:
            for table in ("scan_outcomes", "scan_expected", "scan_items"):
                self.db.execute(f"DELETE FROM {table} WHERE scan_id=?", (scan_id,))
            self.db.execute("DELETE FROM scans WHERE scan_id=?", (scan_id,))

    def prune_acknowledged(self, keep_latest=100):
        """Reclaim delivered or unassigned history; never remove pending records."""
        if type(keep_latest) is not int or keep_latest < 0:
            raise ValueError("invalid retention count")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self._prune_completed_scans()
            self.db.execute("""DELETE FROM records WHERE record_id IN (
              SELECT r.record_id FROM records r
              WHERE NOT EXISTS (SELECT 1 FROM deliveries d WHERE d.record_id=r.record_id AND d.acknowledged_at IS NULL)
                AND NOT EXISTS (SELECT 1 FROM scan_items s WHERE s.record_id=r.record_id)
                AND r.record_id NOT IN (SELECT record_id FROM records ORDER BY rowid DESC LIMIT ?)
            )""", (keep_latest,))
            self.db.execute("DELETE FROM deliveries WHERE record_id NOT IN (SELECT record_id FROM records)")
            self.db.execute("COMMIT")
        except Exception:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise
        self.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.db.execute("VACUUM")

    def clear_all(self):
        """Remove local spool history and delivery state while preserving point identity."""
        self.db.execute("BEGIN IMMEDIATE")
        try:
            counts = dict(self.db.execute("""SELECT
              (SELECT count(*) FROM records) records,
              (SELECT count(*) FROM deliveries WHERE acknowledged_at IS NULL) pending_deliveries,
              (SELECT count(*) FROM scans) scans,
              (SELECT count(*) FROM faults) faults,
              (SELECT count(*) FROM targets) destination_identities""").fetchone())
            for table in ("scan_outcomes", "scan_expected", "scan_items", "scans",
                          "deliveries", "records", "faults", "destination_lanes", "reroute_audit", "targets"):
                self.db.execute(f"DELETE FROM {table}")
            self.db.execute("COMMIT")
        except sqlite3.Error as exc:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            self._write_failure(f"spool clear failed: {type(exc).__name__}", exc)

        try:
            self.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            self.db.execute("VACUUM")
            counts["storage_reclaimed"] = True
        except sqlite3.Error:
            # The deletion is already committed. SQLite can still reuse its free pages.
            counts["storage_reclaimed"] = False
        return counts

    def _make_room(self, margin):
        """Evict oldest committed records, including pending ones, under quota pressure."""
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self._prune_completed_scans()
            self.db.execute("COMMIT")
        except Exception:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise
        # WAL growth alone need not discard observations.
        self.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.db.execute("VACUUM")
        while self._disk_bytes() + margin > self.max_spool_bytes:
            excess = self._disk_bytes() + margin - self.max_spool_bytes
            oldest = []
            reclaimed = 0
            for row in self.db.execute("SELECT record_id,bytes FROM records ORDER BY rowid LIMIT 1000"):
                oldest.append((row[0],))
                reclaimed += row[1]
                if reclaimed >= excess:
                    break
            if not oldest:
                self._write_failure("spool quota exceeded: metadata and new record do not fit")
            self.db.execute("BEGIN IMMEDIATE")
            try:
                self.db.executemany("UPDATE scan_items SET record_id=NULL WHERE record_id=?", oldest)
                self.db.executemany("DELETE FROM deliveries WHERE record_id=?", oldest)
                self.db.executemany("DELETE FROM records WHERE record_id=?", oldest)
                self.db.execute("""UPDATE spool_meta SET value=CAST(value AS INTEGER)+?
                  WHERE key='evicted_record_count'""", (len(oldest),))
                self.db.execute("COMMIT")
            except Exception:
                if self.db.in_transaction:
                    self.db.execute("ROLLBACK")
                raise
            self.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            self.db.execute("VACUUM")

    def commit(self, record: dict, targets=()):
        required = ("record_id", "machine_id", "model", "record_type", "source", "observed_at", "values", "evidence_type")
        if (not isinstance(record, dict) or record.get("version") != 1
                or any(not record.get(key) for key in required if key != "values")
                or not isinstance(record.get("values"), dict)):
            raise ValueError("invalid record envelope")
        if "point_time_ns" in record or "installation_id" in record:
            raise ValueError("point identity is assigned by the spool")
        try:
            timestamp = datetime.fromisoformat(record["observed_at"].replace("Z", "+00:00"))
            if timestamp.tzinfo is None or timestamp.utcoffset().total_seconds() != 0:
                raise ValueError()
        except (TypeError, ValueError, AttributeError):
            raise ValueError("observed_at must be UTC") from None
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        delta = timestamp - epoch
        observed_ns = (delta.days * 86400 + delta.seconds) * 1_000_000_000 + delta.microseconds * 1000
        if not 0 <= observed_ns < 2**63 - 1:
            raise ValueError("observation time outside Influx nanosecond range")
        installation_id = self.db.execute("SELECT value FROM spool_meta WHERE key='installation_id'").fetchone()[0]
        candidate = dict(record, installation_id=installation_id, point_time_ns=2**63 - 1)
        try:
            body = json.dumps(candidate, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ValueError("record is not finite JSON") from exc
        if len(body) > self.max_record_bytes:
            self._write_failure("record exceeds byte limit")
        # Reserve room for the record, indexes, WAL pages, and checkpoint overhead.
        margin = max(65536, len(body) * 4)
        if self._disk_bytes() + margin > self.max_spool_bytes:
            try:
                self._make_room(margin)
            except sqlite3.Error as exc:
                self._write_failure("spool eviction failed", exc)
        if self._disk_bytes() + margin > self.max_spool_bytes:
            self._write_failure("spool quota exceeded")
        try:
            self.db.execute("BEGIN IMMEDIATE")
            last_point_ns = int(self.db.execute("SELECT value FROM spool_meta WHERE key='last_point_ns'").fetchone()[0])
            point_time_ns = max(observed_ns, last_point_ns + 1)
            if point_time_ns >= 2**63:
                raise SpoolError("point time outside Influx nanosecond range")
            committed = dict(record, installation_id=installation_id, point_time_ns=point_time_ns)
            body = json.dumps(committed, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.db.execute("INSERT INTO records VALUES(?,?,?,?)", (record["record_id"], body, len(body), self._now()))
            self.db.execute("UPDATE spool_meta SET value=? WHERE key='last_point_ns'", (str(point_time_ns),))
            for target_id in targets:
                self.db.execute("INSERT INTO deliveries(record_id,target_id) VALUES(?,?)", (record["record_id"], target_id))
            self.db.execute("UPDATE faults SET cleared_at=? WHERE cleared_at IS NULL", (self._now(),))
            self.db.execute("COMMIT")
        except Exception as exc:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            self._write_failure(f"spool commit failed: {type(exc).__name__}", exc)
        return record["record_id"]

    def list_records(self, limit=10):
        if type(limit) is not int or not 1 <= limit <= 10:
            raise ValueError("limit must be 1–10")
        return [json.loads(row[0]) for row in self.db.execute("SELECT body FROM records ORDER BY rowid DESC LIMIT ?", (limit,))]

    def pending(self, target_id: str, limit: int = 100):
        return [json.loads(row[0]) for row in self.db.execute("""SELECT r.body FROM records r JOIN deliveries d USING(record_id)
          WHERE d.target_id=? AND d.acknowledged_at IS NULL ORDER BY r.rowid LIMIT ?""", (target_id, limit))]

    def ack(self, target_id: str, record_id: str):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            updated = self.db.execute("UPDATE deliveries SET acknowledged_at=? WHERE target_id=? AND record_id=? AND acknowledged_at IS NULL",
                                      (self._now(), target_id, record_id)).rowcount
            if updated:
                self._delete_fully_delivered_records(record_id)
            self.db.execute("COMMIT")
        except Exception:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    def begin_scan(self, machine_id: str, group_name: str, scan_id=None, expected_items=()):
        scan_id = scan_id or str(uuid.uuid4())
        try:
            self.db.execute("BEGIN IMMEDIATE")
            self.db.execute("INSERT INTO scans VALUES(?,?,?,?,NULL)", (scan_id, machine_id, group_name, self._now()))
            for item_key in expected_items:
                self.db.execute("INSERT INTO scan_expected VALUES(?,?)", (scan_id, item_key))
            self.db.execute("COMMIT")
        except sqlite3.Error as exc:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            self._write_failure(f"scan start failed: {type(exc).__name__}", exc)
        return scan_id

    def record_scan_item(self, scan_id: str, item_key: str, record_id=None, outcome="ok"):
        if outcome not in ("ok", "failed", "unsupported"):
            raise ValueError("invalid scan outcome")
        try:
            self.db.execute("BEGIN IMMEDIATE")
            self.db.execute("INSERT OR REPLACE INTO scan_items VALUES(?,?,?)", (scan_id, item_key, record_id))
            self.db.execute("INSERT OR REPLACE INTO scan_outcomes VALUES(?,?,?)", (scan_id, item_key, outcome))
            self.db.execute("COMMIT")
        except sqlite3.Error as exc:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            self._write_failure(f"scan item write failed: {type(exc).__name__}", exc)

    def finish_scan(self, scan_id: str):
        expected = self.db.execute("SELECT count(*) FROM scan_expected WHERE scan_id=?", (scan_id,)).fetchone()[0]
        accounted = self.db.execute("""SELECT count(*) FROM scan_expected e JOIN scan_outcomes o
          ON e.scan_id=o.scan_id AND e.item_key=o.item_key WHERE e.scan_id=?""", (scan_id,)).fetchone()[0]
        failed = self.db.execute("SELECT count(*) FROM scan_outcomes WHERE scan_id=? AND outcome='failed'", (scan_id,)).fetchone()[0]
        if expected == 0 or accounted != expected or failed:
            raise SpoolError("scan incomplete or has failed items")
        self.db.execute("UPDATE scans SET completed_at=? WHERE scan_id=?", (self._now(), scan_id))

    def incomplete_scans(self):
        return [dict(row) for row in self.db.execute("SELECT * FROM scans WHERE completed_at IS NULL")]

    def scan_items(self, scan_id: str):
        return [dict(row) for row in self.db.execute("""SELECT e.item_key,i.record_id,o.outcome
          FROM scan_expected e LEFT JOIN scan_items i USING(scan_id,item_key)
          LEFT JOIN scan_outcomes o USING(scan_id,item_key)
          WHERE e.scan_id=? ORDER BY e.item_key""", (scan_id,))]

    def scan_snapshot(self, scan_id: str):
        row = self.db.execute("SELECT * FROM scans WHERE scan_id=?", (scan_id,)).fetchone()
        if row is None:
            raise KeyError(scan_id)
        return dict(row) | {"items": self.scan_items(scan_id)}

    def list_scans(self, limit=10):
        if type(limit) is not int or not 1 <= limit <= 10:
            raise ValueError("limit must be 1–10")
        ids = [row[0] for row in self.db.execute("SELECT scan_id FROM scans ORDER BY started_at DESC LIMIT ?", (limit,))]
        return [self.scan_snapshot(scan_id) for scan_id in ids]

    def stats(self):
        row = self.db.execute("""SELECT (SELECT count(*) FROM records) records,
          (SELECT count(*) FROM deliveries WHERE acknowledged_at IS NULL) pending,
          (SELECT min(r.committed_at) FROM records r JOIN deliveries d USING(record_id)
           WHERE d.acknowledged_at IS NULL) oldest_pending_at,
          (SELECT count(*) FROM scans WHERE completed_at IS NULL) incomplete_scans,
          (SELECT max(started_at) FROM scans) last_scan_at,
          (SELECT detail FROM faults WHERE cleared_at IS NULL ORDER BY id DESC LIMIT 1) fault,
          (SELECT CAST(value AS INTEGER) FROM spool_meta WHERE key='evicted_record_count') evicted_record_count""").fetchone()
        return dict(row) | {"disk_bytes": self._disk_bytes(), "wal_bytes": Path(str(self.path) + "-wal").stat().st_size if Path(str(self.path) + "-wal").exists() else 0}


def _serialized(method):
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return wrapper


for _name in ("close", "register_target", "commit", "list_records", "pending", "ack",
              "begin_scan", "record_scan_item", "finish_scan", "incomplete_scans", "scan_items", "stats",
              "prune_acknowledged", "clear_all", "scan_snapshot", "list_scans"):
    setattr(Spool, _name, _serialized(getattr(Spool, _name)))
