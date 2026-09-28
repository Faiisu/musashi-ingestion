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

Sizing rule: `required bytes = machines × (status bytes × status reads per day + inventory bytes per day) × outage days × destination copies + SQLite/WAL margin`. The 1 GiB value cannot prove 24 hours until real response sizes and destination selections are known. Reject or fault on capacity exhaustion and report the oldest pending age, queue count, and disk use.

The [agent execution contract](agent-execution-contract.md) fixes the software retention policy: `retention_max_history_records` defaults to 100 and bounds unassigned or fully acknowledged history eligible for pruning under quota pressure. Pending destination rows and incomplete scans remain protected. A newly configured destination backfills only records still retained; the oldest available record and pruned count must be visible. The current code retains at least the newest 100 acknowledged or unassigned records unless a retained scan references them, but it does not expose the configurable policy or backfill boundary. When protected history consumes the quota, acquisition faults visibly instead of silently deleting it. The site's required history and archival period remain M33 inputs.

## Security and delivery

Management topology, configuration, connection tests, Start, and Stop require a nonempty operator credential. Bind the API to loopback by default; exposing it on a protected network is an explicit deployment choice. Keep secret references out of responses and logs. Model IV's HTTP network must be restricted because the controller does not provide HTTPS. Request adapters construct paths and commands from typed allowlists only.

MQTT, PostgreSQL, and InfluxDB must each carry every accepted record family and scan coverage before release. Configuration must reject a destination that cannot preserve a family. Collection, spool, and forwarders are separate modules with explicit contracts in one service; collection works without a configured destination. Delivery is at least once. Adding a destination assigns retained history for backfill. Changing one destination's endpoint or credentials atomically moves only that lane's pending assignments to the new endpoint; confirmed deliveries and other lanes stay untouched. Preserve record IDs and report uncertain acknowledgments as possible duplicates. Acknowledge only after remote confirmation. Gaps, partial scans, and destination faults remain queryable. [ADR 0002](../adr/0002-independent-collection-and-destination-rerouting.md) records the routing decision; the current code still follows the old identity behavior.

## Release evidence

M32 must provide simulated source-to-destination and failure evidence for every family. M33 requires named device, firmware, sanitized capture, date, operator acceptance, and measured limits before any hardware-verified claim. The historical audit maps to regression gates as follows:

| Finding | Required gate |
| --- | --- |
| B01 | M22 first disconnected serial read terminates within timeout |
| B02 | M20/M21/M31 anonymous management access denied, including blank credential |
| B03 | M20/M26/M27 oversized/full spool faults stop reads visibly |
| B04 | M26 changing one destination atomically reroutes only that lane's pending assignments |
| B05 | M25 all IV range and sparse fallback coverage accounted |
| B06 | M30 nested values and same-timestamp IDs survive round trip |
| B07 | M28 UTF-8 encoded MQTT chunks obey byte limit |
| B08 | M27 first inventory starts promptly |
| B09 | M29 scan coverage is queryable after replay |
| B10 | M32 full fixture and destination matrix runs |

Unresolved site choices: actual channel/recipe support, controller firmware response variants, export/log sizes, interval under real load, permitted network route, selected destination retention, and outage duration. These are M33 acceptance inputs, not assumed facts.
