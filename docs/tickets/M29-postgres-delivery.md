# M29 — Deliver queryable complete records and scan state to PostgreSQL

Status: needs-triage
Completion: unverified

**Depends on:** [M26](M26-spool-recovery-and-identity.md), [M27](M27-multi-machine-scheduling.md).

**Outcome:** A consumer can query full read-only data and distinguish complete from partial inventories after replay and restart.

## Input and output contract

- **Input:** Pending records and scan snapshots for one PostgreSQL destination ID, a secret-file reference, and versioned database migrations.
- **Output:** Transactional immutable rows containing the full envelope and raw safe data, plus queryable expected scan items, outcomes, and complete/partial state; a machine with no scan is queryable as not started. Successful commit acknowledges only this destination's assignments.
- **Failure output:** Invalid/oversized data, interrupted transaction, or outage leaves uncommitted assignments pending without partial acknowledgment; replay of a confirmed `record_id` remains one logical row.
- **Boundary:** PostgreSQL is a projection of spool data. The collector and spool own observations and scan truth; M26 owns backfill/reroute, and this ticket owns schema, queries, and remote commit behavior.

## Fixed work order and evidence

1. Keep versioned migration `MIGRATION_001` in `destinations/postgres.py` for `musashi_records(record_id PRIMARY KEY, machine_id, model, record_type, source, channel_id, observed_at, body jsonb)`, `musashi_scans(scan_id PRIMARY KEY, machine_id, group_name, started_at, completed_at)`, and `musashi_scan_items(scan_id,item_key PRIMARY KEY,record_id,outcome)`. Add an index for machine/type/source/channel/time. Store the complete spool JSON unchanged in `body`; no source family gets a special lossy projection.
2. For one batch of at most 100 pending records, insert the records and scan projections in one database transaction. Replaying an identical `record_id` is a no-op; replaying the same ID with a different JSON body is an explicit conflict and stays pending. Commit first, then acknowledge each matching spool assignment. On transaction interruption, roll back and leave the whole batch pending. A scan snapshot upserts expected item rows and outcomes; later partial snapshot cannot erase a completed scan or a confirmed `ok`/`unsupported` item.
3. Add `docs/reference/postgres-queries.sql` with three executable queries: latest scan and missing/failed items for a machine, complete versus partial versus not-started state for every configured machine, and records by machine/type/source/time. `not-started` comes from the supplied configured machine list joined against scans; no fabricated scan row. The queries return explicit column names and stable ordering.
4. Evidence against a disposable PostgreSQL instance includes all shared families, nested/raw/TSV equality, complete and partial scans plus not-started machine, identical and conflicting replay, interrupted transaction, large accepted record, outage, backfill, and endpoint reroute with MQTT/Influx lanes unaffected. Record query output and spool ack state by ID.

## Scope and constraints

- Create versioned migrations for immutable record envelopes and scan/item completion, with indexes for machine, type, source, channel/recipe, and time (B09).
- Store full typed JSON and raw JSON/TSV safely or reject it before acknowledgment. Use unique record ID and replay-safe insert semantics.
- Commit bounded batches transactionally and acknowledge spool rows only after commit. Keep credentials/TLS settings outside logs and response bodies.

## Acceptance checks

- [ ] Fixture matrix for II and IV is queryable with source, units, identity, raw safe data, and quality intact.
- [ ] SQL queries distinguish complete, partial, and not-started scans and list missing items.
- [ ] Replay of an accepted record yields one immutable row; interrupted batch leaves uncommitted rows pending.
- [ ] Database outage leaves this target pending while MQTT/Influx delivery can proceed.
- [ ] A new database receives records still present in the spool within the visible window; fully delivered records have already been deleted. Changing its endpoint reroutes only its pending rows and preserves other lanes' assignments.

**Verification:** Run migrations and queries against a disposable PostgreSQL instance, including replay, large record, outage, and transaction interruption.

## Comments

- 2026-09-28: PostgreSQL migration and record/scan writes exist. Disposable PostgreSQL query/replay/outage checks remain open. Synthetic checks do not establish hardware acceptance.
- 2026-09-28: A temporary PostgreSQL 16 service accepted the migration, nested JSON, and a complete scan with `ok` and `unsupported` items. Queries returned the original data and scan outcomes; the spool acknowledged both records. Replay interruption, outage, and large-record checks remain open. This was an ad hoc integration run, not the complete M32 matrix.
