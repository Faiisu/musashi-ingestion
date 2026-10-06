# Rebuild contract (provisional)

This is the working contract for M17–M32. Manufacturer manuals establish device request facts; the current implementation and tests establish software behavior. Synthetic tests cannot establish compatibility with a particular machine or firmware. M33 must measure site values before release for that site.

## Coverage and exclusions

| Model | Required read families | Scope |
| --- | --- | --- |
| II | `UL` uploads `D01`–`D04` | Each supported channel, provisionally 1–100 |
| II | `UL` uploads `D05`–`D09` | Machine status and information |
| IV | All 16 `/v1/status/*` paths in the [catalog](../reference/device-protocols.md) | Live status |
| IV | Machine data and time; six common options with `/data` and `/range` | Inventory |
| IV | Recipe and channel `/data/all`, `/range`, and bounded per-ID fallback | Inventory; URL IDs 1–100 and 1–400 respectively |
| IV | Data export, TSV log, three diagnostic `/result` paths | Inventory |

## Read-family evidence matrix

This matrix is the contract for software coverage and release evidence. The page references are printed manual pages unless noted. `2 MiB / 2 s` is the provisional software bound from this contract, not a measured device capability. Manual-derived and simulated entries remain unverified on firmware until M33.

| Source | Item scope and request family | Manual page | Current software evidence | Bound | Release gate |
| --- | --- | --- | --- | --- | --- |
| II `UL D01` / `DA01` | Per channel, 1–100; pressure, time, vacuum, mode, product name | 89 | Retained example plus synthetic fixture (`ii_uploads.json`; `ii_decode.py`); field-by-field parser comparison passed in M18 | 128-byte frame; 2 s | M32 matrix; M33 firmware, units, name encoding, channel support |
| II `UL D02` / `DA02` | Per channel; syringe size and tube length | 89 | Manual-derived synthetic fixture | 128-byte frame; 2 s | M32 matrix; M33 firmware and supported values |
| II `UL D03` / `DA03` | Per channel; alpha, delta, vacuum corrections | 90 | Manual-derived synthetic fixture | 128-byte frame; 2 s | M32 matrix; M33 firmware and units |
| II `UL D04` / `DA04` | Per channel; detection level and counter | 90 | Manual-derived synthetic fixture | 128-byte frame; 2 s | M32 matrix; M33 firmware and supported values |
| II `UL D05` / `DA05` | Machine; remaining volume | 91 | Manual-derived synthetic fixture | 128-byte frame; 2 s | M32 matrix; M33 firmware and units |
| II `UL D06` / `DA06` | Machine; displayed channel and before/after channel probe | 91 | Manual-derived synthetic fixture; worker channel consistency behavior | 128-byte frame; 2 s | M32 channel-change case; M33 behavior and supported channel count |
| II `UL D07` / `DA07` | Machine; dispense count | 91 | Manual-derived synthetic fixture | 128-byte frame; 2 s | M32 matrix; M33 firmware |
| II `UL D08` / `DA08` | Machine; raw software version and model code | 92 | Manual-derived synthetic fixture; version remains raw | 128-byte frame; 2 s | M32 matrix; M33 firmware/model interpretation |
| II `UL D09` / `DA09` | Machine; sampled syringe-size flags | 92 | Manual-derived synthetic fixture | 128-byte frame; 2 s | M32 matrix; M33 firmware and supported values |
| IV status | 16 exact `/v1/status/*` reads; live machine/channel/recipe state | 20 (API list) | `STATUS`, `status_requests`, synthetic IV contract tests | 2 MiB response; 2 s | M32 all status paths; M33 named firmware, values, latency |
| IV machine and time | `/v1/info/machine/data`, `/v1/time` | 20 (API list) | `STATIC`, `inventory_requests`; synthetic responses | 2 MiB; 2 s | M32 both paths; M33 firmware and clock behavior |
| IV common data | Six `/v1/info/common/{option}/data` paths | 20 (API list) | `COMMON`, `path_for`; synthetic responses | 2 MiB; 2 s | M32 every option; M33 firmware and values |
| IV common ranges | Six `/v1/info/common/{option}/range` paths | 20 (API list) | `COMMON`, `path_for`; synthetic range responses | 2 MiB; 2 s | M32 every option/range; M33 firmware and ranges |
| IV recipe list and range | `/v1/info/recipe/data/all`, `/range`; payload IDs 0–99 | 20 (API list); 36 (range shape) | `STATIC`; sparse/range synthetic cases | 2 MiB; 2 s | M32 complete/sparse coverage; M33 actual recipe count and firmware |
| IV recipe item fallback | `/v1/info/recipe/data/{id}`, URL IDs 1–100 | 20 (API list) | `path_for` typed bounds; synthetic per-ID response | 2 MiB; 2 s | M32 fallback and out-of-range cases; M33 actual recipe count |
| IV channel list and range | `/v1/info/channel/data/all`, `/range`; payload IDs 0–399 | 20 (API list); 36 (range shape) | `STATIC`; sparse/range synthetic cases | 2 MiB; 2 s | M32 complete/sparse coverage; M33 actual channel count and firmware |
| IV channel item fallback | `/v1/info/channel/data/{id}`, URL IDs 1–400 | 20 (API list) | `path_for` typed bounds; synthetic per-ID response | 2 MiB; 2 s | M32 fallback and out-of-range cases; M33 actual channel count |
| IV exports | `/v1/export/data` JSON and `/v1/export/log` TSV | 20 (API list) | `STATIC`; synthetic JSON/TSV and size-fault cases | 2 MiB; 2 s | M32 full export/log bodies and oversize; M33 measured sizes and firmware |
| IV diagnostic results | `/v1/diagnosis/{dispense,vacuum,valve}/result` only | 20 (API list) | `DIAGNOSIS`, typed result paths; synthetic responses | 2 MiB; 2 s | M32 result paths; M33 firmware; start/action paths stay excluded |

