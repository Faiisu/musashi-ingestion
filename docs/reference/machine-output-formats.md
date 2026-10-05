# Machine output variables and formats

This page describes the data returned by the Musashi III and IV adapters and the record envelope written to the spool. The implementation under `src/musashi_ingestion/` is authoritative; the manufacturer manuals and synthetic fixtures provide the evidence noted below.

## Evidence and naming

The configured software models are `III` and `IV`. The III adapter uses the read-only `UL` / `DA01`–`DA09` serial layout documented in the retained Model II manual. A retained reader previously read `D01` from the connected machine identified by the operator as III. The other III fields are manual-derived and fixture-tested; confirm them on named firmware during site acceptance. IV status reads have succeeded, but complete inventory fields and firmware variants still need site acceptance.

Simulator responses and fixtures are synthetic. A record marked `documented` means the worker used a non-simulator configuration; it does not by itself mean every field has been hardware-verified. The worker marks simulator records `simulated`.

## Common record envelope

Each successful observation is a version 1 JSON record. The SQLite spool retains it while delivery is pending. After every assigned destination acknowledges it, the spool deletes the record; `/api/records` shows records still retained locally. Destination adapters send the envelope without changing its fields.

| Field | Meaning |
| --- | --- |
| `version` | Record schema version; currently `1`. |
| `record_id` | Stable unique ID assigned to the record. |
| `machine_id` | Configured machine ID. |
| `model` | `III` or `IV`. |
| `record_type` | `status`, `inventory`, `error`, or `scan`. |
| `source` | III upload code (or `Dxx:channel` for inventory), or IV endpoint path. A scan uses `inventory:<scan_id>`. |
| `observed_at` | UTC ISO 8601 timestamp. |
| `channel_id` | Channel number for a channel-scoped record; otherwise `null`. III channels and IV URL IDs are stored one-based. |
| `values.value` | Parsed III variables, or the complete IV JSON value / UTF-8 text response. |
| `values.raw` | Optional source response: III full response frame as lowercase hex; IV response body as UTF-8 text. |
| `values.scope` | `machine` or `channel`. |
| `values.quality` | Usually `good`; may be `unavailable`, `incomplete`, `partial`, or `error`. |
| `evidence_type` | `simulated` for simulator input; otherwise `documented` in the current worker. |

Example III status record (the values below are from the synthetic D01 fixture; `raw` is shortened for readability):

```json
{
  "version": 1,
  "record_id": "f86f2fc4-01ab-4a1c-9b86-d2bf6fcf3130",
  "machine_id": "iii-line-1",
  "model": "III",
  "record_type": "status",
  "source": "D01",
  "observed_at": "2026-10-05T03:00:00+00:00",
  "channel_id": 20,
  "values": {
    "value": {
      "pressure_kpa": 98.7,
      "dispense_time_ms": 654,
      "vacuum_kpa_magnitude": 3.21,
      "mode_code": 2,
      "product_name": "SIGMA"
    },
    "raw": "0231554c303230443031...",
    "scope": "channel",
    "quality": "good"
  },
  "evidence_type": "simulated"
}
```

Example IV status record: `values.value` is the whole decoded response body. The worker does not rename its JSON keys.

```json
{
  "version": 1,
  "record_id": "a5e8e6a0-0d4a-44ae-9b61-3036907e2f97",
  "machine_id": "iv-line-1",
  "model": "IV",
  "record_type": "status",
  "source": "/v1/status/main",
  "observed_at": "2026-10-05T03:00:00+00:00",
  "channel_id": null,
  "values": {
    "value": {"status": "Ready", "error": 0, "alarm": 0},
    "raw": "{\"status\":\"Ready\",\"error\":0,\"alarm\":0}",
    "scope": "machine",
    "quality": "good"
  },
  "evidence_type": "simulated"
}
```

The IV example body is synthetic fixture data, not a claimed response from a physical controller.

