# ADR 0001: Stable Influx point identity from the spool

Status: accepted for the software rebuild; external round-trip remains unverified.

M30 requires two records observed at the same instant to remain distinct, replay to be idempotent, and tag cardinality to stay bounded. Using `record_id` as a tag gives each record a new series. Using only the observation timestamp can overwrite a different record.

The SQLite spool assigns a stable `installation_id` when it is created and a strictly increasing `point_time_ns` to each record in the same transaction as record and delivery-row insertion. The candidate point time is the original UTC observation time in nanoseconds; if it is not greater than the previous assigned point time, the spool uses the previous value plus one nanosecond. It rejects a time outside InfluxDB's supported nanosecond range. The original `observed_at` remains in the complete JSON body.

Influx writes `musashi_record,installation_id=<id> body=<complete JSON> <point_time_ns>`. The only tag varies by spool installation rather than by record. A replay uses the stored identity; two records from the same spool cannot collide. Query consumers recover `record_id`, original observation time, nested values, raw safe payload, and scan state from the JSON field. A clock step backward can make point time later than observation time; consumers must use `observed_at` for source timing.

An active clone of one spool must not write to the same bucket while the original runs. A pre-migration pending record without point identity remains pending with an explicit delivery error rather than being acknowledged or assigned a guessed identity. The first disposable InfluxDB round trip and bucket-retention sizing are M30/M32 evidence gates.
