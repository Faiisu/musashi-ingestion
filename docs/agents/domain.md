# Domain documentation for agents

This is a single-context ingestion service. Read [the source-of-truth map](../ssot.md) before treating a document as a contract.

For the existing domain, use [architecture.md](../architecture.md) for design intent and [device-protocols.md](../reference/device-protocols.md) for the project's interpretation of the manufacturer manuals. Check the manuals for documented device facts. The current implementation under `src/musashi_ingestion/` establishes software behavior; its synthetic tests do not establish firmware compatibility.

If `CONTEXT.md` is added at the repository root, read its glossary before naming concepts in specs, tickets, and code. If an ADR exists under `docs/adr/`, read the decisions relevant to the change and surface conflicts explicitly. Create a glossary or ADR when a term or a durable decision is actually resolved; these files are not prerequisites for ordinary changes.
