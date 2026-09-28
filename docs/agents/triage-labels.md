# Triage roles

For this local tracker, write one role in each ticket's `Status:` field. Triage state is separate from the ticket's `Completion:` field.

| Matt Pocock role | Ticket value | Meaning |
| --- | --- | --- |
| `needs-triage` | `needs-triage` | A maintainer must assess the next step. |
| `needs-info` | `needs-info` | A specific answer or external detail is required. |
| `ready-for-agent` | `ready-for-agent` | The task is specified and unblocked for an agent. |
| `ready-for-human` | `ready-for-human` | The next step requires a person or site access. |
| `wontfix` | `wontfix` | The task has been rejected; record why in the ticket. |

Use `Completion: verified` only when the ticket's acceptance evidence is recorded. A triage role alone never means that work is complete.
