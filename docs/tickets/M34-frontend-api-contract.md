# M34 — Expose the operator UI API contract

Status: needs-triage
Completion: unverified

**Depends on:** [M21](M21-secure-configuration.md), [M26](M26-spool-recovery-and-identity.md), [M27](M27-multi-machine-scheduling.md).

**Outcome:** A browser UI can read operational state, edit configuration, test saved connections, and control acquisition through one stable, authenticated API without inventing state or exposing secrets.

## Input and output contract

- **Input:** The version 1 configuration, runtime and spool state, saved machine/destination IDs, and the shared local operator session defined in [M36](M36-session-auth-backend.md) and [ADR 0003](../adr/0003-shared-session-login-for-the-operator-console.md). M21 owns configuration validation and connection-test behavior; M26 and M27 own retained-history and per-worker state.
- **Output:** JSON responses below from the management server. They describe the full response fields the UI relies on; additional fields may be present. Protected `/api/*` routes require a valid session cookie and return `Cache-Control: no-store`; anonymous access to `POST /api/auth/login` and `GET /api/auth/session` is the explicit exception. The auth bootstrap routes are `POST /api/auth/login`, `POST /api/auth/logout`, and `GET /api/auth/session`. `GET /health` stays unauthenticated and contains no topology.
- **Failure output:** Missing/invalid session returns 401; invalid login returns a generic 401; cross-origin or missing/invalid CSRF token on a state-changing request returns 403; unknown route returns 404; malformed request returns 400; invalid configuration or test target returns 422; stale revision or live-worker edit returns 409. A connection failure has HTTP 200 and `ok: false`, as defined by M21. Server failures must not include secret values or raw device responses.
- **Boundary:** This ticket owns the browser-facing API shape and status/serving boundary, and records the auth wire contract implemented by M36. M35 owns operational page rendering; M37 owns browser login interaction. It does not add device requests, destination writes, external API-client authentication, or bearer-token compatibility.

## Browser authentication contract

- `POST /api/auth/login` accepts `{"username":"admin","password":"<configured password>"}`. On success it returns 200 with `{"authenticated":true,"csrf_token":"<opaque token>"}` and sets a cryptographically random, server-side session ID in an `HttpOnly; SameSite=Strict; Path=/` cookie. Set `Secure` when the trusted public origin uses HTTPS. Invalid credentials return the same generic 401 response and do not establish a session.
- `GET /api/auth/session` returns 200 with `{"authenticated":false}` when anonymous, or `{"authenticated":true,"csrf_token":"<opaque token>"}` for a valid session. Use `Cache-Control: no-store` on auth responses. A reloaded page may restore UI access from a still-valid cookie, but must not persist the password or CSRF token in browser storage.
- `POST /api/auth/logout` requires the session cookie and CSRF header, invalidates that session, clears the cookie, and returns 204. A service restart invalidates every session. Sessions expire after 8 hours without authenticated activity or 24 hours after creation, whichever occurs first.
- For all state-changing routes (including login/logout, config writes, connection tests, and Start/Stop), require a same-origin `Origin` and reject mismatched Host/Origin pairs. After login, require `X-CSRF-Token` matching the token returned by the auth response/session route. Check authorization first: an anonymous protected mutation returns 401; an authenticated mutation with invalid Origin/CSRF returns 403. By default, direct HTTP allows only `http://127.0.0.1:<published port>`. `MUSASHI_ALLOWED_ORIGINS` may add comma-separated exact origins; the explicit `*` setting allows any matching Host/Origin pair. The application remains HTTP; the deployer may terminate TLS at a reverse proxy and configure the exact HTTPS `MUSASHI_PUBLIC_ORIGIN`. Mark cookies Secure for HTTPS request origins. Never trust an untrusted forwarding header. The UI keeps the CSRF token in memory and sends it only to its same origin. Do not enable cross-origin credentialed API access.
- Browser credentials are `OPERATOR_USERNAME` and `OPERATOR_PASSWORD`, defaulting to `admin` and `00000000`; both can be supplied through the deployment's environment-secret mechanism. No forced password rotation, rate limit, response delay, or account lockout is included. The weak default is an explicitly accepted risk; deployment must keep the management interface behind a restricted network. No external API client or old bearer-token caller is supported by this contract.

## Required routes and UI use

