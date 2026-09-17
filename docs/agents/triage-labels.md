# Issue and Pull Request Labels

Use labels to record whose turn it is and what they must do. Tool-managed and repository-specific labels are outside this contract.

## Issue labels

Every triaged issue carries exactly one `type:` label and one triage label. An issue with no triage label is fresh work for an agent to route; `needs-triage` is reserved for a maintainer decision.

The `type:` axis classifies the work:

| Label | Meaning |
| --------------- | ------------------------------------------ |
| `type: bug` | Reporting a defect to fix |
| `type: feature` | Requesting a new capability or improvement |
| `type: task` | Other work: maintenance, refactor, or docs |

The triage axis records whose turn it is:

| Role and label | Meaning |
| ----------------- | -------------------------------------------- |
| `needs-triage` | Maintainer needs to evaluate this issue |
| `needs-info` | Waiting on the reporter for more information |
| `ready-for-agent` | Fully specified and ready for an AFK agent |
| `ready-for-human` | Requires human implementation |
| `wontfix` | Will not be actioned |

## Pull request states

A non-draft pull request with no verdict is ready for an agent to finalize. A draft is still being built or iterated. `needs-info` is shared with issues and means the pull request is waiting on an outside human.

After reviewing a pull request, an agent applies exactly one mutually exclusive verdict:

| Verdict | Meaning |
| ------------------ | ------------------------------------------------------------------------- |
| `recommend-merge` | Agent endorses it for maintainer review and merge |
| `recommend-close` | Agent recommends that the maintainer review and close it |
| `recommend-triage` | Code is sound, but the maintainer must make the product or scope decision |
| `needs-changes` | Review found defects; the author must revise and push |

`needs-changes` stands in for GitHub's native "changes requested", which is unavailable when the reviewer is the author or an agent acting under the author's account. Put the defects in the review comments, not the label.

`maintainer-approved` records an explicit maintainer decision to merge after required checks pass. Apply it only at the maintainer's direction; it may coexist with an agent verdict because the labels record different authorities.

Verdicts record decisions, not merge or close actions. A new commit makes every applicable verdict stale: remove it and have the corresponding authority review the new head before renewing it.
