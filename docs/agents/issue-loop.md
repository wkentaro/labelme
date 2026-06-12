# Issue Loop

A label-driven loop that triages every open issue and routes it back to you
through the `setup-matt-pocock-skills` triage vocabulary (see
`docs/agents/triage-labels.md`). The labels **are** the state and the comms
channel; each tick derives everything from live GitHub state, so there is no
separate database to keep in sync. This is the issue-side twin of
`docs/agents/pr-loop.md`.

Run it with:

```
/loop Run one issue-loop tick: follow docs/agents/issue-loop.md
```

(or `/loop 30m ...` for a fixed cadence). One tick **sweeps the whole queue**.

## The label state machine

Every open issue carries at most one **state** label and, once triaged, exactly
one **category** label (`type: bug` / `type: feature` / `type: task`). The loop
only ever touches issues that are **its** turn, and never closes an issue.

| Issue state                                 | Owner       | Loop behavior                           |
| ------------------------------------------- | ----------- | --------------------------------------- |
| unlabeled (never triaged)                   | agent       | **process this tick** (initial triage)  |
| `needs-triage`                              | agent       | **process this tick** (evaluate, route) |
| `needs-info`, no reporter reply since notes | reporter    | skip (parked on a human)                |
| `needs-info`, reporter replied since notes  | agent       | **re-triage this tick**                 |
| `ready-for-agent`                           | implementer | skip (handed to the build pipeline)     |
| `ready-for-human`                           | you         | skip (your implementation queue)        |
| `wontfix`                                   | you         | skip (terminal; your hand to close)     |

`needs-triage` is the intake state the loop drains: an unlabeled or
`needs-triage` issue is the agent's to evaluate and route to a destination.
`ready-for-agent` / `ready-for-human` are destinations the loop hands off and
does not implement — triage-only, the way `pr-loop` is review-only.

A `needs-info` issue goes **stale** the moment the reporter replies: a comment
from anyone other than the maintainer/agent, newer than the time the triage
notes were posted, means the loop must re-triage it. A reply on `needs-info` is
the issue analog of a push on a verdicted PR — it invalidates the parked state
and sends the issue back for another look, keeping your `needs-info` pile
trustworthy (every issue in it is genuinely waiting on its reporter).

## Two-way communication

- **Loop -> you:** a state label + a category label (applied automatically),
  plus a drafted comment (triage notes or an agent brief) written to
  `tmp/issue-loop/staged-comments.md` for you to post.
- **You -> loop:**
  - move an issue to `ready-for-agent` / `ready-for-human` / `wontfix`, or close
    it — removes it from the agent-turn queue (your hand only).
  - set an issue back to `needs-triage` — sends it back for re-triage next tick.
  - a reporter replying on a `needs-info` issue — its parked state goes stale,
    auto re-triaged.

Idempotency is free: a fresh destination label makes an issue no-longer-agent-
turn, so it is processed (and staged) exactly **once** per state. No marker
files needed.

## Tick algorithm

1. **Classify the queue.**

   ```bash
   gh issue list --state open --limit 200 \
     --json number,title,labels,author,updatedAt
   ```

   An issue is **agent-turn** when it is unlabeled, carries `needs-triage`, or
   carries `needs-info` with a reporter reply newer than the triage notes.
   Issues carrying `ready-for-agent` / `ready-for-human` / `wontfix` are skipped.

   Staleness check per `needs-info` issue (did the reporter reply?):

   ```bash
   labeled=$(gh api repos/wkentaro/labelme/issues/N/timeline --paginate -q \
     'map(select(.event=="labeled" and .label.name=="needs-info")) | last | .created_at')
   last=$(gh issue view N --json comments -q '.comments[-1] | "\(.author.login) \(.createdAt)"')
   # last comment author != wkentaro  AND  its createdAt > labeled  ->  stale
   ```

   For a stale `needs-info` issue, treat it as agent-turn and re-triage it.

