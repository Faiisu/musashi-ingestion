# Destination delivery test cases

Use this procedure to verify normal delivery, destination outage handling, and backlog recovery for PostgreSQL, InfluxDB, and an MQTT broker. Run the complete procedure once per destination against disposable services and a temporary application data directory. Use the device simulators and synthetic records for repeatable tests; use a physical machine only with site authorization.

These are integration test cases, not a claim that every case has passed. Record evidence for each run. The current implementation and the shared [execution contract](../specs/agent-execution-contract.md) define runtime behavior. The spool is a delivery buffer: records assigned to a destination stay local until confirmation or quota eviction, and records assigned to several destinations remain until every lane confirms unless evicted first. At the spool quota, the oldest committed records are evicted, including pending assignments, so acquisition continues. Status reports `evicted_record_count`; evicted pending records cannot be recovered from this spool.

## Test setup

For each destination under test:

1. Start a disposable PostgreSQL instance, InfluxDB instance, or MQTT broker. Use a fresh bucket/database/topic namespace so unrelated data cannot affect counts.
2. Configure one test machine using a simulator and one destination lane pointing at that service. For an isolated count, do not configure other destinations. Use a fresh temporary spool and make sure its quota can hold the full planned outage backlog.
3. Prepare a deterministic fixture set with unique `record_id` values and known complete record bodies. Include more than one record, at least two source families, and timestamps with UTC offsets represented as `Z` or `+00:00`. Keep the fixture manifest as the expected source of truth.
4. Start the destination and confirm it is ready using its native health check. Start the application, start acquisition, and confirm `GET /health` remains healthy and the authenticated operator status reports the machine and destination workers.
5. Capture the fixture IDs, full expected bodies, source timestamps, destination name, application build, start/end time in UTC, and a fresh-spool baseline. Never put destination credentials in test evidence.

For each case, mark **PASS** only when every expected result and the evidence item are present. A skipped check is not a pass.

## DDT-01 — Normal delivery

**Run separately for:** PostgreSQL, InfluxDB, and MQTT.

**Steps**

1. Confirm the destination is online and its namespace is empty.
2. Start the application and acquisition.
3. Wait for the fixture records to be read and committed.
4. Confirm the destination worker connects and reports a successful delivery.
5. Query or subscribe to the destination using the fixture `record_id` values.
6. Compare each delivered record with the fixture manifest, including nested values, source, channel, quality, raw data when present, and original `observed_at`.
7. Confirm the destination-specific timestamp behavior below.
8. Confirm the spool has no pending assignment for this destination after successful confirmation. With no other destination lanes and no unassigned records, the record bodies should be removed from the spool after acknowledgment.

**Expected results**

- The application stays running and reports no destination fault.
- Every fixture record reaches the destination exactly once as a logical record, with no missing IDs and a complete matching body.
- PostgreSQL: one `musashi_records` row per fixture `record_id`; `body` matches the complete envelope.
- InfluxDB: the expected `musashi_iii` or `musashi_iv` measurement is queryable; the `body` field reconstructs the complete envelope. Compare `observed_at` in the body with the source timestamp. `_time` is the spool point identity time and may be later by nanoseconds when observation times collide or move backward.
- MQTT: all chunks for each `record_id` arrive on the configured topic; reassembly by `index` yields the complete envelope and matches its `record_id`. Confirm QoS 1 and `retain=false`.
- Numeric values and units match the fixture; timestamps represent the same UTC instant as the source.

**Evidence**: fixture manifest, destination query/subscriber output, complete-body comparison result, worker/status snapshot, and spool pending count before/after.

## DDT-02 — Destination becomes unavailable

**Run separately for:** stop PostgreSQL, stop InfluxDB, stop the MQTT broker, or disconnect the test network path. Repeat the outage variant for each supported failure type that applies to the environment.

**Steps**

