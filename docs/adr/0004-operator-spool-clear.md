# ADR 0004: Operator clear of local spool history

Status: accepted

Operators can clear local spool history from the Recent data page after all machine and destination workers stop. The clear deletes records (including pending deliveries), delivery state, scan and fault history, and stored destination identities; destination configuration, the spool installation ID, and its Influx point-time sequence remain. This gives operators a deliberate recovery action for local spool data without implying that already delivered data can be recalled from MQTT, PostgreSQL, or InfluxDB.
