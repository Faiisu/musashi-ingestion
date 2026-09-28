# M25 — Complete and account for every Model IV inventory family

Status: needs-triage
Completion: unverified

**Depends on:** [M24](M24-iv-live-reads.md), [M26](M26-spool-recovery-and-identity.md).

**Outcome:** An operator can tell exactly which IV common settings, ranges, recipes, channels, exports, logs, machine/time, and diagnostic results were collected.

## Input and output contract

- **Input:** Evidenced recipe/channel counts, M19's safe inventory catalog, configured size/deadline limits, scan ID, and a request lane shared with IV status polling.
- **Output:** An expected-item manifest for machine/time, common data and ranges, recipe/channel data and ranges, export, log, and diagnostic results; each item has a result, record ID when data exists, and a complete or partial scan snapshot.
- **Failure output:** Sparse `data/all` is reconciled against the mandatory per-ID reads; unresolved IDs, malformed range, timeout, oversized export/log, and skipped items remain visible and make the scan partial. Explicitly unsupported items remain visible without fabricating values.
- **Boundary:** This owns IV inventory coverage and fallback policy. M24 owns individual safe HTTP reads, M26 owns persistence, and M27 owns request fairness.

## Fixed work order and evidence

1. Build the expected set from the 23 fixed inventory paths returned by `inventory_requests()` plus configured recipe IDs `1..R` and channel IDs `1..C`, for `23 + R + C` keys. Keep exact paths as item keys. Request fixed paths first in their enumerated order, then recipes ascending, then channels ascending, one request per work unit. Preserve `data/all` and per-ID records separately: the per-ID reads are mandatory reconciliation, so a sparse `data/all` never shortens the expected set.
2. Accept a recipe/channel range only when integer `min`/`max` match configured count and begin at 0 or 1; the per-ID URL `k` must return payload `no = k - 1`. Sparse `data/all` is `ok` only when every omitted ID has a successful matching per-ID read; duplicate or extra IDs make the all-item `failed`. A missing per-ID result remains its own failed/missing item. Invalid range or any failed export/log creates its own failed item. Explicit controller rejection is `unsupported`; JSON `null` follows the shared unavailable rule. A partial scan remains partial after restart; next Start begins a new scan ID.
3. Evidence cases use R=1/C=1 (25 expected) and R=100/C=400 (523 expected), full and sparse all responses, wrong payload number, duplicate ID, invalid range, oversized export, malformed TSV, Stop/restart, and a due status poll. For each, assert exact expected path set and count, outcome per key, complete/partial snapshot, no forbidden request, and zero overlap.

## Scope and constraints

- Include every allowed read family from M19, including `/range` endpoints omitted by the previous implementation (B05). Start the first scan promptly and keep expensive exports/logs bounded by M17 limits.
- Treat `data/all` as an optimization only. Compare returned IDs with the expected range and reconcile through the mandatory bounded per-ID reads. Keep URL IDs separate from payload numbering.
- Track per-item success, explicit unsupported, failed, and skipped states; a scan is complete when every expected item has `ok` or `unsupported`, while failures and missing items leave it partial. Retain partial scans on restart and begin a new scan ID.

## Acceptance checks

- [ ] A full fake response produces complete counts across every configured family; partial `data/all` cannot be marked complete without accounted fallbacks.
- [ ] Missing IDs, malformed range data, and failed exports/logs appear in scan coverage and quality.
- [ ] A scan with only `ok` and explicit `unsupported` items is complete while still listing unsupported items; a missing, failed, or skipped item keeps it partial.
- [ ] 400-channel/100-recipe fake sweeps remain bounded and allow status reads between work units.
- [ ] No inventory request uses a forbidden endpoint or overlapping connection.

**Verification:** Run fake-server cases for complete, sparse, oversized, and failed inventories; assert source trace and coverage counts (B05).

## Comments

- 2026-09-28: IV inventory plan includes ranges, exports, diagnostics, and configured per-ID reads. Range/count and payload numbering checks exist; sparse/full 400-channel and 100-recipe fake sweeps remain open. Synthetic checks do not establish hardware acceptance.