1. Start the application, destination, and acquisition. Deliver a baseline record and verify it remotely.
2. Stop the destination service or block the application-to-destination test network path.
3. Keep acquisition running and emit a known set of additional records during the outage. Record their IDs and expected bodies from the simulator/fixture trace.
4. Leave the destination unavailable for the planned test interval, keeping the expected backlog below the configured spool quota.
5. During the outage, confirm the application process and machine worker remain alive; check `GET /health` and authenticated status.
6. Confirm the destination lane reports a delivery fault or failed state, and the spool reports pending work for that lane.
7. Inspect the local spool read-only. Confirm every outage record is present and has an unacknowledged delivery assignment for the tested lane.
8. Emit another known record near the end of the outage. Confirm it is also committed locally and pending for the lane.
9. Record total spool records, pending deliveries, oldest pending time, disk bytes, and WAL bytes.

**Expected results**

- Destination failure does not crash the application or prevent device/simulator reads while spool capacity remains available.
- The application detects and surfaces delivery failure; it does not acknowledge unconfirmed records; quota eviction can remove them if the backlog fills the spool.
- All outage-period fixture IDs and bodies are present in local storage, and per-lane pending counts grow to match the captured input set.
- No claim of unlimited offline operation is made. If the configured quota is reached, acquisition continues by evicting the oldest committed records and their pending assignments. Verify that the eviction counter increases and new records remain accepted; evicted IDs are excluded from later backlog-delivery expectations.

**Evidence**: outage start/end timestamps, service/network fault action, health/status snapshots, fixture IDs, read-only spool query, pending counts, and destination worker error with secrets redacted.

## DDT-03 — Automatic reconnect and backlog delivery

**Run after DDT-02 for the same destination and spool.**

**Steps**

1. Preserve the outage record ID set and pending count from DDT-02.
2. Restart or reconnect the destination without restarting the application.
3. Confirm the application detects recovery and reconnects automatically. If the worker retries on a timer, wait through its configured retry interval and record elapsed time.
4. Keep acquisition running and emit additional identified records while backlog delivery is in progress.
5. Confirm outage records and new records both arrive at the destination. For each destination, query/subscribe by stable record IDs and compare complete bodies with the fixtures.
6. Wait until the tested lane has no pending deliveries. Record spool and remote counts, then compare the complete set of IDs generated during outage and recovery against the destination.
7. Confirm ordinary live delivery continues after the backlog drains by emitting one final identified record and verifying its arrival.

**Expected results**

- The application reconnects without a manual restart and resumes delivery for the destination lane.
- Pending records are sent in spool commit order; new machine records continue to be accepted while backlog delivery runs.
- The destination receives every captured outage and recovery ID with complete matching data. No logical record is missing or represented by multiple independent records.
- PostgreSQL replay of an identical `record_id` remains one row. Influx replay uses the same stored point identity. MQTT QoS 1 can redeliver a chunk if a PUBACK is uncertain; chunks must keep stable record/chunk identity, and consumers should deduplicate reassembled records by `record_id`. Do not treat an at-least-once retransmission as a second logical record.
- After the lane acknowledges all work, its pending count is zero. With no other assigned lanes, delivered record bodies are removed from the spool; with other lanes, they remain until those lanes also acknowledge.
- The application continues in normal live-delivery operation after the backlog is drained.

**Evidence**: before/after pending counts, ordered local pending IDs, remote ID list, full-body equality results, duplicate/replay check, worker recovery status, and final live-record query.

## Result record

Complete one row for each destination and outage variant:

| Case | Destination / outage variant | Fixture IDs | Expected count | Remote logical count | Pending before → after | Body/timestamp comparison | Evidence path | Result / notes |
| --- | --- | --- | ---: | ---: | --- | --- | --- | --- |
| DDT-01 |  |  |  |  |  |  |  |  |
| DDT-02 |  |  |  |  |  |  |  |  |
| DDT-03 |  |  |  |  |  |  |  |  |

For MQTT, also record received chunk count, expected chunk count, QoS, retain flag, and whether any retransmission was deduplicated by `record_id`. For InfluxDB, record measurement, field/body query result, and both `_time` and body `observed_at`. For PostgreSQL, record row count and body equality by primary key.
