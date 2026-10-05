# Read-only device data catalog

For parsed output variables, spool records, and destination representations, see [machine output formats](machine-output-formats.md).

The application must collect every documented read-only data value that its configured machine can return, except the IV screen image. It must never change settings, switch channels, start dispensing, clear data, or run a diagnostic action. An HTTP `GET` is not automatically safe: the IV manual uses GET for many control commands.

The connected serial dispenser is identified by the operator as III; its live reads use the `UL` upload protocol documented in the scanned Model II manual. The [retained III example reader](../../examples/musashi_III_example/read_musashi.py) previously retrieved real values using `UL ... D01`; other upload codes are documented in the scanned manual and have since been exercised in a limited live cycle. IV status reads have succeeded; inventory and site acceptance remain incomplete. Synthetic fixtures must say so.

## Model II: RS-232C uploads

The scanned [II manual](../../examples/Instruction%20Manual%20Super%20%CE%A3CMII%20EN.pdf) lists `UL` as the upload request and `DA01`–`DA09` as responses (manual pages 80, 88–92). The request selects a channel and data number. The reference script confirms the `UL` handshake, checksum, and `D01` parser for channels 1–100. Use the same read-only upload path for the additional documented data numbers, with separate parsers and synthetic fixtures. Do not use download, mode, dispense, or clear commands.

| Upload | Data described by the manual | Scope |
| --- | --- | --- |
| `D01` / `DA01` | Dispensing pressure, time, vacuum, mode, and product name | Selected channel |
| `D02` / `DA02` | Syringe size and adapter tube length | Selected channel |
| `D03` / `DA03` | Sigma alpha, delta, and vacuum corrections | Selected channel |
| `D04` / `DA04` | Remaining-volume detection level and counter setting | Selected channel |
| `D05` / `DA05` | Current remaining volume | Machine status |
| `D06` / `DA06` | Currently displayed channel | Machine status |
| `D07` / `DA07` | Dispensing count | Machine status |
| `D08` / `DA08` | Software version and model specification | Machine information |
| `D09` / `DA09` | Syringe sizes currently sampled | Machine status |

**Coverage rule:** Read machine-level uploads and sweep all supported channels for `D01`–`D04`, subject to the machine's actual channel support. Record a value as unavailable when the controller rejects an upload; do not invent it. Confirm whether any `D01`–`D04` fields vary by machine model or mode during M33.

The scanned manual's printed pages 89–92 show `DA01`–`DA09` layouts. The [II read contract](../specs/model-ii-upload-contract.md) gives the field/unit map and links the synthetic fixtures. `DA06CHxxx` reports the displayed channel. The worker reads it before and after current-channel `D01`–`D04`; a changed or unconfirmed channel marks those records incomplete. `D02`–`D09` decoders are manual-derived and still require firmware confirmation.

The II example imports `database_handler`, which is missing here. Reuse its proven serial read behavior, not its database dependency. Save the operator-selected serial path, preferably `/dev/serial/by-id/...`; do not auto-select the first `/dev/ttyUSB*` device when several machines are connected. For local acquisition simulation, the III adapter also accepts an explicit pseudo-terminal path (`/dev/pts/<n>` on Linux or `/dev/ttysNNN` on macOS) printed by [`simulations/iii`](../../simulations/iii/README.md), and its fixed `socket://musashi-iii:9000` endpoint for Docker Compose dev. These are software test endpoints, not hardware evidence.

## Model IV: HTTP read endpoints

The [IV manual](../../examples/Instruction%20Manual%20Super%20%CE%A3CM%E2%85%A3%20EN%201.0.pdf), Communication Ethernet pages 19–35, lists the following retrieval endpoints. The controller uses a static IP, HTTP on port 1024–1026, and supports up to three simultaneous clients. It does not support HTTPS, so keep access on a restricted machine network.

| Data group | Allowed read endpoints | Response |
| --- | --- | --- |
| Live status | `/v1/status/main`, `/channel`, `/recipe`, `/error`, `/alarm`, `/totalCounter`, `/userCounter`, `/supply`, `/autoInc`, `/interval`, `/stopWatch`, `/tempUnit`, `/sigma`, `/remain`, `/dsubio/in`, `/dsubio/out` | JSON status, values, arrays, or `null` |
| Machine and clock | `/v1/info/machine/data`, `/v1/time` | JSON metadata; ISO 8601 time text on the connected firmware |
| Common settings | `/v1/info/common/{option}/data` and `/range`; `option` is `interval`, `correction`, `rs232c`, `ethernet`, `dsubio`, or `configure` | JSON values and ranges |
| Recipe settings | `/v1/info/recipe/data/all`, `/v1/info/recipe/range`; `/v1/info/recipe/data/{id}` as a fallback | JSON; `id` is 1–100 |
| Channel settings | `/v1/info/channel/data/all`, `/v1/info/channel/range`; `/v1/info/channel/data/{id}` as a fallback | JSON; `id` is 1–400 |
| Full export and log | `/v1/export/data`, `/v1/export/log` | JSON export and TSV log |
| Diagnostic results | `/v1/diagnosis/{type}/result`; `type` is `dispense`, `vacuum`, or `valve` | JSON result only; never start a test |

Endpoint citations below use the manual's printed “Communication Ethernet” page numbers. They are manual-derived evidence, not firmware verification.

