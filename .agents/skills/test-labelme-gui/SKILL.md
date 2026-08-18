---
name: test-labelme-gui
description: Run evidence-backed end-to-end GUI QA for Labelme with Computer Use. Use for manual regression checks, release acceptance, packaged-app validation, nightly or weekly GUI sweeps, visual and accessibility inspection, or reports of confusing desktop behavior that pytest cannot establish with human-level confidence.
---

# Test Labelme GUI

Test the real desktop surface as a user experiences it. Treat this as a complement to
`make test`: keep deterministic logic in pytest and spend Computer Use on native menus,
pointer and keyboard workflows, focus, dialogs, persistence, accessibility exposure,
visual states, and friction.

## Choose the run

Select the smallest profile that answers the request:

- `smoke`: startup plus one complete annotate-save-undo-restart journey. Use for skill
  development, a changed primary workflow, or a fast confidence check.
- `nightly`: all core workflows, error recovery, keyboard access, light and dark themes,
  and one clean-profile restart.
- `weekly`: nightly plus every shape type, alternate save modes, small-window layout,
  a returning profile, non-English UI, stress data, and a packaged build when available.
- `release`: weekly on every supported target OS and packaged artifact. Treat a missing
  artifact or platform as uncovered, not as a source-build pass.

Use the `source` lane for development feedback and the `packaged` lane for installer,
bundle identity, native menu, signing, and distribution confidence. Record both lane and
artifact identity. Read [scenarios.md](references/scenarios.md) and select every scenario
required by the profile plus scenarios touching the changed feature.

## Prepare an isolated run

Run from the repository root:

```bash
uv run --no-sync python .agents/skills/test-labelme-gui/scripts/prepare_run.py \
  --profile smoke --theme system
```

Keep the printed run directory. It contains copied inputs, writable outputs, an editable
config, isolated `QSettings`, evidence folders, a manifest, and a report skeleton. Preserve
it through reporting. A scheduled run may delete old run directories only under an
explicit retention policy.

For a source run, launch Labelme in a long-lived terminal session:

```bash
uv run --no-sync python .agents/skills/test-labelme-gui/scripts/launch_app.py \
  RUN_DIR raw
```

The launcher prints its PID and exact paths before starting Qt. On macOS, resolve the
process's full `.app` path from that PID and target that path with Computer Use. Abort as
an automation gap if multiple live GUI processes remain ambiguous. For a packaged lane,
launch the requested artifact with the prepared input and output paths; never silently
substitute the source lane.

Load the Computer Use skill before interacting with the app. Use `node_repl` with
`@oai/sky` for every UI action. Use the terminal only to launch, capture process output,
and verify on-disk artifacts.

## Execute with fresh evidence

For every scenario:

1. Write the precondition and expected user-visible outcome before acting.
2. Capture a full accessibility tree and screenshot at the starting checkpoint.
3. Prefer accessibility element actions. After every UI mutation, fetch fresh app state
   before choosing the next action. Use coordinates only when the accessibility action is
   missing or demonstrably fails, and record the fallback.
4. Exercise the human path. Include pointer and keyboard variants when the scenario names
   both; programmatic widget calls are outside this layer.
5. Assert the visible result and the durable result independently. Inspect output JSON,
   files, process status, or a clean restart when persistence or recovery is part of the
   claim.
6. Save checkpoint screenshots and accessibility text under the run's `evidence/`
   directory. Use stable names such as `A01-first-annotation/03-after-undo.png`.
7. Record the result immediately in `report.md` using
   [report-contract.md](references/report-contract.md).

A functional pass does not erase friction. Record extra clicks, unclear active states,
unexpected modality, weak feedback, truncated copy, focus surprises, hidden recovery,
and terms that require guessing. State the user's likely expectation and the obstacle.

## Apply the evidence gate

Classify observations before reporting:

- `defect`: the app violates an observable functional or data-integrity expectation.
- `ux-friction`: the task succeeds but the interaction is surprising, unclear, or costly.
- `visual`: clipping, hierarchy, contrast, theme, density, state, or layout quality.
- `accessibility`: missing or misleading name, role, value, focus order, or keyboard path.
- `performance`: visible latency, jank, unresponsiveness, or resource behavior.
- `automation-gap`: Computer Use or the harness cannot make or verify the claim.
- `positive`: behavior worth preserving.

Reproduce a defect from a fresh precondition before calling it verified. One reproduction
is enough for a crash, data loss, or corruption when the complete evidence is preserved;
other defects require two consistent attempts. Keep tool failures as `automation-gap`
until a human-visible or durable app failure independently confirms them.

Use `pass`, `fail`, `friction`, `inconclusive`, `blocked`, or `not-run` for scenario status.
Status and severity are separate. Follow the severity and evidence fields in the report
contract.

## Finish the run

1. Reopen saved annotations in a clean process for every persistence claim.
2. Gracefully quit the app and capture its exit status and stderr. Treat accessibility
   instrumentation warnings as harness evidence unless they also affect a user workflow.
3. Reconcile every selected scenario: no row may disappear. Explain every `blocked`,
   `inconclusive`, or `not-run` result.
4. Summarize coverage by profile, lane, OS, theme, profile state, and input class. Say
   `coverage-complete for <profile>` only when every required row ran in every declared
   environment. Never shorten that to `exhaustive` when matrix cells remain uncovered.
5. Lead the report with verified P0/P1 findings, then P2, UX/accessibility friction,
   automation gaps, and positive observations. Keep all screenshot, AX, log, and output
   paths clickable.

If the user asks to publish findings, first read `docs/agents/issue-tracker.md`. Prepare
one issue per independently fixable verified problem and stop for human review before
creating or modifying GitHub issues.
