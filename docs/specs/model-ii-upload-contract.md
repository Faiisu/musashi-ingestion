# Model II read upload contract

This is a manual-derived software contract for M18 and M22. The retained II example exercised `UL ... D01` on a machine and uses the same `P/T/V/M/N` parser. The fixtures and the other upload parsers are synthetic. They are not hardware captures for this rebuild.

## Transport and request boundary

The II manual specifies RS-232C at 9600 baud, 8 data bits, no parity, and one stop bit (printed page 78). Its upload handshake is on page 81 and frame/checksum format on pages 82–83. The adapter uses a selected `/dev/serial/by-id/...` port, a 2-second whole-request deadline, a 128-byte frame cap, and `CAN`/`EOT` on failure. It sends only `UL` for `D01`–`D09`; the channel number is 1–100. The adapter never sends download, dispense, mode, clear, or other state-changing commands. `D01`–`D04` are channel reads; `D05`–`D09` are machine reads. A rejected upload is unavailable, not a previous value.

The request frame is `STX + hex length + UL + three-digit channel + Dxx + checksum + ETX`. The checksum is the negative sum modulo 256 of the ASCII length, command, and data bytes, encoded as two uppercase hexadecimal characters. Responses use the corresponding `DAxx` prefix inside the same framed format. The adapter validates length and checksum before decoding.

## Payload coverage

The source is the scanned [II manufacturer manual](../../examples/Instruction%20Manual%20Super%20%CE%A3CMII%20EN.pdf). The exact synthetic strings and expected parsed values live in [ii_uploads.json](../../tests/fixtures/ii_uploads.json); code in `src/musashi_ingestion/devices/ii_decode.py` is the runtime authority for decoding.

| Upload | Printed page | Payload fields and units | Scope and evidence |
| --- | --- | --- | --- |
| `DA01` | 89 | `P` pressure in 0.1 kPa steps; `T` dispense time in ms; `V` vacuum magnitude in 0.01 kPa steps; `M` mode code 0–3; `N` product name | Channel. Parser layout matches retained reader; fixture is manual-derived. |
| `DA02` | 89 | `S` syringe size code mapped to 3/5/10/20/30/50/70 cc; `A` tube length code mapped to 0.5/1/1.5/2 m | Channel; manual-derived. |
| `DA03` | 90 | Signed `A` alpha correction; `D` delta correction in percent; signed `V` vacuum correction in 0.01 kPa steps | Channel; manual-derived. |
| `DA04` | 90 | `L` remaining detection level in percent; `C` detection counter setting | Channel; manual-derived. |
| `DA05` | 91 | `R` current remaining volume in percent | Machine; manual-derived. |
| `DA06` | 91 | `CH` currently displayed channel number | Machine; manual-derived. |
| `DA07` | 91 | `CT` eight-digit dispense count | Machine; manual-derived. |
| `DA08` | 92 | `VR` raw software version digits; `SP` V2/V5 model code | Machine; manual-derived. Version digits remain raw until firmware confirmation. |
| `DA09` | 92 | `SY` seven flags for sampled syringe sizes 3/5/10/20/30/50/70 cc | Machine; manual-derived. |

Blank numeric fields are returned as unavailable rather than guessed. A malformed payload, invalid checksum, timeout, or disconnect produces a source error. The worker reads `D06` before and after the current-channel `D01`–`D04` group and marks those observations incomplete if the displayed channel changes or cannot be confirmed.

## Site questions

M33 must confirm these shapes and scales on named machine/firmware combinations; how half-width Japanese product names are encoded; which uploads can return unavailable; actual supported channel count; whether `D06` can change between the two probes; response latency; and whether any fields vary by mode or controller version. Do not infer full channel coverage from a configured maximum alone.
