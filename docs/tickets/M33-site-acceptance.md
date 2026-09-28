# M33 — Confirm read-only coverage on real II and IV machines

Status: needs-triage
Completion: not-started

**Depends on:** [M32](M32-hardware-free-qualification.md).

**Outcome:** A site operator can accept the supported firmware/device combinations with measured coverage, safe request traces, and recovery evidence.

## Input and output contract

- **Input:** Authorized site window, named machine and firmware inventory, approved read-only access, selected network and all three destination routes, M32 evidence, and provisional M17 limits to measure.
- **Output:** An operator-signed per-source matrix with sanitized captures, actual values or explicit unsupported cases, safe request traces, measured load/size/latency/outage limits, destination reconciliation, and site-specific recovery result.
- **Failure output:** An unsupported firmware variant, unsafe request, missing capture, exceeded limit, or incomplete destination reconciliation becomes a named release blocker or follow-up ticket; it is not silently treated as supported.
- **Boundary:** This is the hardware-verified gate for the named site and firmware only. It does not generalize to untested models, versions, or installations.

## Fixed work order and evidence

1. Before a site run, the operator supplies a dated authorization, site ID, each machine's model/serial/firmware, approved II serial path or IV IP/port, evidenced channel/recipe counts, approved read window, three destination endpoints, outage test permission, and site retention/outage requirement. Missing any required item is a `blocked` input row; do not invent it. M32 must have passed for the exact software revision.
2. Deliver `docs/evidence/M33-site-acceptance.md` with one row for each II `D01`–`D09` and every IV family in the M32 manifest, per named machine/firmware. Columns are source, request bytes/path, sanitized response capture, parsed value/unit or explicit unsupported, controller/display comparison, start/end UTC, record ID, scan item/result, and evidence level. Record every excluded path as absent from the request trace. The operator validates sanitized captures and signs the document with name/date; an agent cannot self-approve.
3. Measure status cycle duration and lag, complete scan duration and age, maximum raw/record/MQTT/Influx bytes, spool growth per hour, disk/WAL peak, successful delivery lag to each destination, and tested outage/recovery duration. For each metric record raw measurement, method, sample count, provisional M17 limit, site-required limit, and pass/fail. Where a site-required limit is not supplied, mark the row blocked. Reconcile the same `record_id` in all three destinations, including one partial scan and retained-history boundary.
4. A firmware mismatch, forbidden request, missing capture, unsupported value not explicitly recorded, exceeded required limit, missing destination row, or unsigned acceptance blocks release for that site. Create a follow-up ticket for each blocker and keep `Completion` unverified until the operator-signed matrix and recovery evidence are attached.

## Scope and constraints

- Obtain authorized access to named II and IV devices, firmware versions, network restrictions, selected destinations, and site-approved test window. Do not change machine settings or start diagnostics as part of ingestion.
- Compare each II upload and IV read family against controller display/manual, including units, URL/payload numbering, unavailable values, supported channels/recipes, range responses, export/log sizes, and diagnostic results.
- Measure poll lag, scan duration, record/payload sizes, spool growth, outage duration, and delivery latency to validate or revise M17 limits. Test restart/outage only with site approval.

## Acceptance checks

- [ ] Operator signs a matrix naming machine/firmware, each tested source, observed value or exclusion, and sanitized capture location.
- [ ] Request traces show only permitted reads and no IV screen image; any unsupported firmware behavior has a follow-up ticket.
- [ ] Full and partial scans, destination reconciliation, and measured capacity meet agreed site limits or are reported as release blockers.
- [ ] Operations guide contains site-specific safe configuration and recovery results without secrets.

**Verification:** Review real-device captures, controller-side evidence, service traces, destination queries, and signed site acceptance. This is the sole hardware-verified gate.
