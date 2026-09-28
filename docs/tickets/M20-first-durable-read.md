# M20 — Run one safe mock read into durable storage

Status: needs-triage
Completion: unverified

**Depends on:** [M17](M17-agree-rebuild-contract.md), [M18](M18-ii-read-contract.md).

**Outcome:** From a fresh checkout, an operator can start a minimal backend, obtain health/status, and see one simulated II `D01` observation survive restart.

## Input and output contract

- **Input:** A fresh checkout, a nonempty operator credential, a temporary data directory, and one labeled synthetic II `D01` response with machine and channel identity.
- **Output:** One authenticated mock-read request commits a versioned observation with stable `record_id`, source, scope, UTC time, quality, and `simulated` evidence; `/health` reports process state and protected API reads expose the committed record after restart.
- **Failure output:** Blank/missing credential prevents sensitive access; an oversized response fails before commit and produces a visible acquisition fault without a success record.
- **Boundary:** This proves the smallest collector-to-spool path. It does not establish real serial compatibility, inventory completion, or destination delivery.

## Fixed work order and evidence

1. Use the documented README quickstart from a fresh temporary `MUSASHI_DATA_DIR`; set a nonempty `OPERATOR_TOKEN`. `POST /api/mock-read` with `{}` must return HTTP 201 and `record_id`. `GET /api/records` must contain that same ID and a version 1 `D01` simulated record after service restart. SQLite has one corresponding committed row and zero delivery rows.
2. Record exact HTTP status and JSON for `/health`, unauthorized `/api/records`, unauthorized `/api/control/start`, blank-token startup, and an injected serialized record larger than 2,097,152 bytes. Expected: health 200 without topology; unauthorized routes 401; blank token prevents startup; oversized write returns fault, creates no successful record, and health reports acquisition fault.
3. Update `README.md` only to match commands actually exercised. Evidence is the command transcript, returned ID before/after restart, SQLite row count, and fault/authorization table. Keep the mock's evidence level `simulated`.

## Scope and constraints

- Establish package, dependency lock or bounded versions, one documented local command, a reproducible container build, and a small backend with no frontend.
- Wire one synthetic II `D01` read through validated versioned envelope to an on-disk SQLite transaction before reporting success. Include source, machine ID, channel ID, UTC observation time, evidence type `simulated`, and stable record ID.
- Keep the service closed by default: management mutations require a nonempty credential; health is non-sensitive. A missing token must fail startup or disable management, never grant access (audit B02).
- Set a real byte limit before SQLite insertion, make oversized input a visible error, and never truncate to claim success (B03). Do not claim this slice implements full II coverage.

## Acceptance checks

- [ ] A fresh environment can run the documented build and one mock read; restart preserves the same committed record ID.
- [ ] The unauthenticated start/config mutation is denied, including when token configuration is blank.
- [ ] Oversized data is rejected before commit and appears as a fault; health distinguishes process health from acquisition state.
- [ ] The simulated read commits to the spool with an empty destination list; the collector does not require a forwarder to exist.
- [ ] README shows the exact commands and expected result actually observed.

**Verification:** Run from a clean checkout with a temporary data directory, interrupt after commit, restart, inspect SQLite, and call both authenticated and unauthenticated routes.

## Comments

- 2026-09-28: Synthetic API read, authorization, restart persistence, record limit, package install, and Docker build were exercised; see `tests/test_api.py`, `tests/test_core.py`, and README. Clean-host and fault/status matrix evidence is incomplete. Synthetic checks do not establish hardware acceptance.
