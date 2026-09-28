# M26 — Make records, scans, and target identities durable

Status: needs-triage
Completion: unverified

**Depends on:** [M20](M20-first-durable-read.md), [M21](M21-secure-configuration.md).

**Outcome:** A crash preserves committed data; changing one destination moves only its pending work to the newly selected endpoint without changing other lanes or record IDs.

## Input and output contract

- **Input:** Validated observations and scan outcomes from collection, destination IDs and revisions, retention policy, quota, and remote confirmation events from forwarders.
- **Output:** Atomic durable record/scan writes, per-destination pending and acknowledged state, retained-history window and gaps, plus auditable pending-only reroute counts when one destination endpoint changes.
- **Failure output:** Oversize, quota, or SQLite write failure prevents a false commit and stops acquisition visibly; a crash preserves committed IDs and assignments. Uncertain remote confirmation keeps an item pending with its original record ID.
- **Boundary:** The spool owns persistence and assignment, without device I/O or destination protocols. It permits unassigned records, backfills retained history for a newly added destination, and atomically reroutes only unacknowledged work for the changed lane under [ADR 0002](../adr/0002-independent-collection-and-destination-rerouting.md).

## Fixed work order and evidence

1. In `pipeline/spool.py`, migrate the current SQLite schema without losing `records`, `scans`, `scan_expected`, `scan_outcomes`, or `deliveries`. Add stable configured lane ID, endpoint revision/identity, reroute audit, retained-history boundary and prune count. Commit a version 1 record, its point identity, and its currently selected lane assignments in one `BEGIN IMMEDIATE` transaction. A zero-destination commit creates no delivery rows. Duplicate `record_id` with different body is an error.
2. On registration of a new lane, assign every still-retained record in commit order exactly once. Re-registering an unchanged lane creates no new rows. On an endpoint change, require stopped workers, create the new identity, move only pending rows for that lane in one transaction, and record `{lane_id, old_endpoint, new_endpoint, pending_before, moved, acknowledged_untouched, occurred_at}`. Expose `ack(lane_id, endpoint_identity, record_id) -> bool`: return true and mark acknowledged only for a pending row on the current endpoint; return false without mutation for an old endpoint, unknown ID, or already acknowledged row. Another lane's pending/ack counts and every record ID remain unchanged.
3. Implement `retention_max_history_records` as specified by the [shared execution contract](../specs/agent-execution-contract.md). On quota pressure prune eligible oldest data before retrying once; pending rows and incomplete scans remain protected. If still over quota, return `SpoolError`, stop acquisition, and expose fault in memory even if SQLite cannot persist a fault row. Expose disk/WAL bytes, oldest retained timestamp, pruned count, and per-lane pending count/age. Stop joins collector and delivery workers for at most 10 seconds; unfinished delivery stays pending.
4. Evidence cases use a real temporary SQLite file: no-target commit then backfill; two lanes with mixed pending/ack then one reroute; late old ack; uncertain ack duplicate ID; retention=0 and retention=100; pending-protected full quota; crash before/after commit; interrupted reroute; checkpoint/WAL growth; and reopen of partial scan. Assert exact rows/counts/audit and API status before/after each case.

## Scope and constraints

- Version SQLite schema for immutable records, scan state/items, destination target identities, and per-target delivery state. Tie record and delivery-row insertion to one transaction.
- Enforce serialized byte size before commit and total spool quota with margin for the pending write and WAL. When full or disk write fails, stop new reads and expose a durable fault; a worker must not die while status says `running` (B03).
- Give each changed destination configuration a new endpoint identity, then atomically move only that configured destination's pending assignments to it. Do not move confirmed deliveries or another destination's work; preserve record IDs and an audit of counts. An in-flight old endpoint may receive a duplicate when its acknowledgment is uncertain (B04).
- Let collection commit with no destination. Apply documented retention to unassigned data; a newly added destination receives retained history and a visible earliest available point or gap.
- Make restart recovery and Stop drain behavior explicit; do not acknowledge a row before remote confirmation.

## Acceptance checks

- [ ] Kill/restart preserves record ID, partial scan coverage, target assignment, and pending acknowledgments.
- [ ] A record larger than the per-record or spool limit is rejected before commit; full spool stops acquisition with visible fault and no false healthy status.
- [ ] Changing one endpoint moves exactly that destination's pending rows to the new endpoint; confirmed rows and other lanes stay unchanged, record IDs remain stable, and the audit records before/after counts.
- [ ] With no destination, collection still commits; a destination added later receives only retained history and the backfill boundary is visible.
- [ ] WAL growth, pending age/count, scan age, and disk use are observable and bounded by a documented policy.
- [ ] An authenticated operator can clear all local spool history only after every machine and destination worker stops; pending deliveries are included, destination-side data is untouched, and installation/point identity is preserved.

**Verification:** Exercise real temporary SQLite files, process kill points, concurrent workers, full disk/quota simulation, retained-history backfill, and endpoint reconfiguration while an old forwarder has work in flight.

## Comments

- 2026-09-28: ADR 0002 changes the acceptance target: endpoint changes must reroute only pending work in that destination lane, and adding a destination must backfill retained history. Earlier old-target-isolation checks below are historical evidence for the previous contract; they do not verify this reroute.
- 2026-09-28: SQLite records, scan state, target identity, ack state, quota guard, and pruning exist. Kill-point, concurrent, WAL, full-disk, and target-change recovery matrix remains open. Synthetic checks do not establish hardware acceptance.
- 2026-09-28: Spool schema now persists one installation ID and assigns monotonic Influx point time in the record transaction. Automatic pruning retains pending rows and all incomplete scans; the retention rule is in the rebuild contract. Crash-point and WAL capacity checks remain open.
- 2026-09-28: Pruning now deletes scan coverage and old records in one SQLite transaction. An offline quota regression confirmed delivered history is pruned and pending rows instead cause a visible spool fault. The full kill-point and disk-full matrix remains open.
- 2026-09-28: `tests/test_recovery.py` killed a process with an open write transaction. On reopening the real SQLite file, the earlier committed record, pending target assignment, and partial scan survived; the uncommitted row did not. A simulated SQLite `max_page_count` full error rejected the write and left a visible fault. A changed target received no old pending row. These are selected crash points and a page-limit simulation, not process-kill coverage at every commit boundary or an actual full filesystem.
- 2026-09-28: The page-limit test exposed a recovery bug: a SQLite write error escaped as `OperationalError`, so the read loop could continue. Spool write failures now raise `SpoolError`, which the machine worker treats as a stopping fault. A second test injects failure while writing the fault row; the stopping error still propagates, but the fault cannot be durable when SQLite has no write space.
- 2026-09-29: Added the operator spool-clear path and tests for local-history removal, identity preservation, and session/CSRF protection. Verification has not been run; this acceptance check remains unverified.
