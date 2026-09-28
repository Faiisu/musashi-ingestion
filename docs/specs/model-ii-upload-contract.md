# Model II read upload contract

This is a manual-derived software contract for M18 and M22. The retained II example exercised `UL ... D01` on a machine and uses the same `P/T/V/M/N` parser. The fixtures and the other upload parsers are synthetic. They are not hardware captures for this rebuild.

## Transport and request boundary

The II manual specifies RS-232C at 9600 baud, 8 data bits, no parity, and one stop bit (printed page 78). Its upload handshake is on page 81 and frame/checksum format on pages 82–83. The adapter uses a selected `/dev/serial/by-id/...` port, a 2-second whole-request deadline, and a 128-byte cap on bytes between `STX` and `ETX`. On failure it attempts `CAN` then `EOT` before closing the port. The request vocabulary is exactly `UL` with one `D01`–`D09` selector; channel reads require an integer from 1 through 100 and machine reads use channel field `001`. It never sends download (`DL`), dispense, mode, clear, or other state-changing commands. `D01`–`D04` are channel reads; `D05`–`D09` are machine reads. A rejected upload is unavailable, not a previous value.

The request frame is `STX + two-digit hex payload length + UL + three-digit channel + Dxx + two-digit checksum + ETX`. The checksum is the negative sum modulo 256 of the ASCII length, command, and data bytes, encoded as two uppercase hexadecimal characters. Each command acknowledgement follows the manual's UL handshake; the response frame begins with the matching `DAxx` payload. The adapter validates length and checksum before decoding. The only application request is `UL`; handshake control bytes are `ENQ`, `ACK`, `EOT`, and, on abort, `CAN`.

## Payload coverage

The source is the scanned [II manufacturer manual](../../examples/Instruction%20Manual%20Super%20%CE%A3CMII%20EN.pdf). The exact synthetic strings and expected parsed values live in [ii_uploads.json](../../tests/fixtures/ii_uploads.json); code in `src/musashi_ingestion/devices/ii_decode.py` is the runtime authority for decoding.

| Request / response | Printed page | Response fields and units | Scope and evidence |
| --- | --- | --- | --- |
| `ULnnnD01` → `DA01` | 89 | `P` pressure in 0.1 kPa steps; `T` dispense time in ms; `V` vacuum magnitude in 0.01 kPa steps; `M` mode code 0–3; `N` product name | Channel `nnn`; parser layout and all shared parsed values match the retained reader; manual-derived fixture. |
| `ULnnnD02` → `DA02` | 89 | `S` syringe size code mapped to 3/5/10/20/30/50/70 cc; `A` tube length code mapped to 0.5/1/1.5/2 m | Channel `nnn`; manual-derived fixture. |
| `ULnnnD03` → `DA03` | 90 | Signed `A` alpha correction; `D` delta correction in percent; signed `V` vacuum correction in 0.01 kPa steps | Channel `nnn`; manual-derived fixture. |
| `ULnnnD04` → `DA04` | 90 | `L` remaining detection level in percent; `C` detection counter setting | Channel `nnn`; manual-derived fixture. |
| `UL001D05` → `DA05` | 91 | `R` current remaining volume in percent | Machine; manual-derived fixture. |
| `UL001D06` → `DA06` | 91 | `CH` currently displayed channel number | Machine; manual-derived fixture. |
| `UL001D07` → `DA07` | 91 | `CT` eight-digit dispense count | Machine; manual-derived fixture. |
| `UL001D08` → `DA08` | 92 | `VR` raw software version digits; `SP` V2/V5 model code | Machine; manual-derived fixture. Version digits remain raw until firmware confirmation. |
| `UL001D09` → `DA09` | 92 | `SY` seven flags for sampled syringe sizes 3/5/10/20/30/50/70 cc | Machine; manual-derived fixture. |

Blank numeric fields decode to JSON `null`; no value is guessed. A malformed length or checksum raises `IIProtocolError`; a bounded empty read raises `IITimeout`; an OS-reported device loss raises `IIDisconnected`; a controller `A2` rejection raises `IIUnavailable`. The fault cases and their exact expected write traces are named in the fixture file. Abort traces may contain only `CAN` and `EOT` after the permitted `UL` request and handshake bytes. The worker reads `D06` before and after the current-channel `D01`–`D04` group and marks those observations incomplete if the displayed channel changes or cannot be confirmed.

The retained reader's D01 object additionally exposes raw values, seconds, mode name, and the raw frame. The fixture comparison is field by field for common semantic values: `pressure_kpa`, `time_ms` ↔ `dispense_time_ms`, `vacuum_kpa` ↔ `vacuum_kpa_magnitude`, `mode_code`, and `product_name`. Its parser calls `int()` on numeric strings, so it cannot parse a blank numeric field; the new decoder maps that field to `null` as specified for unavailable data. This comparison is software evidence from the retained parser and a synthetic payload, not a new machine read.

## Site questions

M33 must confirm these shapes and scales on named machine/firmware combinations; how half-width Japanese product names are encoded; which uploads can return unavailable; actual supported channel count; whether `D06` can change between the two probes; response latency; and whether any fields vary by mode or controller version. Do not infer full channel coverage from a configured maximum alone.
