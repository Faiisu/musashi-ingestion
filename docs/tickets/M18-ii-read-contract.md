# M18 — Prove the Model II read contract with fixtures

Status: ready-for-agent
Completion: unverified

**Depends on:** None; can start now.

**Outcome:** A reviewer can distinguish the previously observed `D01` read from manual-derived `D02`–`D09` behavior before an adapter is built.

**Working spec:** [Model II read upload contract](../specs/model-ii-upload-contract.md).

## Input and output contract

- **Input:** Manufacturer pages for serial settings and `UL`/`DA01`–`DA09`, the retained `D01` reader, and labeled synthetic normal and fault frames.
- **Output:** For every `Dxx`, a cited request frame, response shape, scope, field and unit table, unavailable rule, frame limit, deadline, and a fixture with expected decoded values or explicit error.
- **Failure output:** Malformed length/checksum, timeout, disconnect, and unsupported channel each have a distinct expected result and outgoing-byte trace that contains only permitted uploads.
- **Boundary:** This defines a safe protocol and fixtures; M22 executes live reads, M23 performs channel sweeps, and M33 checks real firmware.

## Fixed work order and evidence

1. Update `docs/specs/model-ii-upload-contract.md` and `tests/fixtures/ii_uploads.json` only for the contract; update `tests/test_ii_decode.py` only if a fixture exposes a decoder mismatch. For each `D01`–`D09`, retain exactly one normal payload, expected parsed object, printed manual page, scope, and evidence label. Check the retained `D01` parser field by field; record any difference as a failing case.
2. Add named fixture cases `bad_length`, `bad_checksum`, `timeout`, `disconnect`, `unsupported_channel`, and `blank_numeric`. Expected outputs are respectively frame error, frame error, bounded timeout, bounded disconnect, explicit unavailable, and `null` for the affected numeric field. The expected write trace contains only `UL` request frames and protocol abort bytes `CAN`/`EOT`; it contains no state-changing command.
3. Evidence is a nine-row normal decode table plus a six-row fault table with expected/actual values and exact fixture keys. Unknown character encoding, firmware variant, and physical channel count stay in the M33 question list; do not mark them observed on hardware.

## Scope and constraints

- Use the [II manual and retained example](../reference/device-protocols.md) to document serial settings, the full `UL` handshake, checksums, maximum frame length, timeout/abort behavior, channel scope, units, and unavailable values.
- Create labeled synthetic fixtures for `DA01`–`DA09`, malformed frames, bad checksums, timeout, disconnect, and unsupported channel. Keep the original example separate from production dependencies; it imports a missing database module.
- Identify every command that changes state and make the planned request vocabulary exactly the safe upload commands. Do not infer that a manual response has been seen on hardware.

## Acceptance checks

- [ ] Each upload has a source page, expected request/response shape, field/units table, scope, and evidence label.
- [ ] `D01` fixture checks reproduce the retained reader's observed parsing; the other fixtures are visibly manual-derived.
- [ ] A machine-state-changing command cannot appear in the planned request set.
- [ ] Unknown firmware behavior and unavailable fields are listed for the site gate.

**Verification:** Record a field-by-field fixture and command comparison against the cited manual pages and retained example. Do not connect or operate a machine in this ticket.

## Comments

- 2026-09-28: II UL-only adapter and synthetic first-read/bad-checksum checks exist in `src/musashi_ingestion/devices/ii.py` and `tests/test_devices.py`. D02–D09 field fixtures, units, and unknown-firmware list remain open. Synthetic checks do not establish hardware acceptance.
- 2026-09-28: Added manual-derived `DA01`–`DA09` fixture values with page numbers in `tests/fixtures/ii_uploads.json`, strict decoding in `src/musashi_ingestion/devices/ii_decode.py`, and 2 decoder checks. The full malformed/timeout/disconnect fixture matrix and firmware questions remain open; no new hardware response was captured.
- 2026-09-28: Synthetic timeout/disconnect checks now assert bounded abort and the UL-only trace. The site questions are in the II read contract; a retained-reader parser comparison and peer review still remain before verification.
- 2026-09-28: Added a field-by-field comparison of the shared D01 values with the retained reader semantics, six named fault fixtures with exact writes, decoder/runtime checks for timeout versus OS-reported disconnect, and rejection of non-001 channel fields for machine uploads. Evidence table follows. This remains unverified pending peer review and M33 hardware/site confirmation.

### M18 implementation evidence (synthetic only)

The nine normal fixture keys are `uploads[0]` through `uploads[8]` in order D01–D09. Expected and actual parsed objects matched in `test_all_upload_layouts`:

| Key / manual page | Expected = actual parsed object |
| --- | --- |
| `uploads[0]` / 89 | `{"pressure_kpa":98.7,"dispense_time_ms":654,"vacuum_kpa_magnitude":3.21,"mode_code":2,"product_name":"SIGMA"}` |
| `uploads[1]` / 89 | `{"syringe_size_code":2,"syringe_size_cc":10,"adapter_tube_code":2,"adapter_tube_m":1.0}` |
| `uploads[2]` / 90 | `{"alpha_correction":123,"delta_correction_percent":85,"vacuum_correction_kpa":-0.31}` |
| `uploads[3]` / 90 | `{"remaining_detection_percent":50,"remaining_detection_count":6}` |
| `uploads[4]` / 91 | `{"remaining_volume_percent":50}` |
| `uploads[5]` / 91 | `{"displayed_channel":20}` |
| `uploads[6]` / 91 | `{"dispense_count":12345678}` |
| `uploads[7]` / 92 | `{"software_version_raw":"0100","model_specification":"V5"}` |
| `uploads[8]` / 92 | `{"sampled_syringe_sizes_cc":[5,10,50]}` |

The six fault fixture keys are executed by `test_ii_fault_fixture_matrix_and_safe_write_traces` and `test_blank_numeric_fixture_is_unavailable`; expected and actual outcomes and traces matched:

| Fixture key | Expected | Actual |
| --- | --- | --- |
| `faults[0]` / `bad_length` | `IIProtocolError`; `ENQ, UL001D01, EOT, ACK, CAN, EOT` | Same class and writes |
| `faults[1]` / `bad_checksum` | `IIProtocolError`; `ENQ, UL001D01, EOT, ACK, CAN, EOT` | Same class and writes |
| `faults[2]` / `timeout` | `IITimeout`; `ENQ, CAN, EOT` | Same class and writes |
| `faults[3]` / `disconnect` | `IIDisconnected`; `ENQ, UL001D01, CAN, EOT` | Same class and writes |
| `faults[4]` / `unsupported_channel` | `IIUnavailable`; `ENQ, UL001D01, EOT, ACK, CAN, EOT` | Same class and writes |
| `faults[5]` / `blank_numeric` | Pressure `null`; other D01 values unchanged | Exact expected object |

The accepted write vocabulary is `ENQ`, `ACK`, `EOT`, `CAN`, and a framed `UL001D01`; no other application command is emitted. These are fake-serial and synthetic-payload results, not hardware observations.