| Route | Required response or request | UI use and current state |
| --- | --- | --- |
| `POST /api/auth/login` | `{username, password}`; success returns `{authenticated: true, csrf_token}` and sets session cookie | Sign-in; new contract, implementation pending. |
| `GET /api/auth/session` | `{authenticated: false}` or `{authenticated: true, csrf_token}` | Restore a valid browser session after reload; new contract, implementation pending. |
| `POST /api/auth/logout` | Requires session cookie and `X-CSRF-Token`; success returns 204 and clears the session | Explicit sign-out; new contract, implementation pending. |
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
| `machines[<configured machine ID>]` | `state`, `worker_alive`, `last_attempt`, `last_success`, `poll_lag_seconds`, `skipped_polls`, `error`, `scan_id`, `scan_state`, `missing_items`. An unstarted worker uses `state: "stopped"`, false, null timestamps/error/scan fields, zero lag/skips, and an empty `missing_items` array. |
| `destinations[<configured destination ID>]` | `state`, `worker_alive`, `last_success`, `error`, `pending_count`, `oldest_pending_at`, `oldest_pending_age_seconds`. The public key is the configured ID, not an internal target hash. A destination with no pending record has count zero and null oldest time/age. |
| `spool` | Existing `records`, `pending`, `oldest_pending_at`, `incomplete_scans`, `last_scan_at`, `disk_bytes`, `wal_bytes`, `fault`; add `oldest_retained_at` and `pruned_record_count` for M26's backfill boundary. Empty spool uses zero counts/bytes and null timestamps/fault. |
| `running`, `acquisition_fault` | `running` is true while acquisition is enabled and at least one machine worker is alive; `acquisition_fault` is a safe string or null. Individual worker faults remain visible even when another machine continues. |

`GET /api/scans` retains `scan_id`, `machine_id`, `group_name`, `started_at`, `completed_at`, and `items[]` with `item_key`, `record_id`, and `outcome`; null outcome means missing. The UI derives complete/partial from `completed_at` and item outcomes. `GET /api/records` retains the version 1 envelope in the [shared contract](../specs/agent-execution-contract.md). These status additions are proposed until M26/M27 and this ticket record evidence.

## Fixed work order and evidence

1. Reconcile the required status fields with M26/M27 and the [shared execution contract](../specs/agent-execution-contract.md). Keep machine and destination IDs stable across config, status, records, and scans. Define empty-state values for no machines, no destinations, and no scans. Ensure incomplete scans expose missing item keys and that `acquisition_fault` remains visible when reads stop.
2. Complete the M21 connection-test route and error vocabulary before the UI enables its Test action. Permit saved IDs only, use the M21 two-second deadline, and return no raw response or secret. Confirm that Start/Stop and connection tests use only their fixed routes.
3. Reconcile the auth route contract with M36's implementation and verify invalid credentials, logout, idle expiry, absolute expiry, restart, missing/invalid CSRF token, and cross-origin requests through the same-origin API. Do not accept bearer tokens as a fallback. Record any limits the test clock uses.
4. Serve the UI bundle from the same loopback-first management origin as `/api/*`, with no cross-origin API access required. Verify M36's `HttpOnly`, `SameSite=Strict`, and `Path=/` cookie plus `Secure` for trusted HTTPS origins. Do not put passwords or session IDs in URLs, web storage, HTML, logs, or build assets. Deployment outside loopback requires an explicitly restricted network, an exact origin allowlist, and deployment evidence.
5. Publish a checked request/response contract from the implemented API, including login/logout/session, 401/403/409/422, connection failure, empty state, and stopped/running/fault status examples. Link it from M35 instead of copying a divergent schema. Record the final contract and evidence in this ticket.

## Acceptance checks

- [ ] A valid shared login establishes a browser session; logout, idle/absolute expiry, and service restart invalidate it. Anonymous protected API calls receive 401, invalid credentials do not establish a session, cross-origin requests and requests without a valid CSRF token receive 403, and health reveals no machine or destination topology.
- [ ] Config save returns a redacted incremented revision; stale/live-worker saves return 409 without changing data, and 422 errors identify fields for the form.
- [ ] Saved machine and destination tests return bounded success or named failure without a secret, arbitrary path, device command, or destination write.
- [ ] Status and recent-data responses expose IDs, worker and acquisition faults, scan gaps, pending/retention boundary, and empty states required by the UI; no stale observation is presented as current data.
- [ ] UI assets and API work on the same restricted origin; passwords and session IDs do not appear in persistent browser storage, URLs, logs, or static assets, and deployment evidence records the restricted network boundary.

**Verification:** Exercise the route table against a local service with fake devices and disposable destinations. Capture representative response bodies and error codes, inspect browser network/storage state, and record paths to evidence here. This is software evidence, not hardware acceptance.

## Comments

- 2026-09-28: Initial console uses the current config/status/records/scans/control routes on one origin. Authenticated smoke checks returned 200 for config/status/records/scans and anonymous status returned 401 over the deployed HTTPS proxy. `POST /api/connection-test` and several M26/M27 status fields are still absent; full contract acceptance remains open.
- 2026-09-28: Accepted the shared local `admin` session-login design in ADR 0003. Its default `admin` / `00000000` and lack of login throttling are documented risks; external API clients and bearer-token compatibility are out of scope. All new session behavior remains planned until implemented and verified.
