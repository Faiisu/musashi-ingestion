# M35 — Build the operator frontend

Status: needs-triage
Completion: unverified

**Depends on:** [M34](M34-frontend-api-contract.md), [M37](M37-operator-login-ui.md).

**Outcome:** An operator can inspect acquisition health, configure machines and destinations, test saved connections, and review recent observations and inventory coverage in a browser on the protected management origin.

## Pages and behavior

| Page | Required content and actions | API |
| --- | --- | --- |
| Overview | Process and acquisition state, Start/Stop, acquisition fault, per-machine and per-destination summaries, pending count, oldest pending age, retained-history boundary, prune count, disk/WAL usage. Distinguish stopped, starting, running, and faulted workers. | `GET /health`, `GET /api/status`, `POST /api/control/start`, `POST /api/control/stop` |
| Machines | Configured II/IV IDs, model-specific endpoint fields, polling and inventory intervals, channel/recipe counts, per-machine last attempt/success, lag, skips, fault, and liveness. Add/edit/remove through the full configuration document; Test only after Save. | `GET/PUT /api/config`, `GET /api/status`, `POST /api/connection-test` |
| Destinations | MQTT/PostgreSQL/InfluxDB entries, redacted secret reference, delivery state and pending age/count by lane. Add/edit/remove through the full configuration document; Test only after Save. Show the retained-history limit when adding a destination and pending reroute implications before saving an endpoint change. | `GET/PUT /api/config`, `GET /api/status`, `POST /api/connection-test` |
| Recent data | Latest ten records with machine, model, type, source, observed time, evidence type, and quality; latest ten scans with complete/partial state and missing/failed/unsupported item keys. Label these as recent entries, not a complete archive. | `GET /api/records`, `GET /api/scans` |

## Input and output contract

- **Input:** The [M34 API contract](M34-frontend-api-contract.md), M37's session sign-in UI/API client, and redacted version 1 configuration. The UI must use server-provided IDs and timestamps rather than synthesizing device health.
- **Output:** An accessible, responsive interface that makes current state, errors, and the Stop → edit → Save → Test → Start sequence understandable. Editing a secret reference uses an explicit replacement input; an unchanged `********` placeholder preserves the saved reference.
- **Failure output:** M37 handles 401/403 and clears protected page data on sign-out or expired session; 409 retains unsaved form values and offers a reload of the latest revision; 422 maps server field keys to inputs and shows unmatched errors; network/test failures and acquisition faults remain visible. Do not silently retry a config mutation or Start.
- **Boundary:** This owns browser presentation and interaction. M34 owns server routes and status fields; M21 owns validation and safe connection tests; M33 owns real-device acceptance. `POST /api/mock-read` is a development fixture and is not an operator action.

## Fixed work order and evidence

1. Build the four pages above using the M34 route table and M37's session client. Use no third-party runtime assets. Keep all visible UI copy, status text, validation, and error messages in English. Provide keyboard access, labeled inputs, visible focus, readable status text, and explicit loading/empty/error states.
2. Treat configuration as one revisioned document. Disable edits while workers are alive, preserve unrelated machine/destination entries on edit, and show a confirmation for removal or endpoint reroute. On 409, fetch the new revision and require the operator to review conflicts before saving again. Do not convert redacted placeholders into new secret values.
3. Show device values with their `observed_at` and `evidence_type`; label `simulated` records plainly. A failed or missing scan item must not appear complete. Show status freshness separately from historical observations; a page refresh must not imply a new machine read.
4. Record a page-by-page review using fake devices and representative API success/error responses. Include narrow and wide viewport captures, keyboard operation, 401/403/409/422 handling, offline API behavior, stopped and faulted states, and the full Stop → edit → Save → Test → Start flow. From a separate operator network device, open the protected HTTPS address and exercise sign-in, status read, sign-out, and a reload; record device/browser, route reachability, and safe screenshots without credentials or site-specific addresses.

## Acceptance checks

- [ ] All four pages render empty, loading, healthy, and faulted states with no false claim of live or hardware-verified data.
- [ ] An operator can edit II/IV machines and all three destination kinds, resolve validation/conflict errors, test saved entries, and explicitly start/stop acquisition without losing unrelated configuration.
- [ ] Recent records and scans show evidence type, observation age, and complete/partial/missing coverage accurately; the UI does not imply more than ten entries are available.
- [ ] Keyboard and narrow-screen review covers every form, control, status message, and error path; text remains usable without color cues and all UI text is English.
- [ ] Sign-in, sign-out, page reload with a valid session, 401 recovery, and CSRF 403 handling work; browser inspection finds no password, session ID, or CSRF token in persistent storage, URL, static assets, or screenshots.
- [ ] A separate operator device on the approved network reaches the protected management origin and completes sign-in, status read, reload, and sign-out; cookie flags and network restrictions match M36/M31. If direct HTTP is used, it is limited to an exact private-LAN origin; the HTTPS proxy origin remains available. Evidence names the device/browser and date without exposing credentials.

**Verification:** Review the interface on the same-origin local service with fake II/IV and destination responses, then repeat the named access flow from a separate operator network device. Record captures and behavior notes against each acceptance check here. Device compatibility remains M33 evidence.

## Comments

- 2026-09-28: Initial responsive four-view console is served by `src/musashi_ingestion/api/server.py` and deployed at the private Tailscale endpoint. It covers current routes and secure in-memory token entry. M34's connection-test route and complete status contract are still open; operator-device, keyboard, narrow-viewport, and full workflow review remain unverified.
- 2026-09-28: M37 now owns the shared session sign-in UI; M35 verifies its integration with all four operational pages and access from a separate network device. Current token-entry UI remains implemented behavior until M37 is completed; the accepted login defaults are weak and must not be exposed beyond a restricted network.
- 2026-09-28: Network-access request adds an exact private-LAN HTTP origin alongside the tailnet HTTPS origin. Separate-device sign-in remains unverified.
