# M30 — Deliver lossless supported records to InfluxDB

Status: needs-triage
Completion: unverified

**Depends on:** [M26](M26-spool-recovery-and-identity.md), [M27](M27-multi-machine-scheduling.md).

**Outcome:** A consumer can retrieve every accepted record family without nested-value loss or point collision.

## Input and output contract

- **Input:** Pending complete envelopes and scan snapshots for one InfluxDB destination ID, stored installation/point identity from [ADR 0001](../adr/0001-influx-point-identity.md), bucket settings, token reference, and encoded request limit.
- **Output:** Confirmed points whose queried body reconstructs each accepted record and scan outcome, including nested values, original observation time, source, units, and record ID; remote confirmation acknowledges only this destination's assignment.
- **Failure output:** Collision risk, unsupported/oversized encoding, timeout, or outage leaves the item pending with a visible fault. Retrying one record uses the same point identity; a distinct record gets a distinct point.
- **Boundary:** The spool assigns point identity and owns backfill/reroute; this forwarder encodes and confirms writes. An earlier spool format is an upgrade input only if a real retained database requiring migration is identified.

## Fixed work order and evidence

1. Use the [ADR 0001](../adr/0001-influx-point-identity.md) schema: measurements `musashi_iii` and `musashi_iv`; bounded machine/source/scope tags; source-prefixed scalar fields for parsed values; and a string `body` field containing the complete record for lossless recovery. Encode numeric leaves consistently as floats to prevent conflicts between integer/float variants. Use spool `point_time_ns` as timestamp, synchronous writes, and acknowledge only after server acceptance. Query the fields and body back; compare the complete body including nested values, raw TSV, source, quality, original `observed_at`, and scan outcomes.
2. Set `max_payload_bytes` default and minimum to 16,777,216. Measure the UTF-8 bytes of the escaped final line before sending; one accepted 2,097,152-byte record must fit or the write remains pending with an explicit oversize fault. Never split a record into points or omit a field. Do not add `record_id` as a tag. Retry uses the identical line and point time; distinct IDs with equal observation time have distinct stored point times.
3. Evidence in a disposable bucket includes every shared family, a worst-case escaping record, same-time distinct IDs, exact replay, unavailable/partial scan, network outage and restart, retained-history backfill, and pending-only reroute to a new bucket. Record the line byte length, tag set, queried full JSON equality, point count, and spool pending/ack states. A legacy pending record without point identity stays pending with `MissingPointIdentity`; migration is required only if an actual retained old spool is supplied as input.

## Scope and constraints

- Use the complete JSON body string as the lossless source for nested JSON, TSV logs, scan completion, units, and model-specific values. Structured scalar fields supplement it for direct querying. If Influx cannot retain a family within limits, reject that destination combination before Start; never acknowledge silently omitted fields (B06).
- Prove point identity for distinct records with the same machine, type, and timestamp, while replaying one record produces the intended idempotent result. Keep tag cardinality bounded.
- Enforce request and payload limits, timeout, TLS, and token redaction; acknowledge only on confirmed acceptance.

## Acceptance checks

- [ ] Round-trip queries recover separate III/IV measurements, bounded tags, typed scalar values, and each supported fixture family from the complete body, including nested status, export/log, scan state, source, and units.
- [ ] Two distinct record IDs at the same observation timestamp remain distinguishable; replay behaves as specified.
- [ ] Unsupported or oversized payloads fail configuration or remain pending with explicit fault, never silently drop content.
- [ ] The final encoded line stays within the configured 16 MiB minimum for the worst accepted record or an oversize write stays pending with a visible fault.
- [ ] Outage/restart preserves pending rows and does not block MQTT/PostgreSQL.
- [ ] A new bucket receives retained history within the visible window; changing this destination reroutes only its pending rows while preserving stored point identity for replay.

**Verification:** Use a disposable InfluxDB bucket; compare queried data with fixtures, replay IDs, and same-timestamp cases.

## Comments

- 2026-09-28: The current release scope starts from the current spool format. Compatibility work for an older spool becomes an upgrade requirement only if a retained database needing it is identified; the current Influx round trip and reroute/backfill checks remain open.
- 2026-09-28: Influx line encoding retains complete JSON and record ID identity. Disposable bucket round trip, replay, and outage checks remain open. Synthetic checks do not establish hardware acceptance.
- 2026-09-28: [ADR 0001](../adr/0001-influx-point-identity.md) replaces per-record ID tags with a durable installation tag and monotonic point time assigned by SQLite. Synthetic same-observation-time records have distinct point times and no per-record tag. Disposable bucket query/replay and outage evidence remain open under the current socket/Docker restriction.
- 2026-09-28: Audit found that a pre-identity pending Influx row would block newer rows for that target. Status now exposes the affected record ID and reason. The current rebuild has no migration or operator recovery path for such a row; resolve this before claiming upgrade/recovery acceptance. No deployed legacy spool has been identified in this checkout.
- 2026-09-30: Structured III/IV measurements and source-prefixed scalar fields are implemented. A live bucket query returned `musashi_iii` field `value_d01_pressure_kpa` and `musashi_iv` field `value_v1_status_supply_value`; the complete disposable family/replay/outage round trip remains unverified.
