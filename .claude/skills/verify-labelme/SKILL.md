---
name: verify-labelme
description: Launch the labelme desktop app from a checkout offscreen in a sandboxed scratch run, read its state, and capture screenshots and saved annotation files as proof. Use to verify a labelme change or PR in the real app, or to compare one journey on a base tree and a head tree.
---

# Verify labelme

labelme is a PySide6 desktop app. This skill runs the real `labelme` entry point offscreen in its own process, with a scratch `HOME`, and reads it through a control port. Every command prints JSON. A failed command prints `{"ok": false, "error": ...}` and exits 1.

The helper is `.claude/skills/verify-labelme/scripts/labelme_ctl.py`. Run it from any directory with the system `python3`, and run `labelme_ctl.py <command> --help` for flags. The examples below use `CTL=.claude/skills/verify-labelme/scripts/labelme_ctl.py` from the repo root.

It runs on macOS only, because it uses `sandbox-exec` to keep labelme's writes inside the run dir.

## Launch

```sh
$CTL launch --checkout . --seed annotated -- '{data}'
export LABELME_VERIFY_RUN=<run_dir from the output>
```

- The output's `export` line quotes the path, so `eval` it when the path has spaces.
- `--checkout` is the tree to run. Launch starts that tree's `.venv/bin/python`, so run `uv sync --frozen` in the tree first. That sync builds the tree outside the sandbox, so run it only on a tree you trust. To compare base and head, make a worktree for each, sync each, and launch one instance per tree.
- `--seed` copies sample data into `<run_dir>/data`: `raw` (three images, no annotations, the default), `annotated` (the same images with five, three, and two shapes), `tutorial` (`examples/tutorial`), or `none`.
- The scratch `.labelmerc` sets the UI language to `en_US`, and the window is 1280x800.
- Everything after `--` is passed to `labelme`. `{data}` expands to the seeded folder. Pass a folder, an image, or a `.json` file, plus any labelme flag such as `--no-auto-save` or `--output '{data}/ann'`. labelme can read any path but write only inside the run dir, so copy a file you want to edit into `<run_dir>/data` first. A save outside shows `Save failed` in the status bar.
- Launch returns once the window is visible, and, when the last argument is an existing path, once an image is on the canvas or the folder's Image List is known to be empty. It also returns when a dialog opens first, such as the error for an image that cannot be read. Its output carries `image_loaded` and `dialog`, so check both before driving. The default timeout is 120 s.

Each launch gets a fresh run dir from `mktemp`, so instances never share state, and two or more can run side by side. A `LABELME_VERIFY_RUN` already set does not change that. `--run-dir` picks the directory instead. It must be new, empty, or made by an earlier launch and cleaned up since. Launch refuses one that still holds `home`, `data`, or `tmp`, or whose `evidence` is a symlink. It makes those three fresh, and it replaces each file it writes in the run dir and `evidence/` instead of writing through a link left at that name. Inside the run dir:

- `home/` is the process's `HOME`. It holds `.labelmerc`, the log under `.cache/labelme/`, and the window state in `qtsettings/labelme-labelme.ini`. The helper redirects Qt's window state there, because Qt's native store on macOS ignores `HOME`.
- `data/` holds the seeded images and the annotation files the app writes.
- `evidence/` holds `labelme.log` (the process's stdout and stderr) and every screenshot.
- `run.json` marks the directory as made by `launch` and holds the token every request sends. The control port rejects a request without it, so keep the run dir private.
- `sandbox.sb` is the macOS sandbox profile labelme runs under, and `tmp/` is its `TMPDIR`.

The sandbox denies every file write outside the run dir and every write to the user's preferences, so no file dialog, Save As, or link inside `data/` can change the user's files or `~/Library/Preferences`. A denied write fails with `Operation not permitted`, and labelme shows its own error. Help > Tutorial's browser and Settings' `Open config file as text` editor open nothing, and each appends a line to `state.blocked`, so a journey that needs one of them reports why it stopped. The sandbox blocks writes only. labelme can still read any file and reach the network, so it keeps a trusted tree from damaging files, not a hostile tree from leaking them.

## Doctor

```sh
$CTL doctor
```

Run it right after launch and whenever a reply looks wrong. It exits 0 and prints `"healthy": true` only when the PID is the one this run started, the control port answers from that PID, `labelme` imports from the checkout, `HOME` and the window state sit in the run's `home/`, the platform is `offscreen`, a write outside the run dir fails, and no uncaught exception has reached labelme's crash handler. An error dialog the app shows on purpose, such as a file that cannot be opened, does not make it unhealthy. `checkout_head` and `checkout_dirty` record which tree you are driving. Any other result exits 1 with `"ok": false`, `"healthy": false`, an `error`, and the report fields it gathered. When labelme answered, `problems` lists each failed check. When labelme exited, `exit_code` holds its code. Drive only an instance whose doctor is healthy.

## Observe

| Command | What it reads |
| --- | --- |
| `state` | The window title, the top `dialog` (title, `modal`, labels, fields, buttons, lists), `popup` menu with its `items`, `focus`, `status_bar`, `toolbar` buttons with checked and enabled state, `docks` with their list rows (`text`, `checked`, `selected`), `mouse_buttons_held`, and `blocked`, the launches the helper stopped. |
| `wait --status Saved --no-dialog` | Polls `state` until every condition holds: `--status`, `--no-dialog`, `--file <path>`. It fails within its timeout, 10 s by default, even when labelme stops answering, and fails with `exit_code` when labelme exits first. |
| `screenshot 01-name.png` | Saves the top dialog, or the main window with `--window main`, to `evidence/`. The name is relative to `evidence/`, and a file already at that name is replaced. |

If labelme exits cleanly, the next `state` or `screenshot` replies `{"exited": true, "exit_code": 0}`, and `wait` and `doctor` fail with that `exit_code`. If labelme dies without exiting, such as on a Qt abort, the command exits 1 with `labelme crashed without exiting`, and the cause is in `evidence/labelme.log`.

## Evidence

A proof has three parts.

- The action and its result: the command, its reply, and a screenshot taken after the change is visible. Number screenshots in journey order (`01-drawing.png`, `02-label-dialog.png`).
- The side effect on disk: read the annotation file the app wrote under `data/`, and copy it into `evidence/` before cleanup. A `Saved` status alone does not prove the file holds the right shapes.
- A second view of the state: reopen the file, move to the next image and back, or relaunch on the same data, and confirm the shapes return.

Drive the path a user takes: menus, shortcuts, toolbar buttons, list rows, and canvas clicks. Leave the app's Python objects alone. Offscreen rendering uses the Fusion style, so screenshots prove behavior and layout but not the native macOS or Windows look. For native-look screenshots, follow `docs/agents/gui-driving.md`.

## Cleanup

```sh
$CTL cleanup
```

It refuses a directory without `run.json`. It kills only the PID this run started, after checking that its command line names this run dir. Then it deletes `home/`, `data/`, `tmp/`, `sandbox.sb`, `instance.json`, and `exit_code`, and keeps `evidence/`. Report the evidence path, `<run_dir>/evidence`, with the verdict. Run cleanup after every run, failed runs included. If `doctor` reports a PID that is not ours, leave that process alone.
