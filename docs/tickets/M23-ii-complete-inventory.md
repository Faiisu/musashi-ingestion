# M23 — Complete and account for Model II channel inventories

Status: needs-triage
Completion: unverified

**Depends on:** [M22](M22-ii-live-reads.md), [M26](M26-spool-recovery-and-identity.md).

**Outcome:** An operator can see whether all supported II channels and `D01`–`D04` settings were read, which items failed, and when the scan is fresh.

## Input and output contract

- **Input:** An evidenced supported-channel count, M18's four channel upload contracts, a scan ID, refresh policy, and a serialized request lane shared with status polling.
- **Output:** An expected-item set of `(channel, D01–D04)` reads, per-item record ID or explicit unsupported result, timestamps, counts, and a complete or partial scan snapshot committed to the spool.
- **Failure output:** Missing response, timeout, disconnect, or skipped read names its exact item and leaves the scan partial; a device-confirmed unsupported item remains visible within a complete scan. Restart retains the prior partial snapshot.
- **Boundary:** This owns the II inventory plan and coverage; M22 owns single reads, M26 owns durable scan transactions, and M27 owns fair scheduling.

## Fixed work order and evidence

1. Use configured, evidenced `channel_count = N`. At Start create one scan with exactly `4 × N` expected keys, in order `D01:1` through `D04:1`, then channel 2, and so on. Perform one `UL` request per inventory work unit through M22's serialized lane. A completed successful item stores its record ID; a controller rejection stores `unsupported`; timeout, disconnect, malformed frame, or quota failure stores `failed` or remains missing and keeps the scan partial.
2. After the last key, set `completed_at` only if all outcomes are `ok` or `unsupported`; emit the full scan snapshot. On Stop/crash preserve the partial scan and emit its partial snapshot when writes are possible. On next Start begin a new scan ID from the first key; retain the previous partial scan as evidence. Refresh begins after `inventory_interval_seconds` measured from the preceding scan start. Do not infer count from a `D06` channel value.
3. Evidence cases are N=1 (4 expected), N=100 (400 expected), one unsupported D04, one missing D02, failed first request, Stop/restart at item 2, and a slow request during a due status poll. Assert expected key set, outcomes/counts, scan state, snapshot body, request ordering, and zero serial overlap.

## Scope and constraints

- Start an inventory promptly after Start, then refresh by the configured policy. Determine supported channel range from documented/device evidence; never assume the maximum is present.
- Read channel work in bounded units, yielding to status polls. Record expected, succeeded, explicitly unsupported, failed, and skipped items with scan ID and start/end times. A scan is complete only when all expected items have `ok` or explicit `unsupported` results.
- A disconnect or restart leaves an incomplete scan visible. Never infer full completion from the number of returned rows alone.

## Acceptance checks

- [ ] Fake 1-channel and 100-channel devices produce correct expected/completed counts for all four channel uploads.
- [ ] A missing item names its channel/upload and makes the scan partial; an unavailable item is distinct from a transport failure.
- [ ] A scan with only `ok` and explicit `unsupported` items is complete while still listing unsupported items; failed or skipped items keep it partial.
- [ ] Status polling continues between bounded inventory units; no overlapping serial request occurs.
- [ ] Restart cannot turn a partial scan into a complete one.

**Verification:** Run deterministic fake-clock and fake-serial sweeps with slow, missing, and changed-channel cases.

## Comments

- 2026-09-28: SQLite scan expected/item outcomes and bounded II channel plan exist. One-channel synthetic scan was exercised; 100-channel, slow/missing, and restart sweep evidence remains open. Synthetic checks do not establish hardware acceptance.
