# M28 — Deliver complete records to MQTT within byte limits

Status: needs-triage
Completion: unverified

**Depends on:** [M26](M26-spool-recovery-and-identity.md), [M27](M27-multi-machine-scheduling.md).

**Outcome:** A selected broker receives every supported record family with stable identity, bounded messages, and independent retry state.

## Input and output contract

- **Input:** Pending records for one configured destination ID, its broker/topic/credential reference, encoded byte cap, and the spool's stable record IDs and scan snapshots.
- **Output:** Ordered version 1 MQTT chunks for every retained family; QoS 1 PUBACK for all required chunks causes acknowledgment of that destination assignment only.
- **Failure output:** Oversize encoding, lost PUBACK, outage, TLS failure, or restart leaves unconfirmed work pending with a visible reason. Retries preserve record/chunk identity and may duplicate a received message.
- **Boundary:** The forwarder reads spool assignments and reports confirmations. M26 owns backfill and pending reroute when this destination changes; collector progress is independent of broker availability until spool capacity is exhausted.

## Fixed work order and evidence

1. Use one configured `topic` as the exact MQTT topic for every chunk; QoS 1 and retain=false. Encode the complete version 1 spool record as canonical UTF-8 JSON, then base64. Each published JSON chunk is `{ "version":1, "record_id":string, "index":zero_based_int, "count":positive_int, "encoding":"base64-json-utf8", "data":base64_fragment }`. A subscriber sorts by `index`, requires one value for every index `0..count-1`, concatenates `data`, base64-decodes, parses UTF-8 JSON, and compares its `record_id` with the envelope. Keep fragment boundaries and chunk count stable across retries.
2. Enforce the configured 1,024–262,144 byte cap on each fully encoded UTF-8 chunk, including envelope. Publish in index order and acknowledge the lane only after PUBACK for every chunk. Failed publish, missing PUBACK within 30 seconds, disconnection, or restart retains the assignment; retry all chunks with the same ID. A new broker receives M26 backfill; endpoint change uses M26's pending-only reroute.
3. Evidence from a disposable broker includes the complete shared family manifest, Thai UTF-8 export/log larger than one chunk, exactly-at-cap and over-cap lengths, lost final PUBACK, broker outage/restart, wrong TLS credential, and endpoint change with a second lane present. Record topic, QoS, retain flag, byte length, chunk index/count, reassembled body equality, and pending/ack rows for each case.

## Scope and constraints

- Use QoS 1 with PUBACK before spool acknowledgment. Define topic/envelope schema and chunk reassembly identity for large JSON/TSV data.
- Enforce `max_payload_bytes` on the encoded UTF-8 message including envelope; do not slice by Unicode character count or assume fixed overhead (B07).
- Retry after connection loss and uncertain ack without deleting pending rows; downstream duplicate tolerance is documented. Broker target changes follow M26 identity policy.

## Acceptance checks

- [ ] A test broker receives and reassembles every supported family; payload bytes never exceed configured limit, including non-ASCII and large exports.
- [ ] Lost PUBACK, restart, and broker outage leave correct pending rows while other destinations continue.
- [ ] Acknowledgment occurs only after PUBACK for every required chunk, and duplicate deliveries retain stable IDs.
- [ ] TLS/credential errors are visible without logging secrets.
- [ ] A newly configured broker receives retained history within the visible backfill window; changing this broker reroutes only its pending assignments and keeps stable record IDs.

**Verification:** Use a disposable broker and inspect received UTF-8 byte lengths, chunk sets, spool rows, and retry traces.

## Comments

- 2026-09-28: MQTT QoS 1 adapter and byte-safe chunk checks exist. A disposable broker, lost PUBACK, restart, TLS, and reassembly checks remain open. Synthetic checks do not establish hardware acceptance.
- 2026-09-28: A temporary Mosquitto 2 broker received 64 chunks from a Thai-text synthetic export; reassembly matched the original record ID, each encoded message stayed within 1024 bytes, and the spool acknowledged after publish. Lost PUBACK, outage/restart, and TLS checks remain open. This was an ad hoc integration run, not the complete M32 matrix.
