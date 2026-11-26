---
name: verify-labelme
description: Launch the labelme desktop app from a checkout, drive it headlessly with real Qt mouse and keyboard input, and capture screenshots and saved annotation files as proof. Use to verify a labelme change or PR in the real app, or to compare one journey on a base tree and a head tree.
---

# Verify labelme

labelme is a PySide6 desktop app. This skill runs the real `labelme` entry point offscreen in its own process, with a scratch `HOME`, and drives it through a control port that sends the same Qt input events a user's mouse and keyboard produce. Every command prints JSON.

The helper is `.claude/skills/verify-labelme/scripts/labelme_ctl.py`. Run it from any directory with the system `python3`, and run `labelme_ctl.py <command> --help` for flags. The examples below use `CTL=.claude/skills/verify-labelme/scripts/labelme_ctl.py` from the repo root.

It runs on macOS only, because it uses `sandbox-exec` to keep labelme's writes inside the run dir.

## Launch

```sh
$CTL launch --checkout . --seed annotated -- '{data}'
export LABELME_VERIFY_RUN=<run_dir from the output>
```

- `--checkout` is the tree to run. Launch starts that tree's `.venv/bin/python`, so run `uv sync --frozen` in the tree first. That sync builds the tree outside the sandbox, so run it only on a tree you trust. To compare base and head, make a worktree for each, sync each, and launch one instance per tree.
- `--seed` copies sample data into `<run_dir>/data`: `raw` (three images, no annotations, the default), `annotated` (the same images with five, three, and two shapes), `tutorial` (`examples/tutorial`), or `none`.
- `--language` writes the UI language to the scratch `.labelmerc`. It defaults to `en_US`, which the feature map's names assume. Pass `ja_JP` or another code to check a translation.
- Everything after `--` is passed to `labelme`. `{data}` expands to the seeded folder. Pass a folder, an image, or a `.json` file, plus any labelme flag such as `--no-auto-save` or `--output '{data}/ann'`. labelme can read any path but write only inside the run dir, so copy a file you want to edit into `<run_dir>/data` first. A save outside shows `Save failed` in the status bar.
- Launch returns once the window is visible, and, when the last argument is an existing path, once an image is on the canvas or the folder's Image List is known to be empty. It also returns when a dialog opens first, such as the error for an image that cannot be read. Its output carries `image_loaded` and `dialog`, so check both before driving. The default timeout is 120 s.

Each launch gets a fresh run dir from `mktemp`, so instances never share state, and two or more can run side by side. `--run-dir` picks the directory instead, and it must be new, empty, or made by an earlier launch. Inside the run dir:

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

Run it right after launch and whenever a reply looks wrong. It exits 0 and prints `"healthy": true` only when the PID is the one this run started, the control port answers from that PID, `labelme` imports from the checkout, `HOME` and the window state sit in the run's `home/`, the platform is `offscreen`, a write outside the run dir fails, and no uncaught exception has reached labelme's crash handler. An error dialog the app shows on purpose, such as a file that cannot be opened, does not make it unhealthy. `checkout_head` and `checkout_dirty` record which tree you are driving. Drive only an instance whose doctor is healthy.

## Drive

Read the screen with `state`, act, then read the reply. Every action replies about 300 ms after the input with `{"did": ..., "state": ...}`, so a dialog the action opened is already in `state.dialog`.

| Command | What the user does |
| --- | --- |
| `state` | Looks at the screen: window title, the top `dialog` (title, `modal`, labels, fields, buttons, lists), `popup` menu with its `items`, `focus`, `status_bar`, `toolbar` buttons with checked and enabled state, `docks` with their list rows (`text`, `checked`, `selected`), `mouse_buttons_held`, and `blocked`, the launches and file choices the helper stopped. |
| `menu` | Opens every menu and reads each item's path, enabled state, checked state, and shortcut. |
| `action 'Edit > Polygon'` | Chooses a menu bar item. It refuses a disabled item, and any item while a dialog or popup is open, as the menu bar would. |
| `key Ctrl+S` | Presses a key sequence on the open popup menu or the focused widget. Use Qt names: `Return`, `Escape`, `Delete`, `Ctrl+Z`, `D`. `Ctrl` is Command on macOS, matching the app's shortcuts. |
| `type 'cat'` | Types text into the focused widget, non-ASCII text such as `猫` included. |
| `click 'Save'` | Clicks a button or a text field in the top dialog, or in the main window when no dialog is open. It matches visible text, tooltip, accessible name, or placeholder, such as `'Next'`, `'OK'`, `'Discard'`, or `'Search Filename'`. With a context menu open, it clicks the item with that text, such as `'Delete Shapes'`. |
| `pick 'Shape List' blue_block` | Clicks a row in a dock list (`Shape List`, `Label List`, `Image List`) or a dialog list. Add `--double` to double-click, or `--modifier ctrl` to add to the selection. |
| `click-canvas 120 80` | Clicks the canvas at image pixel (120, 80), whatever the zoom. Add `--double` or `--modifier shift`. `--button right` opens the context menu of the shape under the point, or the canvas menu on empty space. |
| `drag-canvas 300 90 320 110` | Presses at one image pixel, moves, and releases at another. |
| `wait --status Saved --no-dialog` | Polls `state` until every condition holds: `--title`, `--status`, `--dialog <title>`, `--no-dialog`, `--file <path>`, `--image-loaded`. The default timeout is 10 s. |
| `screenshot 01-name.png` | Saves the top dialog, or the main window with `--window main`, to `evidence/`. The name is relative to `evidence/`. |

Input goes to the open popup menu, else the top dialog, modal or not, such as Settings, else the main window. Close a dialog to reach the window behind it.

Before each input the helper does what the OS would. It releases a mouse button that a modal dialog swallowed the release of, and it reactivates the top window, because the offscreen platform has no window manager to do it. Without that, a double-click that opens a dialog leaves Left held, and the next canvas move drags whatever shape is selected.

A command fails with `{"ok": false, "error": ...}` and exit code 1 when its target is missing, ambiguous, disabled, or behind an open dialog or popup, as the real input would be. Read the error, check `state`, and choose another entry point. An action that closes the app replies `{"exited": true, "exit_code": 0}`. If labelme dies without exiting, such as on a Qt abort, the command exits 1 with `labelme crashed without exiting`, and the cause is in `evidence/labelme.log`.

The feature map in [`features/README.md`](features/README.md) has the recipe for each user-facing feature. Read the feature's file before you drive it.

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

## Gotchas

- zsh passes `"300 100"` as one argument. Write coordinates as separate words.
- Canvas coordinates are image pixels. Read a shape's points from its annotation file, or from the image size in the file, to aim a click.
- Auto save is on by default, so each change writes `<image>.json` next to the image. Pass `--no-auto-save` to test explicit saves and the unsaved-changes dialog.
- File > Open File and Open Folder show Qt's own file dialog offscreen. `type` the absolute path into its focused field and press `Return`. On macOS, type the path `realpath` prints: a `/var/folders/...` path, which goes through a symlink, left the dialog open and empty in testing.
- AI-Segment and AI-Find All download models into the scratch `HOME` on first use, which takes minutes and needs network access. The feature map does not cover them yet.
