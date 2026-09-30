# M33 — Confirm read-only coverage on real II and IV machines

Status: needs-triage
Completion: unverified

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

## Comments

- 2026-09-30: Partial live smoke run on revision `9d06cf8`. `uv run python -m unittest discover -s tests -v` passed 42 tests. A direct read-only IV probe at `192.168.1.11:1024` returned HTTP 200 for all 16 M24 status paths (07:47:56–07:48:13 UTC); per-request elapsed times were approximately 0.05–1.09 s. The probe used a 2,097,152-byte cap and recorded response lengths and JSON shapes only; it did not save sanitized response captures or compare values with the controller display. II access was blocked before the first request: `/dev/ttyUSB0` is `root:dialout` mode `0660`, and the test process is not in `dialout`. No inventory, diagnostic, destination, outage, or recovery tests ran. M32 remains unverified, so the M33 prerequisite was not met. Site ID, model/serial/firmware, evidenced recipe/channel counts, approved window, destination endpoints, outage permission, site limits, and operator signature are still missing. M33 remains unverified and cannot establish site acceptance from this smoke run.
- 2026-09-30: After adding the II serial device to the local Compose override and correcting the II session terminator, the application started through its authenticated control API. II status reads now succeed in the container; IV status reports success, and the Influx lane is running with acknowledged writes. The active IV inventory remains partial; scan outcomes mark `/v1/info/recipe/range` and `/v1/time` failed. Full family captures, controller comparison, destination reconciliation for all records, site limits, recovery run, and operator sign-off remain open; this does not verify M33.
- 2026-09-30: Operator corrected the serial machine label from II to III. Runtime config now uses model `III` and machine ID `Musashi-iii-0`. Queries against the configured bucket returned III `D01` pressure fields and an IV supply field; the destination worker is acknowledging writes. The current IV inventory remains partial, with `/v1/info/channel/range` failing validation against the configured count; earlier outcomes also failed `/v1/info/recipe/range` and `/v1/time`. During deployment, the spool count changed from 3,136 to 0 in observed status snapshots; the cause is unresolved. The spool has since accumulated new records. Full family captures, controller comparison, destination reconciliation, measured limits, and sign-off remain open.
