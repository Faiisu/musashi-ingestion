# Rebuild plan and tickets

This page is navigation for the rebuild. A partial backend implementation is runnable with a simulated read; full ticket acceptance, destination integration, and hardware validation remain open. Each [ticket](agents/issue-tracker.md) owns its `Status:` and `Completion:` fields; this page does not duplicate them. Use the [source-of-truth map](ssot.md) for evidence levels and authority.

The previous M01–M16 ticket files were removed. The historical backend findings remain in the [audit report](audits/backend-2026-09-28.md); the original backend ticket set is M17–M33. [M34](tickets/M34-frontend-api-contract.md) and [M35](tickets/M35-operator-frontend.md) track the protected operator API/UI; [M36](tickets/M36-session-auth-backend.md) and [M37](tickets/M37-operator-login-ui.md) isolate the accepted session-login redesign in [ADR 0003](adr/0003-shared-session-login-for-the-operator-console.md). An initial token-based console is implemented and deployed; connection tests, session login, and full backend status fields remain open.

The [agent execution contract](specs/agent-execution-contract.md) fixes shared shapes, limits, retention, and evidence format. Each ticket now has a fixed work order and named result cases. Ticket dependencies and external site inputs still govern when its work can start; `Status:` and `Completion:` remain in the ticket itself.

## Implementation snapshot (2026-09-28)

The repository now contains the management API and durable spool (phases 0–1), II/IV read adapters and machine workers (phase 2), three destination adapters (phase 3), and a Compose image definition (part of phase 4). The 23 socket-free regression checks pass, including process-kill and backup/restore recovery cases. An earlier API restart check, MQTT broker check, PostgreSQL check, and image build also passed. These results cover pieces of the ticket criteria; consult each ticket for acceptance evidence and remaining checks. The full simulated matrix in M32 and real-device acceptance in M33 have not run. InfluxDB has not completed a disposable bucket round trip. Socket and Docker access in the current environment prevent those integration checks here.

| Phase | Result that can be reviewed | Active tickets |
| --- | --- | --- |
| 0. Establish constraints and safe requests | Measurable release gates and manual-backed II/IV request contracts | [M17](tickets/M17-agree-rebuild-contract.md), [M18](tickets/M18-ii-read-contract.md), [M19](tickets/M19-iv-read-contract.md) |
| 1. Establish a safe durable core | One simulated read survives restart; configuration, authorization, and spool recovery are defined | [M20](tickets/M20-first-durable-read.md), [M21](tickets/M21-secure-configuration.md), [M26](tickets/M26-spool-recovery-and-identity.md), [M36](tickets/M36-session-auth-backend.md) |
| 2. Read and account for machines | II and IV status plus complete/partial inventories, with independent schedules | [M22](tickets/M22-ii-live-reads.md), [M23](tickets/M23-ii-complete-inventory.md), [M24](tickets/M24-iv-live-reads.md), [M25](tickets/M25-iv-complete-inventory.md), [M27](tickets/M27-multi-machine-scheduling.md) |
| 3. Deliver records | MQTT, PostgreSQL, and InfluxDB each preserve supported data and independent pending state | [M28](tickets/M28-mqtt-delivery.md), [M29](tickets/M29-postgres-delivery.md), [M30](tickets/M30-influx-delivery.md) |
| 4. Prepare release | Restricted deployment and a full hardware-free failure matrix | [M31](tickets/M31-deploy-and-recover.md), [M32](tickets/M32-hardware-free-qualification.md) |
| 5. Confirm at the site | Named devices and firmware validated with operator evidence | [M33](tickets/M33-site-acceptance.md) |
| 6. Operator interface | Browser API contract, four operator pages, and session sign-in | [M34](tickets/M34-frontend-api-contract.md), [M35](tickets/M35-operator-frontend.md), [M37](tickets/M37-operator-login-ui.md) |

## Dependency and evidence gates

- M17, M18, and M19 define the initial constraints. Every other ticket lists its blocking edges in its own file. M36 can implement the accepted login decision before M17's broader rebuild review; M37 follows M36. M26 depends on M20 and M21; II and IV inventories require its durable scan state before their restart checks can pass.
- Simulated fixtures and test services can qualify M20–M32. They do not establish hardware compatibility. M33 requires authorized site access and is the only hardware-verified gate.
- Every device request must stay read-only: only permitted II uploads and exact IV read paths; no state-changing device request, screen image, or arbitrary device URL. The planned frontend uses only the protected management API.
- Record-family coverage, size limits, scan completeness, secure management access, spool-full behavior, destination identity, and replay identity must be demonstrated before release. The [historical audit](audits/backend-2026-09-28.md) describes B01–B10; M17 maps them to the new gates and M32 requires regression evidence.
- [ADR 0002](adr/0002-independent-collection-and-destination-rerouting.md) sets the new collection/spool/forwarder boundary, retained-history backfill, and pending-only destination reroute. The current code still retains old-target assignments, so M26 and M32 must prove the new behavior.
- [ADR 0003](adr/0003-shared-session-login-for-the-operator-console.md) replaces the planned/current bearer-token browser flow with a shared local account and server-side sessions. M36/M37 own the login migration; M21/M34/M35 consume and verify it. The default password and lack of login throttling require a restricted management network.
- A ticket may become `Completion: verified` only when all of its acceptance checks have recorded evidence. Keep unknown site values provisional until M33 measures them.