Evidence paths name synthetic software evidence, not hardware captures. The IV manual lists exact Web API paths on printed page 20; endpoint response details continue through pages 21–36. The II page references identify the upload field layouts. The [protocol catalog](../reference/device-protocols.md) and [model contracts](model-ii-upload-contract.md) carry the interpretation and fixture links.

## Contract review record

| Input reviewed | Evidence checked | Result and unresolved facts |
| --- | --- | --- |
| II manual | Scanned manual, printed pp. 78, 81–83, 89–92; [II protocol catalog](../reference/device-protocols.md) | Pass for documented serial settings, upload framing, checksums and DA01–DA09 layouts. Firmware encoding, availability and physical channel support remain M33 questions. |
| IV manual | Scanned manual, printed Communication Ethernet pp. 19–36; exact API list on p. 20 | Pass for read-path inventory and explicit exclusions; GET may operate the machine, so only acquisition paths are allowed. Response variants and actual configured counts remain M33 questions. |
| Retained III example | `examples/musashi_III_example/read_musashi.py` and documented `D01` use | Pass as evidence only for the prior D01 reader; its missing database dependency is not reused. Other uploads remain manual-derived. |
| Audit B01–B10 | [Historical backend audit](../audits/backend-2026-09-28.md) and primary regression map below | Pass as a ticket assignment; every finding has one primary owner. Current acceptance still depends on each ticket's evidence. |
| ADR 0001 | [Stable Influx point identity](../adr/0001-influx-point-identity.md) | Pass as accepted software intent. Disposable Influx round trip and replay remain unverified in M30/M32. |
| ADR 0002 | [Independent collection and rerouting](../adr/0002-independent-collection-and-destination-rerouting.md) | Pass as accepted software intent. Destination-free collection, retained backfill, and atomic pending-only reroute remain implementation gates. |
| ADR 0003 | [Shared operator session login](../adr/0003-shared-session-login-for-the-operator-console.md) | Pass as accepted management-access intent. M36/M37 implementation and protected-device access remain open. |

This is an implementer review record, not maintainer acceptance. M17 remains unverified until a maintainer accepts the contract review.

All records retain source, scope, UTC time, stable ID, evidence level, quality, and raw safe response when within limits. An [inventory scan](../../CONTEXT.md) is complete when every expected read has a successful observation or an explicit unsupported result. Failed, missing, or skipped reads leave it partial; item outcomes remain visible even for a complete scan. No IV screen image, II download/control command, IV control GET, POST, redirect, or arbitrary path is permitted. A status response is never evidence that an inventory is complete.

## Provisional operating envelope

These values are implementation guardrails, not measured hardware capacities. Code/configuration own actual defaults; M33 owns site-specific validation.

| Limit | Provisional target | Reason and site check |
| --- | --- | --- |
| Configured machines | 8 | Bounds worker count; confirm actual II/IV mix and CPU use. |
| Status interval | Minimum 1 s; default 1 s | Existing product intent; measure full status-cycle duration. |
| Request timeout | 2 s | Bounds a stalled request; measure slowest normal response. |
| Inventory work unit | 1 request between status opportunities | Prevents a 400-channel sweep monopolizing the request lane. |
| Raw response and record | 2 MiB each | A single read cannot consume an unbounded spool; measure exports/logs before raising. Oversize is a fault, never truncation. |
| MQTT encoded message | 256 KiB | Byte cap includes chunk envelope; verify broker's actual limit. |
| Influx encoded line | 16 MiB | Covers escaped form of the accepted 2 MiB JSON record; verify with a disposable bucket and site settings. |
| Spool allocation | 1 GiB including margin for SQLite WAL and pending write | Enforce a lower logical data quota than allocated disk space; confirm filesystem free space. |
| Outage target | 24 h for status plus one inventory, subject to sizing | Must be recalculated from measured record sizes and enabled destinations. |
| Fresh inventory target | Within configured refresh interval after a complete scan | Partial scans remain visible; confirm interval and scan duration. |
| Delivery lag target | Under 60 s while destinations are available | Measure during M32 and M33; outage age is reported separately. |