| Exact read family | Manual citation and documented response | Current evidence |
| --- | --- | --- |
| Status `/v1/status/{main,channel,recipe,error,alarm,totalCounter,userCounter,supply,autoInc,interval,stopWatch,tempUnit,sigma,remain,dsubio/in,dsubio/out}` | Pages 26–31; JSON fields, values, arrays, and nullable recipe value are shown in endpoint examples | Manual-derived; sparse/null fixtures synthetic; firmware variants unknown |
| Machine `/v1/info/machine/data` | Page 33; JSON data format reference | Manual-derived; synthetic fixture |
| Clock `GET /v1/time` | Pages 20 and 22–23; GET acquires time; POST sets it | Manual-derived; synthetic fixture |
| Common `/v1/info/common/{option}/{data,range}` for six options | Pages 20 and 33–34; JSON data and range | Manual-derived; synthetic fixtures |
| Recipe all/range and `/data/{id}` | Pages 20 and 34; JSON; URL ID is 1–100 | Manual-derived; synthetic partial-list/range/item fixtures |
| Channel all/range and `/data/{id}` | Pages 20 and 35; JSON; URL ID is 1–400 | Manual-derived; synthetic partial-list/range/item fixtures |
| `/v1/export/data` and `/v1/export/log` | Page 22; JSON export and TSV text respectively | Manual-derived; synthetic fixtures; response sizes unverified |
| `/v1/diagnosis/{dispense,vacuum,valve}/result` | Pages 20 and 33; JSON `value` result | Manual-derived; synthetic fixture; result availability/shape variants unknown |
| Screen `/v1/screen` | Page 25; image acquisition | Manual-documented and excluded by scope |
| Control GET `/v1/current/*`, `/v1/clear/*`, `/v1/calibrate/*`, `/v1/diagnosis/{type}/{onoff}`, `/v1/logout` | Page 20; execution/update/registration operations, including diagnosis start/abort on page 33 | Manual-documented state-changing and excluded; synthetic allowlist rejection |
| POST `/v1/login`, `/v1/import`, `/v1/time` | Page 20; registration/import/set-time operations | Manual-documented and excluded; synthetic allowlist rejection |

The machine-information, common, recipe, and channel paths use the manual's JSON-format reference (pages 36–45). Exact firmware response variants remain unknown until M33. The manual lists HTTP ports 1024–1026, up to three simultaneous clients, and no HTTPS support (printed pages 7–8). Software bounds are a 2-second timeout and 1 MiB response limit; these are adapter limits, not controller guarantees. The adapter constructs requests from fixed kinds/options and typed IDs, so a caller-supplied path is rejected before any HTTP request.

`tests/fixtures/iv_responses.json` is the endpoint manifest: it records the expanded allowlist, representative typed-ID boundary fixtures, response kinds, evidence label, and named fault cases. Its fixtures are synthetic, never device captures. A partial `data/all` array intentionally represents missing IDs as unavailable; payload `no` is zero-based even though URL IDs are one-based.

In the live-status row, each abbreviated suffix after `/v1/status/main` has the same `/v1/status` prefix. In the common-settings row, `/range` means `/v1/info/common/{option}/range`. The adapter must expand these to exact paths before adding them to its allowlist.

The channel payload includes `disTime` (seconds), `disPress` (kPa), `disVacuum` (−kPa as printed in the manual), `shotMode`, `chName`, and `no`. URL `id` is 1–400, while payload `no` is 0–399. Keep those numbering schemes separate. The `data/all` endpoints cover the same items as the individual endpoints. The current implementation conservatively requests each configured ID as well; reducing those requests requires a verified reconciliation rule.

The IV manual's Communication Ethernet page 36 describes range replies as JSON with integer `min` and `max`. Recipe/channel payloads use arrays under `recipe`/`ch`; their `no` values start at zero. The adapter accepts nested ranges under `recipe.no` and `ch.no`, as observed on the connected IV on 2026-09-30, and the flat synthetic range shape. Configured counts bound the individual sweep and must fit within the returned capacity. All-data responses can contain IDs beyond a configured subset, within the protocol limits. Per-ID payload numbering is still validated. A read-only check on that date returned recipe IDs 0–99 and channel IDs 0–399; this establishes the reported range, not successful reads of every item. The clock endpoint returned ISO 8601 text with an offset; the adapter validates and preserves that text.

The [synthetic IV response manifest](../../tests/fixtures/iv_responses.json) includes a partial `data/all` result, per-ID responses, ranges, and a null status. Its fault cases are exercised by `tests/test_iv_contract.py`. The manifest is test data, not a controller capture.

Use an exact path allowlist with fixed parameters. Exclude `/v1/screen` because screen images are out of scope. Block `/v1/current/*`, `/v1/clear/*`, `/v1/calibrate/*`, `/v1/diagnosis/{type}/{onoff}`, `/v1/logout`, and every POST action. Do not follow redirects or accept a free-form URL. Some GET paths operate the machine, so method-only filtering is unsafe.

## Collection rules

- Poll changing status at the operator's per-machine interval, with a 1-second minimum. A cycle may take longer than its interval; report lag and skip overlapping cycles.
- Collect full channel/recipe/common inventories and large exports in bounded background sweeps. Between due status polls, advance inventory one request at a time; do not wait a full polling interval between inventory items. Record scan start, completion, partial failures, and last successful scan. Do not claim that all channels refresh every second.
- Keep distinct record types for status, channel/recipe settings, machine metadata, logs, and full data exports. Preserve the original response when safe, plus parsed fields, source path/upload code, machine ID, channel or recipe ID, timestamp, schema version, and quality. Redact any credential or sensitive setting before logging or publishing.
- On each destination, either deliver a record type with a documented encoding or mark that destination combination unsupported during configuration. Never silently drop a type. Large payload and retention policies belong to M20 and M26–M30.

## Checks deferred until hardware is available

The current protocol tests use synthetic fakes and the retained II example; no machine is connected. During M33, confirm each upload/endpoint, response size, field units, access rights, supported channels/recipes, latency, and behavior when values are unavailable. Add sanitized hardware captures alongside synthetic fixtures.
