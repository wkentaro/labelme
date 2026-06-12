# PR Loop

A label-driven loop that triages every open pull request and routes it back to
you through the `setup-github-labels` vocabulary. The labels **are** the state
and the comms channel; each tick derives everything from live GitHub state, so
there is no separate database to keep in sync.

Run it with:

```
/loop Run one PR-loop tick: follow docs/agents/pr-loop.md
```

(or `/loop 30m ...` for a fixed cadence). One tick **sweeps the whole queue**.

## The label state machine

Every open PR is owned by exactly one party. The loop only ever touches PRs that
are **its** turn, and never merges, closes, or force-pushes.

| PR state                                     | Owner       | Loop behavior              |
| -------------------------------------------- | ----------- | -------------------------- |
| draft                                        | author      | skip (still being worked)  |
| `do-not-merge`                               | you         | skip forever (hard block)  |
| `needs-info`                                 | contributor | skip (parked on a human)   |
| `ready-to-merge` (fresh)                     | you         | skip (in your ship queue)  |
| `recommend-close` (fresh)                    | you         | skip (in your triage pile) |
| `ready-to-merge`/`recommend-close` **stale** | agent       | clear verdict, re-review   |
| non-draft, no verdict, no block              | agent       | **process this tick**      |

A verdict endorses one specific diff. **Stale** = the PR's latest commit is newer
than the time the verdict label was applied. A push after a verdict invalidates
it, so the loop strips the label and re-reviews — this keeps your emerald queue
(`is:pr is:open label:ready-to-merge`) trustworthy.

## Two-way communication

- **Loop -> you:** a verdict label (applied automatically) plus a drafted review
  comment written to `tmp/pr-loop/staged-comments.md` for you to post.
- **You -> loop:**
  - merge or close a PR — removes it from the queue (your hand only).
  - remove a verdict label — sends the PR back for re-review next tick.
  - add `do-not-merge` — the loop never touches that PR again.
  - push a commit to your own PR — its verdict goes stale, auto re-reviewed.

Idempotency is free: a fresh verdict makes a PR no-longer-agent-turn, so it is
processed (and staged) exactly **once** per diff. No marker files needed.

## Tick algorithm

1. **Classify the queue.**

   ```bash
   gh pr list --state open --limit 100 \
     --json number,title,isDraft,author,labels,headRefOid
   ```

   A PR is **agent-turn** when `isDraft=false`, it carries none of
   `needs-info` / `do-not-merge`, and either it has no verdict label **or** its
   verdict is stale.

   Staleness check per verdicted PR:

   ```bash
   latest=$(gh pr view N --json commits -q '.commits[-1].committedDate')
   labeled=$(gh api repos/wkentaro/labelme/issues/N/timeline --paginate -q \
     'map(select(.event=="labeled" and (.label.name=="ready-to-merge" or .label.name=="recommend-close"))) | last | .created_at')
   # latest > labeled  ->  stale
   ```

   For a stale PR, `gh pr edit N --remove-label <verdict>` and treat it as
   agent-turn.

1. **Process the agent-turn set.**

   - **Community PRs (author != wkentaro):** dispatch **one review subagent per
     PR** (cap ~8 concurrent) so the dispatcher context stays clean. Each
     subagent is **review-only** — it never pushes to the fork. It assesses the
     diff against current `main`, CI status, mergeability/conflicts, scope fit,
     supersession by already-merged work, and staleness, then returns a
     structured verdict + a drafted comment (schema below).

   - **Your own non-draft PRs:** finalize sequentially in a worktree — rebase
     onto `main` if behind, run the tests, polish — then verdict. (Usually empty:
     your in-flight work stays draft, and the relicensing factory opens its PRs
     as drafts too, so the draft flag keeps both out of this path until ready.)

1. **Emit outcomes.** For each processed PR, apply exactly one verdict label
   automatically and append its drafted comment to the staging file:

   ```bash
   gh pr edit N --add-label "ready-to-merge"     # clean, mergeable, in-scope: just needs your click
   gh pr edit N --add-label "recommend-close"    # stale / superseded / out-of-scope / unfixable without author
   gh pr edit N --add-label "needs-info"         # a specific contributor action would unblock it
   ```

   When re-reviewing a stale PR, remove the old verdict first.

1. **Report & stop.** Print a one-line-per-PR summary (number, verdict, why).
   The loop re-invokes next tick to catch new and changed PRs. If no PR was
   agent-turn, report "queue drained" and idle.

## Verdict rubric

- `ready-to-merge` — only when genuinely clean: applies on `main`, CI green (or
  trivially fixable by you), in scope, no design concerns. The bar is "you read
  the comment and click merge."
- `recommend-close` — superseded by merged work, abandoned, out of project
  scope, or unmergeable without changes only the author can make. Your call; the
  loop never closes.
- `needs-info` — one concrete thing from the contributor would unblock it (a
  rebase, a test, a question answered). The drafted comment names that thing.

## Staged comments file

`tmp/pr-loop/staged-comments.md` (gitignored) is an append-only ledger. Each
processed PR gets one dated block:

```
## PR #1641 — ready-to-merge — 2026-06-12
> *This was generated by AI during triage.*

<drafted comment body>
---
```

Every contributor-facing comment opens with the AI-triage notice blockquote
(`> *This was generated by AI during triage.*`) so recipients know the review
was machine-drafted, matching the issue-tracker triage convention.

Post the ones you agree with (`gh pr comment N --body-file ...` or paste),
delete blocks as you clear them. Because a verdicted PR is no longer agent-turn,
the loop never re-stages it unless its verdict goes stale.

## Review subagent output schema

Each community-PR subagent returns:

```json
{
  "number": 1641,
  "verdict": "ready-to-merge | recommend-close | needs-info",
  "confidence": "high | medium | low",
  "reason": "one-line rationale for the dispatcher summary",
  "comment": "the contributor-facing review comment to stage"
}
```

## Guardrails

- Never merge, never close, never force-push a contributor branch. Verdicts are
  recommendations; merging and closing stay your hand.
- Review-only on forks: the loop reads community diffs, it does not write to
  them.
- Public comments are **staged, not posted** — they reach `tmp/` for your
  approval, never GitHub directly.
- `do-not-merge` is an absolute skip.
