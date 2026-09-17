# Issue and Pull Request Labels

Use labels to record issue type, ownership, and review decisions. Tool-managed
and repository-specific labels are outside this contract and remain untouched.

## Contract rules

- A triaged issue carries exactly one `type:` label and one triage state. An
  unlabeled issue is untriaged; `needs-triage` means under evaluation.
- A non-draft PR with no verdict is the agent's to finalize. The draft flag is
  the "still being built" state; there is no label for it.
- The agent emits at most one `recommend-*` verdict per head. `recommend-revise`
  hands the PR back to its author; the other three hand it to the maintainer.
- Verdicts are recommendations. The agent never merges and never closes. Never
  rename `recommend-merge` to `ready-to-merge`: merge bots watch that string.
- `maintainer-approved` is set only on explicit maintainer direction and may
  coexist with a `recommend-*` label.
- A new push makes any verdict stale. The authority that set it clears and
  renews it.

## `/triage` role mapping

| Role | Issue label | PR label |
| --- | --- | --- |
| `bug` | `type:bug` | none |
| `enhancement` | `type:feature` | none |
| `needs-triage` | `needs-triage` | `recommend-triage` |
| `needs-info` | `needs-info` | `recommend-revise` |
| `ready-for-agent` | `ready-for-agent` | none |
| `ready-for-human` | `ready-for-human` | `recommend-merge` |
| `wontfix` | `wontfix` | `recommend-close` |

`type:task` is used for maintenance, refactor, documentation, and other work
that is neither a bug nor an enhancement. A non-draft PR without a verdict is
already ready for an agent, so it needs no PR label.

## Label meanings

### Issue labels

| Label | Meaning |
| --- | --- |
| `type:bug` | Reporting a defect to fix |
| `type:feature` | Requesting a new capability or improvement |
| `type:task` | Other work: maintenance, refactor, or docs |
| `needs-triage` | Under evaluation, not yet routed |
| `needs-info` | Waiting on the reporter for more information |
| `ready-for-agent` | Fully specified and ready for an AFK agent |
| `ready-for-human` | Requires human implementation |
| `wontfix` | Will not be actioned |

### Pull request verdicts

| Label | Meaning |
| --- | --- |
| `recommend-merge` | Agent finalized it and endorses maintainer review and merge |
| `recommend-close` | Agent recommends that the maintainer review and close it |
| `recommend-triage` | Code is sound; the maintainer must make the product or scope decision |
| `recommend-revise` | Review found defects or questions; the author must revise and push |
| `maintainer-approved` | Maintainer reviewed this head and approves merging after required checks pass |

Verdicts record decisions, not merge or close actions. A new commit makes an
applicable verdict stale: remove it and have the corresponding authority review
the new head before renewing it.
