# M21 — Configure machines and destinations through a protected API

Status: needs-triage
Completion: unverified

**Depends on:** [M17](M17-agree-rebuild-contract.md), [M36](M36-session-auth-backend.md).

**Outcome:** An operator can save, inspect, and validate multiple machines and destinations without exposing secrets or silently accepting invalid acquisition settings.

## Input and output contract

- **Input:** An authenticated versioned config document with a current revision, stable machine and destination IDs, model-specific connection fields, per-machine schedules, and secret-file references.
- **Output:** An atomic saved revision and redacted config read; field-level validation results, protected connection-test results, and a safe bind/session state. Collection may start with no destination configured.
- **Failure output:** Invalid or stale input leaves the previous complete revision intact; missing or invalid sessions, forbidden device requests, inline secrets, and unsupported destination/family choices are rejected without disclosure.
- **Boundary:** This owns configuration schema, validation, atomic save, and safe connection tests. M36 owns login, sessions, and CSRF; M34 owns the browser API contract and UI-facing status fields. Device adapters own request allowlists; M26 owns retained records and routing when a destination changes.

## Fixed work order and evidence

1. Keep version 1 `PUT /api/config` with integer `revision`, `machines[]`, and `destinations[]`; add `retention_max_history_records` from the [shared contract](../specs/agent-execution-contract.md), default 100. A machine entry requires stable `id`, `model`, and model fields: II `port` under `/dev/serial/by-id/` plus `channel_count` 1–100; IV IPv4 `host`, `port` 1024–1026, `channel_count` 1–400, `recipe_count` 1–100. `poll_interval_seconds` defaults to 1 and must be finite and at least 1; `inventory_interval_seconds` defaults to 3600 and must be finite and at least 60. Destination `kind` is exactly `mqtt`, `postgres`, or `influxdb`; require stable `id` and `secret_ref`. Reject duplicate IDs and duplicate device endpoints.
2. MQTT requires `host`, `topic`, optional `port` 1–65535 (default 1883 or 8883 with TLS), `tls` boolean (default false), and `max_payload_bytes` 1,024–262,144 (default 262,144). PostgreSQL uses a DSN in `secret_ref` and a 2-second connection deadline. InfluxDB requires `url`, `org`, `bucket`, HTTPS for non-loopback URLs, and `max_payload_bytes` at least 16,777,216 (default 16,777,216); verify TLS by default. MQTT's secret file is username/password JSON, PostgreSQL's is a DSN, and InfluxDB's is a token. Reject inline `password`, `token`, `secret`, and `dsn` fields; reject unreadable or empty secret files before Start.
3. `GET /api/config` returns the persisted revision and redacts `secret_ref` as `********`. A PUT with that placeholder retains the prior reference for the same ID. A stale revision or update while any worker is alive returns 409; validation returns 422 with field-keyed `errors`; neither changes the file. Use M36's session authorization and CSRF checks for all protected routes. Preserve the current atomic write/rename/fsync behavior.
4. Add authenticated `POST /api/connection-test`; example body is `{"kind":"machine","id":"ii-1"}`. `kind` is `machine` or `destination`, and `id` must name a saved entry. Use only saved config. II reads `D06`; IV reads `/v1/status/main`; destination checks establish a connection or authentication without publishing/writing a record. Success is HTTP 200 with `{"ok":true,"id":"ii-1","kind":"machine"}`. A bounded connection failure is HTTP 200 with the same fields, `ok:false`, and `error` from `timeout`, `connection_failed`, `authentication_failed`, or `invalid_response`. Invalid ID/kind is 422. Never include a secret, DSN, or arbitrary remote response. Each test has a 2-second deadline.
5. Evidence table covers valid II/IV reload, destination-free config, all duplicate/invalid fields, CAS race, interrupted save, placeholder edit, anonymous and CSRF-rejected config/test requests, each connection-test failure, and no arbitrary path/command. The next destination added while stopped must expose retained-history boundary at Start, as specified by M26.

## Scope and constraints

- Define versioned configuration with stable machine IDs, model-specific serial or IP/port fields, per-machine status and inventory policy, retention/backfill policy from M17, destination choices, and secret references. Retained `.env` and `config/config.json` are legacy local data, not a schema to import without validation.
- Validate finite poll intervals of at least one second, duplicate IDs/ports, IV port 1024–1026, and resource limits from M17. Reject unsupported record-family/destination combinations before Start.
- Require M36 session authorization for configuration reads/writes and connection tests; redact responses and logs. Keep management bound to a safe address unless explicitly configured for a restricted network (B02, [ADR 0003](../adr/0003-shared-session-login-for-the-operator-console.md)).
- Save with revision compare-and-swap and atomic replacement. Redacted placeholders must not overwrite existing secrets. Default auto-start off.

## Acceptance checks

- [ ] Valid II and IV entries survive reload with stable IDs; bad values, duplicates, non-finite numbers, and unsupported combinations return field-level errors.
- [ ] Stale revision and interrupted write cannot corrupt or overwrite a newer complete config.
- [ ] Anonymous configuration reads reveal no topology; anonymous or CSRF-rejected writes and connection tests change no state; saved secrets never appear in responses or logs. M36 records credential, session, and auth-route evidence.
- [ ] No API request can submit an arbitrary IV path or a state-changing serial command.
- [ ] A valid machine-only configuration can start collection without destinations; adding a destination while stopped preserves machine IDs, assigns retained history automatically, and exposes the retained-history boundary.

**Verification:** Exercise authenticated/anonymous API calls, save conflicts, process interruption, and secret-preserving edits with mock connection endpoints.

## Comments

- 2026-09-28: Versioned config, CAS save, redaction, and basic validation exist in `src/musashi_ingestion/config/store.py`. Interruption, connection-test, concurrent API, and full invalid-input checks remain open. Synthetic checks do not establish hardware acceptance.
