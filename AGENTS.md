# Agent instructions

## Sources of truth

Before changing code, configuration, documentation, or ticket state, read [docs/ssot.md](docs/ssot.md). Use the authority for the kind of fact being changed, then update dependent docs in the same change. Keep hardware claims at their recorded evidence level.

## Modular programming

- Organize code by domain responsibility. Keep each module cohesive, expose a clear interface, and hide its internal details.
- Keep coupling low: connect modules through explicit contracts, inject device and external-service dependencies at boundaries, and avoid circular dependencies or shared mutable state.
- Keep each behavior in one owning module. Extract reusable modules when there is a real shared contract; avoid splitting trivial code into arbitrary pieces. Update the owning module's tests when its behavior changes.

## Agent skills

### Issue tracker

Local Markdown tickets live in `docs/tickets/`; that directory is the canonical tracker. Read [docs/agents/issue-tracker.md](docs/agents/issue-tracker.md) before creating, triaging, or completing tickets or specs.

### Triage labels

Ticket `Status:` values use the five Matt Pocock triage roles. Read [docs/agents/triage-labels.md](docs/agents/triage-labels.md) when changing a ticket's triage state.

### Domain docs

This is a single-context repo. Read [docs/agents/domain.md](docs/agents/domain.md) before domain modeling, architecture changes, or writing a spec.

## Documentation work

Use the `project-documentation` skill for project docs and the `writing-for-agents` skill when editing agent instructions. Keep `docs/development-plan.md` as navigation; each ticket owns its `Status:` and `Completion:` fields.
