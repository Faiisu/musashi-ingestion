# M27 — Run independent machine schedules and fault states

Status: needs-triage
Completion: unverified

**Depends on:** [M21](M21-secure-configuration.md), [M22](M22-ii-live-reads.md), [M24](M24-iv-live-reads.md), [M26](M26-spool-recovery-and-identity.md).

**Outcome:** Two configured machines can poll at their own rates while inventory and delivery continue without one failure masking another.

## Input and output contract

- **Input:** Validated per-machine status and inventory intervals, bounded device reads, one request lane per machine, and acquisition Start/Stop signals.
- **Output:** Independent observation streams and inventory progress, with per-machine last attempt/success, lag, skipped-cycle count, worker liveness, and fault state visible through the API.
- **Failure output:** A slow or dead machine creates bounded lag/skips and a visible fault for that machine; a full spool stops new collection visibly. A destination outage remains a forwarder fault and does not fabricate observations.
- **Boundary:** Scheduling coordinates collectors and spool writes; it does not parse device responses, decide retention, or implement MQTT/PostgreSQL/Influx protocols.

## Fixed work order and evidence

1. In `runtime/supervisor.py`, maintain one worker and one serialized request lane per machine. Set the first status deadline and first inventory start to the Start instant. After a status cycle, advance the monotonic deadline by whole intervals until it is in the future; count each passed deadline as skipped and never synthesize its observation. Run at most one inventory request between two status opportunities. Refresh inventory from the preceding scan's start time.
2. Define API status per machine as `state`, `worker_alive`, `last_attempt`, `last_success`, `poll_lag_seconds`, `skipped_polls`, `error`, `scan_id`, `scan_state`, and `missing_items`; per lane as `state`, `worker_alive`, `pending_count`, `oldest_pending_age_seconds`, `last_success`, and `error`. Global acquisition fault is true on a spool fault or dead collector that was expected to run. Start is idempotent while running; Stop is idempotent while stopped and has the M26 ten-second bound.
3. Evidence uses an injected monotonic clock and fake II/IV adapters at 1 s and 3 s intervals. Cases: first scan begins at Start; a 1-second poll started at t=0 and completed at t=2.5 reports two skipped deadlines and schedules the next at t=3; slow IV leaves II progressing; one failed inventory request leaves partial scan; no destination still collects; one destination outage leaves other lanes and collectors progressing; repeated Start/Stop yields one worker per machine; and spool full sets global fault. Compare API fields with actual worker liveness and spool rows.

## Scope and constraints

- Use one serial request lane per II and one request lane per IV. Schedule with a monotonic clock; skip rather than overlap missed cycles. Bound work per inventory slice and report poll lag.
- Run first inventory promptly after Start instead of waiting a full refresh interval (B08). Repeated Start/Stop must be idempotent. Stop ends new reads and leaves committed delivery to bounded draining.
- Track thread/process liveness, last attempt/success, errors, skipped polls, per-source coverage, and global acquisition fault. A dead worker cannot report `running` solely from a stale boolean.

## Acceptance checks

- [ ] Fake II at 1 second and IV at a different interval both make progress during inventories, without concurrent requests to either machine.
- [ ] Slow/hung source produces bounded lag and explicit skipped cycles; no synthetic catch-up observations are emitted.
- [ ] Full spool stops all new collection with a visible global fault; a single fatal device worker is visible and does not stop healthy peers.
- [ ] Restart and repeated Start/Stop create no duplicate worker or duplicate observation.
- [ ] Collector and spool continue without a configured forwarder; a destination outage appears in its lane and cannot stall healthy machine reads before protected spool capacity is exhausted.

**Verification:** Use fake clocks/adapters and injected failures; compare status API with actual worker liveness and spool state.

## Comments

- 2026-09-28: Independent machine threads, first inventory, skip count, and status exist. Fake-clock multi-machine lag, hung-source isolation, and repeated Start/Stop checks remain open. Synthetic checks do not establish hardware acceptance.
