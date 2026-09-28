# Sources of truth

This project uses a source of truth for each kind of fact. No single document is the authority for the whole system. When sources disagree, use the authority in this map, then bring the other sources back into sync in the same change.

## Authority map

| Fact | Authoritative source | Role of other sources |
| --- | --- | --- |
| Runtime behavior, API routes, validation, config and record schemas, defaults, limits, and delivery behavior | `src/musashi_ingestion/` and its verification evidence | Architecture and tickets state intent; code establishes current behavior. Hardware and external service behavior remain unverified where no integration evidence exists. |
| Package and deployment definitions | `pyproject.toml`, `uv.lock`, `Dockerfile`, and `compose.yml` | A successful build does not establish site deployment or recovery. |
| Current operator configuration | Local `.env` and `config/config.json`, if present | These retained local files are data from the removed service. They do not define valid future schema or defaults. Never copy machine-specific secrets into docs. |
| Device protocol facts documented by the manufacturer | The relevant manual in `examples/` | `docs/reference/device-protocols.md` interprets those facts; device adapters enforce a current software allowlist. Firmware behavior remains unverified. |
| Product and architecture intent | Explicitly accepted decisions in `docs/architecture.md`, `docs/specs/rebuild-contract.md`, or an approved ticket | The working contract contains provisional numbers and unresolved site choices. |
| Ticket triage and delivery state | The `Status:` and `Completion:` fields plus acceptance evidence in each `docs/tickets/` file | `docs/development-plan.md` is a navigation map by phase; it does not copy ticket state. See the [local tracker rules](agents/issue-tracker.md). |

## Change procedure

1. Identify which kind of fact changed and consult its authority above.
2. If implementation is added or changed, update its code/configuration and relevant tests first; then update docs that describe it.
3. If intent is changing, update the architecture decision or ticket criteria before changing implementation. Resolve any disagreement explicitly.
4. Keep reference pages concise and link to the canonical source rather than maintaining duplicate schemas, defaults, or full option lists by hand. If a generated reference is practical, generate it from the implementation.
5. Distinguish documented, inferred, simulated, and hardware-verified device behavior. Mock or synthetic evidence must not be described as hardware verification.
6. When a claim cannot be confirmed from its authority, mark it unresolved or unverified instead of guessing.
7. For ticket work, update the canonical ticket file. Keep triage readiness separate from verified completion; record evidence before setting `Completion: verified`.

## Evidence vocabulary

These terms describe the evidence behind a technical claim. Ticket triage and completion use the separate fields defined in [the tracker rules](agents/issue-tracker.md).

- **Proposed:** design intent awaiting acceptance.
- **Planned:** work described by a ticket but not yet confirmed complete.
- **Implemented:** present in current code; this does not imply hardware validation or full ticket acceptance.
- **Hardware-verified:** exercised against the named real device/model and recorded with the relevant acceptance evidence.

See [AGENTS.md](../AGENTS.md) for the repository instructions that apply this policy to code and documentation changes.
