---
name: test-labelme-gui
description: Drive the real Labelme desktop app with computer use and report evidence-backed findings. Use for GUI regression after a change, release acceptance, visual or accessibility inspection, or a reported desktop behavior that pytest cannot reproduce.
---

# Test Labelme GUI

Test what a user sees and touches — menus, pointer and keyboard workflows, dialogs,
persistence, themes. Keep deterministic logic in pytest; spend this skill on the
human-visible surface.

## Launch isolated

Labelme resolves its config (`~/.labelmerc`), caches, and window state through
`HOME`, so one environment variable isolates a run from the tester's real profile.
From the repository root, in a shell that stays alive for the whole session:

```bash
RUN_DIR=$(mktemp -d)
cp -R examples/primitives "$RUN_DIR/inputs"
mkdir "$RUN_DIR/outputs" "$RUN_DIR/evidence"
HOME="$RUN_DIR" uv run --no-sync labelme "$RUN_DIR/inputs" \
  --output "$RUN_DIR/outputs" 2>"$RUN_DIR/stderr.log"
```

Variants:

- Raw image, no annotations: copy only the `.jpg` into `inputs`.
- Image sequence: copy from `examples/video_annotation/data_annotated`.
- Corrupt annotation: overwrite an `inputs/*.json` with `{ not json`.
- Theme: append `--config "color_theme: dark"` (or `light`).
- First-launch empty state: omit the path argument.

Keep `RUN_DIR` until the report is delivered; `outputs/`, `stderr.log`, and
`evidence/` are the durable record of the run.

## Exercise the app

For each check: state the expected outcome first, act as a user would (pointer or
keyboard, never programmatic widget calls), then verify both the visible result and
the durable one — the saved JSON in `outputs/`, or the state after a clean restart.
Screenshot each checkpoint into `evidence/` with names like `02-undo-after-rect.png`.

Core flows, in priority order. A quick check covers the first three; a full sweep
covers all, plus unscripted exploration of whatever looked surprising along the way:

01. Launch on the annotated example: canvas shapes, label list, file list, and window
    title agree.
02. Draw a rectangle and a polygon, accept labels, undo: the shape disappears from the
    canvas and from the saved JSON.
03. Quit and relaunch on the same `RUN_DIR`: annotations persist, no unexpected save
    prompt, exit status is clean.
04. Edit: select, move, resize, delete a shape; undo restores the exact geometry.
05. Each remaining shape type (circle, point, line, line strip): correct `shape_type`
    and points in the saved JSON.
06. Navigate next and previous images; zoom, fit window, brightness/contrast apply and
    cancel.
07. Unsaved-changes dialog with auto-save disabled (`--no-auto-save`): Cancel keeps the
    session, Discard drops the edit, Save writes it.
08. Corrupt JSON and missing image: the error names the problem and the session stays
    usable.
09. Keyboard only: the primary annotate-save flow works by menus and shortcuts, focus
    stays visible.
10. Dark and light themes: text legible, icons update, disabled states distinguishable.
11. Accessibility: main controls expose meaningful names and roles.

AI Assist downloads models — exercise it only when the request explicitly authorizes
network use (the cache lands inside `RUN_DIR`, so it stays isolated).

## Report

Findings first, then coverage. Classify each finding: defect (broken function or
data), friction (works but surprising or costly), visual, accessibility, or
automation gap (the tooling failed, not the app). Reproduce a defect from a fresh
state before reporting it; a crash or data loss needs only one occurrence with full
evidence. Every finding carries the steps, expected versus actual, and evidence
paths. Close with what was covered and what was not — an unrun check is a gap, not
a pass.

If asked to file the findings, follow `docs/agents/issue-tracker.md` and stop for
human review before creating issues.
