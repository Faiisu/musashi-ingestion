# Issue tracker: local Markdown

The project's canonical implementation tickets are the files in [`docs/tickets/`](../tickets/). No Git remote or hosted issue tracker is configured in this checkout. Use these files for Matt Pocock workflows that say to fetch or publish an issue. Do not copy a ticket into `.scratch/` or another tracker.

## Files and fields

- Keep one issue per `docs/tickets/MNN-<slug>.md`. Preserve existing M numbers and gaps; allocate the next number after the highest existing ID for a new ticket.
- Put `Status: <triage role>` and `Completion: <delivery state>` directly below the title. Use the roles in [triage-labels.md](triage-labels.md). `Status:` answers who can take the next step; `Completion:` answers whether the acceptance criteria have been demonstrated.
- Use `Completion: not-started`, `unverified`, or `verified`. `unverified` means some work may exist but all acceptance checks have not been evidenced. Set `verified` only after recording the evidence against every acceptance check.
- Keep dependencies in the existing `**Depends on:**` field. Link blockers by ticket ID and add a path link when a reader would otherwise have to search.
- Append discussion or follow-up findings under `## Comments` in that ticket. Record decisions in the architecture or an ADR when they govern more than one ticket.
- Put a new feature spec in `docs/specs/<slug>.md` when a spec is needed. Link its implementation tickets from the spec. Existing architecture and the development plan remain separate explanation and navigation documents.

## Workflow

When a skill says “publish to the issue tracker,” create or update the canonical file above. When it says “fetch the ticket,” read that file and its comments. `docs/development-plan.md` links tickets by phase but does not duplicate their triage or completion states. Keep its links and dependencies current when adding or removing a ticket.

Some Matt Pocock skill templates hardcode `.scratch/<feature>/issues/` for local tickets. Substitute `docs/tickets/` for published implementation tickets in this repo; the hardcoded path is a generic template, not a second tracker.

Wayfinder may use `.scratch/` for temporary exploration maps. Such files are working notes; promote a decided implementation task into `docs/tickets/` and link it from the map. The ticket file remains the source of truth for delivery state.