When a read fails, the worker creates an `error` record whose `values.value` identifies the exception type and whose `values.quality` is `error`; it does not replace the failed read with an older value. A successfully decoded top-level JSON `null` that is committed as an observation has `quality: "unavailable"`. An IV response object that contains a nested `null` remains a successful object unless the adapter returns top-level `null`.

## Musashi III outputs

The III transport sends a serial `UL` request and receives a framed ASCII `DAxx` response. The complete checked response frame is retained in `values.raw` as hex. `values.value` contains the parsed values below. Blank numeric fields in `D01` decode to JSON `null`; the parser does not substitute zero.

| Upload / response | Scope | `values.value` fields | Units / notes |
| --- | --- | --- | --- |
| `D01` / `DA01` | Channel | `pressure_kpa`, `dispense_time_ms`, `vacuum_kpa_magnitude`, `mode_code`, `product_name` | Pressure is raw `P / 10` kPa; time is milliseconds; vacuum is raw `V / 100` kPa magnitude; mode remains numeric code 0–3. Product name is trailing-space trimmed. |
| `D02` / `DA02` | Channel | `syringe_size_code`, `syringe_size_cc`, `adapter_tube_code`, `adapter_tube_m` | Syringe code maps to 3, 5, 10, 20, 30, 50, or 70 cc. Tube code maps to 0.5, 1, 1.5, or 2 m. |
| `D03` / `DA03` | Channel | `alpha_correction`, `delta_correction_percent`, `vacuum_correction_kpa` | Signed alpha correction; delta is percent; vacuum correction is raw signed value divided by 100 kPa. |
| `D04` / `DA04` | Channel | `remaining_detection_percent`, `remaining_detection_count` | Detection threshold and counter setting. |
| `D05` / `DA05` | Machine | `remaining_volume_percent` | Current remaining-volume percentage. |
| `D06` / `DA06` | Machine | `displayed_channel` | Displayed channel, 1–100. The worker reads it before and after channel data; a mismatch marks that channel's buffered status values `incomplete`. |
| `D07` / `DA07` | Machine | `dispense_count` | Eight-digit dispenser count returned as an integer. |
| `D08` / `DA08` | Machine | `software_version_raw`, `model_specification` | Version digits are retained as text (including leading zeroes); model is `V2` or `V5`. |
| `D09` / `DA09` | Machine | `sampled_syringe_sizes_cc` | List selected from `[3, 5, 10, 20, 30, 50, 70]` cc, in that order in the response bit field. |

Every poll commits machine status values `D05`–`D09` and the current displayed channel. It reads `D01`–`D04` for that displayed channel. The slower inventory scan reads `D01`–`D04` for each configured channel and records each result separately, with source such as `D01:20` and `channel_id: 20`.

## Musashi IV outputs

The IV transport issues allowlisted HTTP `GET` requests. JSON responses are decoded as JSON and retained unchanged in `values.value`; the original UTF-8 body is retained in `values.raw`. `/v1/time` and `/v1/export/log` are retained as UTF-8 text. No shared variable names are imposed on IV response bodies.

### Polled status variables

Each endpoint below is a separate `status` record with the exact path as `source`. The endpoint name describes its status family; the response body may be an object, array, scalar, or JSON `null` as allowed by the controller.

| Endpoint | Data family |
| --- | --- |
| `/v1/status/main` | Main machine state, including status, error, and alarm fields where returned. |
| `/v1/status/channel` | Current channel state. |
| `/v1/status/recipe` | Current recipe; a response may be `null` when no recipe is selected. |
| `/v1/status/error`, `/v1/status/alarm` | Current error and alarm information. |
| `/v1/status/totalCounter`, `/v1/status/userCounter` | Total and user counters. |
| `/v1/status/supply`, `/v1/status/remain` | Supply and remaining-volume state. |
| `/v1/status/autoInc`, `/v1/status/interval`, `/v1/status/stopWatch` | Auto-increment, interval, and stopwatch state. |
| `/v1/status/tempUnit`, `/v1/status/sigma` | Temperature-unit and Sigma state. |
| `/v1/status/dsubio/in`, `/v1/status/dsubio/out` | D-sub input and output state. |

