# ADR 0002: Independent collection and destination rerouting

Status: accepted as rebuild intent; implementation and migration evidence remain open.

Collection, the durable spool, and forwarding are separate modules connected by explicit record and delivery contracts in one service. Collection commits observations even with no destination configured. A newly configured destination may receive retained history; retention can remove unassigned older observations, so the available backfill window must be visible. Changing one destination's endpoint moves only that lane's unacknowledged assignments to the new endpoint. Confirmed deliveries are not moved, and other lanes are unaffected. The record ID stays stable; an uncertain acknowledgment can cause delivery to both old and new endpoints. Consumers use that ID to recognize duplicates.

This replaces the old-target-pending policy in the provisional rebuild contract. It favors an operator's current destination selection and independent collection over preserving delivery to an endpoint that is no longer selected. The reroute must be atomic with respect to assignment and worker handoff, and its before/after counts must be auditable. It does not claim the current code implements rerouting or retained-history backfill.
