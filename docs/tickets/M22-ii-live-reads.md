# M22 — Read Model II status safely over one serial link

Status: needs-triage
Completion: unverified

**Depends on:** [M18](M18-ii-read-contract.md), [M20](M20-first-durable-read.md), [M21](M21-secure-configuration.md).

**Outcome:** A configured II machine produces validated live observations from the safe upload set, with clear failures and no first-read hang.

## Input and output contract

- **Input:** A validated II serial-by-ID path, evidenced channel range, poll interval, M18 upload catalog, and one serialized serial session.
- **Output:** Bounded `D05`–`D09` machine reads and current-channel `D01`–`D04` observations with decoded values, units, source, channel, raw safe frame, UTC time, and quality in the spool.
- **Failure output:** Bad checksum, unsupported value, timeout, disconnect, or changed channel produces a source-specific fault or incomplete quality, never a stale successful observation; the read lane remains recoverable.
- **Boundary:** This owns live II reads. M23 owns all-channel inventory and M27 owns scheduling across machines.

## Fixed work order and evidence

1. In `devices/ii.py` and `runtime/supervisor.py`, use one serial session per machine at 9600/8N1 and a 2-second whole-request deadline. One live cycle is `D06`, `D05`, `D07`, `D08`, `D09`, `D01`–`D04` for the first `D06` channel, then `D06` again. Use M18's decoder. Store each success as version 1 `record_type: "status"`, `source: "Dxx"`, with raw frame hex, parsed values, scope, quality, and channel ID for `D01`–`D04`.
2. If either `D06` fails or the two displayed channels differ, mark every buffered `D01`–`D04` success `quality: "incomplete"`; do not attach it to the later channel. Each failed upload yields a source-specific `error` record and a status fault, never the prior successful value. Explicit controller rejection is unavailable. Timeout/disconnect closes or aborts the session and allows the next attempt to reconnect.
3. Evidence cases are first read disconnected, normal cycle, bad checksum, timeout, mid-frame disconnect, explicit rejection, and channel changes. For each record expected/actual elapsed bound (2 seconds per request), outgoing byte trace, exact record source/quality, fault, and next-attempt result. No write trace contains a command other than `UL` plus abort bytes.

## Scope and constraints

- Implement one serialized serial session using only `UL` uploads, checksum/frame validation, finite timeouts, abort/reconnect, and selected `/dev/serial/by-id/...` path. Never auto-pick an arbitrary USB device.
- Probe current channel and machine-level `D05`–`D09`; read current-channel `D01`–`D04` where supported. Detect channel changes during a cycle and mark the affected observation incomplete rather than mislabel it.
- Remove nested-lock acquisition in the connect/read path; the first disconnected read must finish or time out (B01). A failed upload produces an error/gap, not a replayed old value.

## Acceptance checks

- [ ] A fake serial device proves first read, reconnect, bad checksum, timeout, and mid-read disconnect end within configured bounds.
- [ ] Captured outgoing bytes contain only the approved read command family.
- [ ] Every read stores source, scope, units, channel identity, and evidence level; unsupported values remain explicit.
- [ ] One II fault is visible in status and does not crash the service.

**Verification:** Use a protocol fake with byte trace and a timed first-read case. Physical device correctness remains for M33.

## Comments

- 2026-09-28: UL-only reader and first-read/bad-checksum synthetic checks exist. Current-channel D01–D04, channel-change detection, field units, and full fault matrix remain open. Synthetic checks do not establish hardware acceptance.
- 2026-09-28: The worker now decodes `D06`, reads current-channel `D01`–`D04`, and marks those records incomplete if a second `D06` differs. `tests/test_runtime.py` checks changed-channel quality and durable per-source errors. Reconnect, timeout, disconnect, and complete captured-byte checks remain open.
- 2026-09-30: A real II required `EOT` after the final response `ACK` before it would accept the next `UL`; without it, only the first sequential upload completed. Added the terminator and a sequential fake regression. The 43-test suite passes. After rebuilding the container, a live cycle at displayed channel 100 read `D06`, `D05`, `D07`–`D09`, `D01`–`D04`, and a confirming `D06`; the channel stayed stable. Other M22 fault cases and full M33 evidence remain open.
- 2026-09-30: Operator corrected the connected serial dispenser's label from II to III. The prior live-cycle note's “II” refers to the previous label; the `UL`/`Dxx` names refer to the protocol documentation. The application now configures and records this machine as III. Full fault coverage and site acceptance remain open.
