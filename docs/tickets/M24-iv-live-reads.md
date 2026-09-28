# M24 — Read Model IV status through an exact safe allowlist

Status: needs-triage
Completion: unverified

**Depends on:** [M19](M19-iv-read-contract.md), [M20](M20-first-durable-read.md), [M21](M21-secure-configuration.md).

**Outcome:** A configured IV machine yields all safe live-status observations while the HTTP client cannot operate the dispenser.

## Input and output contract

- **Input:** A validated IV host and port, poll interval, M19's exact status path catalog, and a per-device serialized HTTP lane with deadline and response-byte cap.
- **Output:** One observation or explicit unavailable result per documented status source, retaining source path, parsed values, safe raw response, UTC time, and quality in the spool.
- **Failure output:** Null, malformed JSON, timeout, redirect, oversized body, and transport failure remain distinguishable and bounded; no failed source is silently marked good or replaced with an older value.
- **Boundary:** This owns live IV status. M25 owns slower inventory families, M27 owns cross-machine scheduling, and M33 validates real-controller responses.

## Fixed work order and evidence

1. A live cycle requests the 16 `STATUS` entries in their `iv.py` order, once each, with GET and no redirect following. Construct paths with `path_for`; accept only HTTP 200. Enforce a 2-second request deadline and 2,097,152-byte raw body cap (replace the current 1 MiB default). Preserve JSON in `values.value`, UTF-8 raw text in `values.raw`, exact path in `source`, and `quality: "good"`; JSON `null` sets `quality: "unavailable"`.
2. On a non-200 response, malformed JSON, timeout, transport failure, or oversized body, create a source-specific error/fault and continue to the next allowlisted status path. Do not follow 3xx, issue a control GET, or reuse prior values. Limit concurrent requests to one per configured IV machine so the service stays within the device's documented three-client limit.
3. Evidence is a 16-row path/result table plus `null`, 302 redirect, 4xx, invalid JSON, exactly-at-limit, one-byte-over-limit, timeout, and slow-IV-with-II cases. Assert exact request method/path, response bytes, record quality or fault, and absence of a subsequent redirected request.

## Scope and constraints

- Build requests from typed allowlist entries only; reject redirects, POST, arbitrary paths, and every state-changing GET. Exclude `/v1/screen` (M19).
- Serialize per-device requests, enforce timeout/response-byte limits, and honor the three-client limit. Read every status group; distinguish JSON null, unavailable value, malformed body, and transport error.
- Preserve original safe response and parsed values with source path and UTC timestamp. A failed auxiliary status endpoint must affect completeness/quality rather than silently returning `good`.

## Acceptance checks

- [ ] Request traces contain exactly permitted paths and no control command, redirect follow, or screen fetch.
- [ ] All documented status families produce records or explicit per-source unavailability/fault.
- [ ] Timeout, oversized body, invalid JSON, and partial status responses stay bounded and visible.
- [ ] Reader and configuration both enforce the fixed 2,097,152-byte raw-response limit.
- [ ] A slow or failed IV read does not crash the service or affect a configured II machine.

**Verification:** Drive a fake IV HTTP server with full, partial, redirect, and fault responses. Hardware validation remains for M33.

## Comments

- 2026-09-28: IV status allowlist, byte/timeout bounds, and per-source durable error records exist. Full fake-server status family and fault matrix remain open. Synthetic checks do not establish hardware acceptance.
