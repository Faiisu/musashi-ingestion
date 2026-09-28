# M17 — Agree the rebuild contract and release gates

Status: ready-for-human
Completion: unverified

**Depends on:** None; can start now.

**Outcome:** One decision record tells implementers what must be collected, what must never be sent to a machine, and what evidence allows release.

## Input and output contract

- **Input:** II and IV manuals, retained II example, historical findings B01–B10, current architecture, software limits, and unresolved site capacity and firmware facts.
- **Output:** A reviewed coverage matrix naming each II upload and IV read family, its scope, evidence level, destination support, safe request boundary, measurable limit with owner, and M32/M33 release evidence.
- **Unresolved input:** Unknown site counts, payload sizes, outage duration, and firmware variants stay explicitly provisional with a measurement owner and release gate; no guessed hardware claim closes them.
- **Boundary:** This ticket decides the contract and sizing method. Device code, spool behavior, and destination adapters belong to their implementation tickets.

## Fixed work order and evidence

1. Use the [shared execution contract](../specs/agent-execution-contract.md) as the fixed record, scan, retention, routing, limit, and error vocabulary. Produce one row in `docs/specs/rebuild-contract.md` for each `D01`–`D09` upload and each IV family listed in `docs/reference/device-protocols.md`; columns are source, item scope, manual page, software evidence, size/deadline, and M32/M33 gate. Explicitly mark IV screen and all control requests excluded.
2. Reconcile every B01–B10 finding against exactly one primary ticket and its named regression case. Keep provisional software limits in the existing operating-envelope table; site measurements remain M33 inputs with owner `site operator`. Use the sizing equation already in the spec and label a 24-hour claim `unverified` until measured sizes exist.
3. Submit the changed spec plus a review matrix with rows `II manual`, `IV manual`, `retained II example`, `audit B01–B10`, `ADR 0001`, `ADR 0002`, and `ADR 0003`; each row cites the checked path/page and records pass or a named unresolved fact. A maintainer's acceptance of that review is required before `Completion: verified` because this ticket's outcome is an agreed contract.

## Scope and constraints

- Reconcile the [proposed architecture](../architecture.md), [device catalog](../reference/device-protocols.md), and [historical audit](../audits/backend-2026-09-28.md). Treat manuals as protocol evidence, the old audit as failure evidence, and neither as proof of a new implementation.
- Set a coverage matrix for II `D01`–`D09` and every IV read group, including channel/recipe ranges, JSON export, TSV log, time, diagnostic results, and explicit exclusion of screen images and all control actions.
- Decide measurable limits: supported machine count, status interval and timeout, inventory request budget, maximum raw response/record/MQTT message, spool quota and outage duration, unassigned-record retention/backfill window, scan age, delivery lag, and acceptable fault visibility. Values require a sizing calculation or test evidence; mark unknown site values as provisional.
- Require all three destinations to preserve each accepted record family for release. Define complete versus partial scans, retained-history backfill, and pending-only destination rerouting under [ADR 0002](../adr/0002-independent-collection-and-destination-rerouting.md). Define release gates for simulated qualification and later site acceptance.

## Historical audit coverage

The replacement map is: B01 → M22; B02 → M36 primary, with M20/M21/M31/M34 regression checks; B03 → M20, M26, M27; B04 → M26 pending-only reroute under ADR 0002; B05 → M25; B06 → M30; B07 → M28; B08 → M27; B09 → M29; B10 → M32. Confirm this map during the contract review and preserve a regression check for each finding.

## Acceptance checks

- [ ] A reviewed architecture decision or spec records the coverage matrix, numeric limits or provisional ranges, ownership of each limit, and the assumptions requiring site confirmation.
- [ ] The security boundary explicitly requires authenticated management, restricted network access, secret redaction, and read-only protocol enforcement.
- [ ] The release gate maps audit B01–B10 to replacement tickets and requires evidence for each before declaring deployable.
- [ ] The contract states collector/spool/forwarder inputs and outputs, destination-free collection, retention-limited backfill, pending-only reroute, and complete-scan semantics without relying on current code behavior.
- [ ] No proposed behavior is described as hardware-verified without a named device, firmware, capture, and date.

**Verification:** Review the decision against both manuals, the retained II example, every audit finding, and the new ticket dependency graph. Record unresolved choices as explicit blockers, not guessed defaults.

## Comments

- 2026-09-28: Working contract: [rebuild-contract.md](../specs/rebuild-contract.md). Limits are provisional; manual cross-check and site sizing/review are still open. Synthetic checks do not establish hardware acceptance.
- 2026-09-28: Added the per-family coverage/evidence matrix, source review record, and one-primary-ticket regression ownership for B01–B10 in the working contract. Maintainer acceptance remains required before this ticket can be verified; site measurements remain M33 inputs.
