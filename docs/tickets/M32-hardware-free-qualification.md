# M32 — Qualify the full simulated path and failure matrix

Status: needs-triage
Completion: unverified

**Depends on:** [M23](M23-ii-complete-inventory.md), [M25](M25-iv-complete-inventory.md), [M28](M28-mqtt-delivery.md), [M29](M29-postgres-delivery.md), [M30](M30-influx-delivery.md), [M31](M31-deploy-and-recover.md).

**Outcome:** A reproducible evidence report proves all in-scope simulated read families reach selected destinations or fail explicitly.

## Input and output contract

- **Input:** Fresh checkout, fake II/IV devices and fixture manifests, temporary spool/config, disposable MQTT/PostgreSQL/InfluxDB services, and injected failure schedule.
- **Output:** A reproducible source-to-spool-to-three-destination matrix keyed by record/scan ID, with expected and observed values, request traces, pending/ack state, evidence paths, and pass/blocker for every family and B01–B10 regression.
- **Failure output:** A skipped family, unexplained mismatch, missing destination result, or unbounded fault is an explicit release blocker, not a passing row. The report separates simulated results from hardware claims.
- **Boundary:** This qualifies the complete software path and documented deployment on test services; M33 alone confirms named machines and measured site limits.

## Fixed work order and evidence

1. Deliver `tests/fixtures/release-matrix.json` listing every family in the [shared execution contract](../specs/agent-execution-contract.md) with `case_id`, source request, expected record/scan body, and failure variant; add a single `scripts/qualify.py` entry point that creates a fresh temporary config/spool and exits nonzero unless every required case passes. It must use fake II/IV transports through the real supervisor and three disposable services, not direct destination-only calls.
2. Write `docs/evidence/M32-simulated-matrix.md` with one row per fixture × destination (MQTT, PostgreSQL, InfluxDB), keyed by `record_id` or `scan_id`, and columns expected body, observed body, source trace, spool state, remote evidence path, pass/fail. Add B01–B10 rows and fault rows for disconnect, timeout, redirect, malformed response, channel change, partial scan, oversize, full spool, destination outage, lost ack, kill/restart, repeated Start/Stop, no-destination collection, retention-limited backfill, and one-lane pending reroute. A skipped or missing cell is a failure.
3. Run `uv run python scripts/qualify.py` from the repository root. Compare complete JSON bodies after MQTT reassembly, PostgreSQL query, and Influx query. Verify request traces contain only II `UL` and IV allowlisted GETs. Record exact command, service versions, start/end UTC, and artifact paths. Mark the report `simulated`; release gate passes only if every manifest and audit row passes and M31's clean-host evidence exists. Otherwise list blocking case IDs.

## Scope and constraints

- Run II `D01`–`D09` and every IV read family, including ranges, exports, logs, and sparse `data/all`, through actual service configuration, spool, and all three disposable destinations (B10).
- Inject disconnect, timeout, redirect, malformed response, channel change, partial scan, oversized payload, full spool, destination outage, lost ack, process kill, restart, and repeated Start/Stop.
- Compare source fixture, record, scan state, MQTT payload, PostgreSQL row, and Influx query by stable identity. Capture byte traces proving no control request or screen fetch.

## Acceptance checks

- [ ] Matrix lists each source family, expected behavior, observed result, evidence path, and unresolved issue; no family is skipped by the test setup.
- [ ] All audit failures B01–B10 have a passing regression or explicit blocked decision.
- [ ] Partial inventories list missing items; committed records survive restart; full spool is a visible acquisition fault.
- [ ] The matrix includes destination-free collection, retention-limited backfill to each of the three destinations, pending-only reroute of one lane, and stable IDs under uncertain acknowledgment.
- [ ] Report labels evidence as simulated and does not claim hardware compatibility.

**Verification:** Run the matrix from a fresh checkout against fake devices and disposable MQTT/PostgreSQL/Influx services; inspect output, request traces, and persisted state.

## Comments

- 2026-09-28: ADR 0002 adds destination-free collection, retained-history backfill, and pending-only reroute to this matrix. Existing recovery checks do not establish those behaviors.
- 2026-09-28: Five checked-in recovery regressions now cover a killed SQLite writer, live backup/restore, fake destination outage plus lost ack and target change, a simulated SQLite full error, and inability to persist its fault row. The socket-free subset passes 23 tests. The full discovery run has one environment error: `test_api.py` cannot create a socket (`PermissionError`). Docker access is denied, so the disposable three-destination matrix and clean-host deployment have not run. No M32 acceptance check is complete yet.
