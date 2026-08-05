# Issue tracker: GitHub

Issues and PRDs for this repo live as GitHub issues on `wkentaro/labelme`. Use the `gh` CLI for all operations.

## Conventions

- **Create an issue**: `gh issue create --title "..." --body "..."`. Use a heredoc for multi-line bodies.
- **Read an issue**: `gh issue view <number> --comments`, filtering comments by `jq` and also fetching labels.
- **List issues**: `gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'` with appropriate `--label` and `--state` filters.
- **Comment on an issue**: `gh issue comment <number> --body "..."`
- **Apply / remove labels**: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **Close**: `gh issue close <number> --comment "..."`

Infer the repo from `git remote -v` — `gh` does this automatically when run inside a clone.

## When a skill says "publish to the issue tracker"

Create a GitHub issue.

## When a skill says "fetch the relevant ticket"

Run `gh issue view <number> --comments`.

## Wayfinding operations

GitHub's native sub-issue / dependency APIs are not reliably reachable via `gh`, so wayfinder maps use a body convention here:

- **Map**: an issue labelled `wayfinder:map` plus a per-effort topic label `wayfinder:<effort>` (e.g. `wayfinder:config`). Body follows the wayfinder map template.

- **Ticket**: a child issue labelled `wayfinder:<type>` (`research`/`prototype`/`grilling`/`task`) **and** the same `wayfinder:<effort>` topic label. Body ends with a metadata block:

  ```
  Map: #<map-number>
  Blocked by: none            # or: #<n>, #<m>
  ```

- **Claim**: assign the ticket to the effort's dev (here, `wkentaro`) before any work. An open, **unassigned** ticket is unclaimed. The map issue is assigned to the owner from creation; that is ownership, not a claim.

- **Frontier query**: `gh issue list --label wayfinder:<effort> --state open --json number,title,assignees,body` then keep tickets that are unassigned **and** whose every `Blocked by:` issue is closed.

- **Resolve**: post the answer as a comment, `gh issue close`, then append a one-line gist + link to the map's Decisions-so-far.