Sizing rule: `required bytes = machines × (status bytes × status reads per day + inventory bytes per day) × outage days × destination copies + SQLite/WAL margin`. The 1 GiB value cannot prove 24 hours until real response sizes and destination selections are known. On spool quota exhaustion, evict oldest committed records to continue collection and report eviction count, oldest pending age, queue count, and disk use. Actual disk/SQLite write failures remain faults.

The [agent execution contract](agent-execution-contract.md) fixes the software retention policy: after every assigned destination acknowledges a record, its body and delivery rows are deleted. Unassigned history remains available for later destination registration until quota eviction. Under quota pressure, records are evicted in oldest commit order, including pending records; their delivery rows are removed and scan record links are cleared while scan outcomes and incomplete scan metadata remain available. A newly configured destination backfills only records still retained. This is a delivery buffer, not an archive: already delivered rows cannot be recovered from the spool after a destination loses data. Quota eviction keeps acquisition running and reports a persistent `evicted_record_count`; discarded pending data will not be delivered later. Actual SQLite write failures or a new record that cannot fit after eviction still fault acquisition. The site's required history and archival period remain M33 inputs.

## Security and delivery

Management topology, configuration, connection tests, Start, and Stop require an authenticated browser session. The browser-facing API uses the shared local `admin` account; its default password is `00000000` and may be overridden through environment secrets. No forced password change, login throttling, or account lockout is planned. This weak default is accepted only for a deployment behind a restricted network; bind the API to loopback by default and require explicit deployment evidence before exposing it on a protected network. Use same-origin session cookies and CSRF protection. Sessions expire after 8 hours idle or 24 hours total and are invalidated on server restart. External API clients and bearer-token compatibility are out of scope. Keep secret references out of responses and logs. Model IV's HTTP network must be restricted because the controller does not provide HTTPS. Request adapters construct paths and commands from typed allowlists only.

MQTT, PostgreSQL, and InfluxDB must each carry every accepted record family and scan coverage before release. Configuration must reject a destination that cannot preserve a family. Collection, spool, and forwarders are separate modules with explicit contracts in one service; collection works without a configured destination. Delivery is at least once. Adding a destination assigns only records still retained for backfill. Changing one destination's endpoint or credentials atomically moves only that lane's pending assignments to the new endpoint; confirmed deliveries and other lanes stay untouched. Delete a record only after every destination assigned to it has confirmed delivery. Preserve record IDs while records are pending and report uncertain acknowledgments as possible duplicates. Gaps, partial scans, and destination faults remain queryable. [ADR 0002](../adr/0002-independent-collection-and-destination-rerouting.md) records the routing decision.

## Release evidence

M32 must provide simulated source-to-destination and failure evidence for every family. M33 requires named device, firmware, sanitized capture, date, operator acceptance, and measured limits before any hardware-verified claim. The historical audit maps to regression gates as follows:

| Finding | Primary ticket and regression case | Related gates |
| --- | --- | --- |
| B01 | M22 — first disconnected II read terminates within timeout | — |
| B02 | M36 — invalid or missing session denies management access; explicitly blank login credentials prevent startup | M20, M21, M31, and M34 auth/recovery checks |
| B03 | M26 — full quota evicts oldest records and continues acquisition; actual write failures remain visible | M20 commit bounds; M27 worker-stop behavior |
| B04 | M26 — endpoint change reroutes only that lane's pending assignments atomically | — |
| B05 | M25 — IV ranges, sparse `data/all`, fallback, and expected-item outcomes | — |
| B06 | M30 — complete nested body and same-time distinct IDs round-trip | — |
| B07 | M28 — UTF-8 encoded chunk including envelope stays within byte cap | — |
| B08 | M27 — first inventory starts promptly | — |
| B09 | M29 — scan state and item coverage are queryable after replay | — |
| B10 | M32 — full fixture × destination matrix and release failure cases | — |

Unresolved site choices: actual channel/recipe support, controller firmware response variants, export/log sizes, interval under real load, permitted network route, selected destination retention, and outage duration. These are M33 acceptance inputs, not assumed facts.