1. **Process the agent-turn set.** Dispatch **one triage subagent per issue**
   (cap ~8 concurrent) so the dispatcher context stays clean. Each subagent
   follows the `/triage` skill: read the full issue (body, comments, labels,
   reporter, prior triage notes), explore the codebase via the domain glossary,
   and for bugs **attempt reproduction** before anything else. It then returns a
   structured recommendation — one category, one destination state, and a
   drafted comment (schema below). Subagents **read** the issue tracker; they do
   not post or close.

1. **Emit outcomes.** For each processed issue, apply exactly one category label
   and one destination state label automatically, and append its drafted comment
   to the staging file:

   ```bash
   gh issue edit N --add-label "type: bug"          # or "type: feature" / "type: task"
   gh issue edit N --add-label "ready-for-agent"    # fully specified, AFK-ready
   gh issue edit N --add-label "ready-for-human"    # real, but needs human judgment to build
   gh issue edit N --add-label "needs-info"         # one concrete reporter action would unblock it
   gh issue edit N --add-label "wontfix"            # not actionable; you review and close
   ```

   When re-triaging a stale `needs-info` issue, remove the old state label first
   (`gh issue edit N --remove-label needs-info`). Never leave two state labels on
   one issue — if a destination conflicts with an existing state label, flag it
   in the summary and leave the issue on `needs-triage` rather than guessing.

1. **Report & stop.** Print a one-line-per-issue summary (number, category,
   destination, why). The loop re-invokes next tick to catch new issues and
   reporter replies. If no issue was agent-turn, report "queue drained" and idle.

## Triage rubric

The destination is the agent's recommendation; the maintainer can always
override by changing the label.

- `ready-for-agent` — fully specified and AFK-ready: a fresh agent could pick it
  up with zero added context. The staged comment is an agent brief (see the
  `/triage` skill's AGENT-BRIEF reference). A confirmed reproduction makes a far
  stronger brief — include the failing code path.
- `ready-for-human` — real and worth doing, but blocked on judgment the agent
  can't make: design decisions, external access, or manual testing. Same brief
  structure as `ready-for-agent`, plus a line on why it can't be delegated.
- `needs-info` — one concrete thing from the reporter would unblock it (repro
  steps, a version, a sample file). The staged comment is triage notes that
  capture what's established and name the specific questions.
- `wontfix` — out of project scope, superseded, or unfixable. The staged comment
  is a polite explanation. The loop applies the label but **never closes** —
  closing stays your hand, the way `pr-loop` never merges.

## Staged comments file

`tmp/issue-loop/staged-comments.md` (gitignored) is an append-only ledger. Each
processed issue gets one dated block:

```
## Issue #2160 — ready-for-agent — 2026-06-12
> *This was generated by AI during triage.*

<drafted agent brief or triage notes>
---
```

Every contributor-facing comment opens with the AI-triage notice blockquote
(`> *This was generated by AI during triage.*`) so recipients know the triage
was machine-drafted, matching the `/triage` skill convention.

Post the ones you agree with (`gh issue comment N --body-file ...` or paste),
delete blocks as you clear them, and close the `wontfix` ones yourself. Because a
destination-labeled issue is no longer agent-turn, the loop never re-stages it
unless you send it back to `needs-triage` or the reporter replies on a
`needs-info` issue.

## Triage subagent output schema

Each triage subagent returns:

```json
{
  "number": 2160,
  "category": "type: bug | type: feature | type: task",
  "destination": "ready-for-agent | ready-for-human | needs-info | wontfix",
  "confidence": "high | medium | low",
  "reason": "one-line rationale for the dispatcher summary",
  "comment": "the reporter-facing agent brief or triage notes to stage"
}
```

If a subagent can't confidently settle on a destination, it returns
`"destination": "needs-triage"` with its reasoning in `reason`; the dispatcher
leaves the issue on `needs-triage` for you rather than mislabeling it.

## Guardrails

- Never close an issue. `wontfix` is a label; closing stays your hand, like
  `pr-loop` never merging or closing.
- Read-only on the tracker: subagents read issues and the codebase, they do not
  post comments or change labels — only the dispatcher writes labels, and only
  the maintainer posts comments and closes.
- Public comments are **staged, not posted** — they reach `tmp/` for your
  approval, never GitHub directly.
- One state label at a time. Conflicting states get flagged and parked on
  `needs-triage`, never silently overwritten.