The currently checked-in IV fixture uses examples such as `{"value": 0}`, `{"value": null}`, and `null`. These illustrate response shapes only. Firmware versions may use different field names or types; consult the returned `values.value` for the actual record and validate it against the connected controller before relying on an individual field.

### Inventory variables and response formats

| Endpoint family | Record output | Format / variable notes |
| --- | --- | --- |
| `/v1/info/machine/data` | `inventory` | Complete machine-information JSON body. |
| `/v1/time` | `inventory` | UTF-8 ISO 8601 time text; timezone offset is preserved. |
| `/v1/info/common/{interval,correction,rs232c,ethernet,dsubio,configure}/data` | `inventory` | Complete JSON settings body for the named common group. |
| `/v1/info/common/{option}/range` | `inventory` | Complete JSON range response, preserved without normalizing its fields. |
| `/v1/info/recipe/data/all`, `/v1/info/recipe/range` | `inventory` | Recipe collection (under `recipe`) and supported range. A recipe item's `no` is zero-based. |
| `/v1/info/recipe/data/{id}` | `inventory` | Per-recipe JSON response. URL IDs are 1–100; payload `no` is 0–99. |
| `/v1/info/channel/data/all`, `/v1/info/channel/range` | `inventory` | Channel collection (under `ch`) and supported range. |
| `/v1/info/channel/data/{id}` | `inventory` | Per-channel JSON response. URL IDs are 1–400; payload `no` is 0–399. |
| `/v1/diagnosis/{dispense,vacuum,valve}/result` | `inventory` | Result body only. The worker reads results and does not start a diagnosis. |
| `/v1/export/data` | `inventory` | Complete JSON export body. |
| `/v1/export/log` | `inventory` | UTF-8 tab-separated text; preserved as text, not converted into JSON rows. |

For channel settings, the manual documents fields including `no`, `disTime` (seconds), `disPress` (kPa), `disVacuum` (−kPa as printed), `shotMode`, and `chName`. The adapter preserves all returned fields without unit conversion. Recipe, common-setting, machine-information, status, and export JSON fields are likewise preserved; exact firmware-specific shapes remain to be confirmed at site acceptance.

The inventory worker also emits a `scan` summary record containing `scan_id`, `machine_id`, `group_name`, start/completion timestamps, expected items, per-item outcomes, and associated record IDs. A missing or unsupported item is represented in scan outcomes rather than filled with an invented value.

## Delivery representations

The acquisition record envelope remains the logical output for both machine models. The destinations encode it differently:

| Destination | Representation |
| --- | --- |
| MQTT | Each message is a versioned JSON chunk envelope with `record_id`, `index`, `count`, `encoding`, and base64 `data`. A record fits in one message when possible and is split into multiple chunks when necessary. |
| PostgreSQL | Full record in `musashi_records.body` as `jsonb`, with commonly queried envelope columns alongside it. |
| InfluxDB | A `musashi_iii` or `musashi_iv` point with envelope tags/fields, flattened scalar values, and a lossless JSON `body` field. |

## Source files and fixtures

- III field parser: [`devices/ii_decode.py`](../../src/musashi_ingestion/devices/ii_decode.py)
- IV endpoint and response parser: [`devices/iv.py`](../../src/musashi_ingestion/devices/iv.py)
- Record construction and acquisition behavior: [`pipeline/spool.py`](../../src/musashi_ingestion/pipeline/spool.py), [`runtime/supervisor.py`](../../src/musashi_ingestion/runtime/supervisor.py)
- III field map and evidence: [`model-ii-upload-contract.md`](../specs/model-ii-upload-contract.md), [`ii_uploads.json`](../../tests/fixtures/ii_uploads.json)
- IV endpoint catalog and evidence: [`device-protocols.md`](device-protocols.md), [`iv_responses.json`](../../tests/fixtures/iv_responses.json)
- Synthetic device services: [Musashi III simulator](../../simulations/iii/README.md), [Musashi IV simulator](../../simulations/iv/README.md)
