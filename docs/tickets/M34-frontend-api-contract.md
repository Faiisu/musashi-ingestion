# M34 — Expose the operator UI API contract

Status: needs-triage
Completion: unverified

**Depends on:** [M21](M21-secure-configuration.md), [M26](M26-spool-recovery-and-identity.md), [M27](M27-multi-machine-scheduling.md).

**Outcome:** A browser UI can read operational state, edit configuration, test saved connections, and control acquisition through one stable, authenticated API without inventing state or exposing secrets.

## Input and output contract

- **Input:** The version 1 configuration, runtime and spool state, saved machine/destination IDs, and an operator bearer token. M21 owns configuration validation and connection-test behavior; M26 and M27 own retained-history and per-worker state.
- **Output:** JSON responses below from the management server. They describe the full response fields the UI relies on; additional fields may be present. All `/api/*` routes require `Authorization: Bearer <token>` and return `Cache-Control: no-store`. `GET /health` stays unauthenticated and contains no topology.
- **Failure output:** Missing/invalid token returns 401; unknown route returns 404; malformed request returns 400; invalid configuration or test target returns 422; stale revision or live-worker edit returns 409. A connection failure has HTTP 200 and `ok: false`, as defined by M21. Server failures must not include secret values or raw device responses.
- **Boundary:** This ticket owns the browser-facing API shape and serving boundary. M35 owns rendering and interaction. It does not add device requests, destination writes, or a new credential store.

## Required routes and UI use

| Route | Required response or request | UI use and current state |
| --- | --- | --- |
| `GET /health` | `{process, acquisition, fault}` | Process indicator; implemented. This is not a substitute for protected status. |
| `GET /api/config` | Version 1 document with `revision`, `machines[]`, `destinations[]`, redacted `secret_ref` | Edit forms; implemented in part, with M21 acceptance open. |
| `PUT /api/config` | Send the full document with its last-read integer `revision`; success returns redacted saved document with new revision | Save while stopped; 409 requires reloading before retry, 422 returns field-keyed `errors`; implemented in part. |
| `POST /api/connection-test` | Send `{kind: "machine" | "destination", id: <saved ID>}`; receive `{ok, kind, id}` and an allowlisted `error` when `ok` is false | Test only a saved entry after Save; specified by M21, not implemented yet. |
| `GET /api/status` | `running`, `acquisition_fault`, `machines` and `destinations` keyed by ID, plus `spool` | Overview and per-item health; implemented in part. M27 must expose per-machine attempt/success, lag, skips, fault, liveness; the shared contract also requires per-lane pending/age, scan gaps, retained-history boundary/prune count, and disk/WAL size. |
| `POST /api/control/start`, `POST /api/control/stop` | JSON status body with the same fields as `GET /api/status` | Explicit operator action; implemented in part. The UI re-reads status after each result and never treats HTTP 200 alone as proof that every worker is healthy/stopped. |
| `GET /api/records`, `GET /api/scans` | `{records: [...]}` and `{scans: [...]}` respectively, newest first, at most 10 entries | Recent observations and inventory coverage; implemented. These are recent views, not complete history exports. |

The target `GET /api/status` body retains the existing top-level keys and adds these stable UI fields. A timestamp is an RFC 3339 UTC string or `null`; a fault is a safe string or `null`. Counts are nonnegative integers. A missing configured machine or destination must not silently disappear from the response.

| Location | Required fields and meaning |
| --- | --- |
| `machines[<configured machine ID>]` | `state`, `worker_alive`, `last_attempt`, `last_success`, `poll_lag_seconds`, `skipped_polls`, `error`. An unstarted worker uses `state: "stopped"`, false, null timestamps/error, and zero lag/skips. |
| `destinations[<configured destination ID>]` | `state`, `worker_alive`, `last_success`, `error`, `pending_count`, `oldest_pending_at`. The public key is the configured ID, not an internal target hash. A destination with no pending record has count zero and null oldest time. |
| `spool` | Existing `records`, `pending`, `oldest_pending_at`, `incomplete_scans`, `last_scan_at`, `disk_bytes`, `wal_bytes`, `fault`; add `oldest_retained_at` and `pruned_record_count` for M26's backfill boundary. Empty spool uses zero counts/bytes and null timestamps/fault. |
| `running`, `acquisition_fault` | `running` is true while acquisition is enabled and at least one machine worker is alive; `acquisition_fault` is a safe string or null. Individual worker faults remain visible even when another machine continues. |

`GET /api/scans` retains `scan_id`, `machine_id`, `group_name`, `started_at`, `completed_at`, and `items[]` with `item_key`, `record_id`, and `outcome`; null outcome means missing. The UI derives complete/partial from `completed_at` and item outcomes. `GET /api/records` retains the version 1 envelope in the [shared contract](../specs/agent-execution-contract.md). These status additions are proposed until M26/M27 and this ticket record evidence.

## Fixed work order and evidence

1. Reconcile the required status fields with M26/M27 and the [shared execution contract](../specs/agent-execution-contract.md). Keep machine and destination IDs stable across config, status, records, and scans. Define empty-state values for no machines, no destinations, and no scans. Ensure incomplete scans expose missing item keys and that `acquisition_fault` remains visible when reads stop.
2. Complete the M21 connection-test route and error vocabulary before the UI enables its Test action. Permit saved IDs only, use the M21 two-second deadline, and return no raw response or secret. Confirm that Start/Stop and connection tests use only their fixed routes.
3. Serve the UI bundle from the same loopback-first management origin as `/api/*`, with no cross-origin API access required. Keep the bearer token in browser memory only: the operator enters it for the session, and a reload requires entry again. Do not place it in URL, web storage, cookies, HTML, logs, or build assets. The browser sends it only to the same origin. Deployment outside loopback requires a protected network, TLS termination, and deployment evidence; do not widen the default bind address.
4. Publish a checked request/response contract from the implemented API, including 401, 409, 422, connection failure, empty state, and stopped/running/fault status examples. Link it from M35 instead of copying a divergent schema. Record the final contract and evidence in this ticket.

## Acceptance checks

- [ ] An authenticated browser can call every required route from the same origin; anonymous `/api/*` calls receive 401, and health reveals no machine or destination topology.
- [ ] Config save returns a redacted incremented revision; stale/live-worker saves return 409 without changing data, and 422 errors identify fields for the form.
- [ ] Saved machine and destination tests return bounded success or named failure without a secret, arbitrary path, device command, or destination write.
- [ ] Status and recent-data responses expose IDs, worker and acquisition faults, scan gaps, pending/retention boundary, and empty states required by the UI; no stale observation is presented as current data.
- [ ] UI assets and API work on the same restricted origin; token handling and deployment evidence show no credential in persistent browser storage, URLs, responses, or static assets.

**Verification:** Exercise the route table against a local service with fake devices and disposable destinations. Capture representative response bodies and error codes, inspect browser network/storage state, and record paths to evidence here. This is software evidence, not hardware acceptance.

## Comments

- 2026-09-28: Initial console uses the current config/status/records/scans/control routes on one origin. Authenticated smoke checks returned 200 for config/status/records/scans and anonymous status returned 401 over the deployed HTTPS proxy. `POST /api/connection-test` and several M26/M27 status fields are still absent; full contract acceptance remains open.
