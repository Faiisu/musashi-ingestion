"""PostgreSQL delivery of immutable complete record envelopes.

Apply ``MIGRATION_001`` with a database migration runner before delivery.
The injected connection follows DB-API 2.0 and transaction semantics.
"""

import json


MIGRATION_001 = """
CREATE TABLE IF NOT EXISTS musashi_records (
    record_id text PRIMARY KEY,
    machine_id text NOT NULL,
    model text NOT NULL,
    record_type text NOT NULL,
    source text NOT NULL,
    channel_id text,
    observed_at timestamptz NOT NULL,
    body jsonb NOT NULL
);
CREATE INDEX IF NOT EXISTS musashi_records_lookup
    ON musashi_records(machine_id, record_type, source, channel_id, observed_at);
CREATE TABLE IF NOT EXISTS musashi_scans (
    scan_id text PRIMARY KEY, machine_id text NOT NULL, group_name text NOT NULL,
    started_at timestamptz NOT NULL, completed_at timestamptz
);
CREATE TABLE IF NOT EXISTS musashi_scan_items (
    scan_id text NOT NULL REFERENCES musashi_scans(scan_id),
    item_key text NOT NULL, record_id text REFERENCES musashi_records(record_id),
    outcome text, PRIMARY KEY(scan_id, item_key)
);
"""


class PostgresDestination:
    def __init__(self, connection):
        self.connection = connection

    def send(self, record: dict) -> None:
        body = json.dumps(record, ensure_ascii=False, sort_keys=True, allow_nan=False)
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("""INSERT INTO musashi_records
                    (record_id,machine_id,model,record_type,source,channel_id,observed_at,body)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                    ON CONFLICT (record_id) DO NOTHING""",
                    (record["record_id"], record["machine_id"], record["model"],
                     record["record_type"], record["source"], record.get("channel_id"),
                     record["observed_at"], body))
                if record["record_type"] == "scan":
                    scan = record["values"]["value"]
                    cursor.execute("""INSERT INTO musashi_scans
                        (scan_id,machine_id,group_name,started_at,completed_at)
                        VALUES (%s,%s,%s,%s,%s)
                        ON CONFLICT (scan_id) DO UPDATE SET
                          completed_at=COALESCE(musashi_scans.completed_at,EXCLUDED.completed_at)""",
                        (scan["scan_id"], scan["machine_id"], scan["group_name"],
                         scan["started_at"], scan["completed_at"]))
                    for item in scan["items"]:
                        cursor.execute("""INSERT INTO musashi_scan_items
                            (scan_id,item_key,record_id,outcome) VALUES (%s,%s,%s,%s)
                            ON CONFLICT (scan_id,item_key) DO UPDATE SET
                            record_id=EXCLUDED.record_id,outcome=EXCLUDED.outcome""",
                            (scan["scan_id"], item["item_key"], item["record_id"], item["outcome"]))
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def close(self) -> None:
        self.connection.close()
