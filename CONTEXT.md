# Musashi ingestion language

This service reads Musashi machines and retains observations for independent delivery. These terms describe the data contract shared by collection, spool, and forwarders.

## Language

**Observation**:
A time-stamped result of one permitted device read, with its source, scope, quality, and evidence level. A failed read is a fault, not a substitute observation.

**Inventory scan**:
One bounded pass over an expected set of slower-changing machine reads, including II channel settings or IV settings, recipes, channels, exports, logs, and diagnostic results. It is separate from frequent live-status polling.
_Avoid_: Inventory as stock on hand

**Scan item**:
One expected read within an inventory scan, identified by its source and channel or recipe scope when applicable.

**Complete scan**:
A scan in which every expected item has a successful observation or an explicit unsupported result. A failed, skipped, or missing item leaves the scan partial; complete does not claim every value exists.
_Avoid_: Complete as a claim that every value exists

**Destination**:
A configured output endpoint of one kind: MQTT, PostgreSQL, or InfluxDB. Its configured ID identifies the delivery lane when its connection settings change.

**Pending delivery**:
An observation assigned to a destination lane but not yet confirmed by that destination. Retrying it preserves the observation's record ID.
