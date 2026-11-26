---
name: verify-labelme
description: Launch the labelme desktop app from a checkout, drive it headlessly with real Qt mouse and keyboard input, and capture screenshots and saved annotation files as proof. Use to verify a labelme change or PR in the real app, or to compare one journey on a base tree and a head tree.
---

# Verify labelme

labelme is a PySide6 desktop app. This skill runs the real `labelme` entry point offscreen in its own process, with a scratch `HOME`, and drives it through a control port that sends the same Qt input events a user's mouse and keyboard produce. Every command prints JSON. A failed command prints `{"ok": false, "error": ...}` and exits 1.

The helper is `.claude/skills/verify-labelme/scripts/labelme_ctl.py`. Run it from any directory with the system `python3`, and run `labelme_ctl.py <command> --help` for flags. The examples below use `CTL=.claude/skills/verify-labelme/scripts/labelme_ctl.py` from the repo root.

It runs on macOS only, because it uses `sandbox-exec` to keep labelme's writes inside the run dir.

## Launch

```sh
$CTL launch --checkout . --seed annotated -- '{data}'
export LABELME_VERIFY_RUN=<run_dir from the output>
```

- The output's `export` line quotes the path, so `eval` it when the path has spaces.
- `--checkout` is the tree to run. Launch starts that tree's `.venv/bin/python` without your shell's `PYTHON*` variables, so labelme imports only from that tree. Run `uv sync --frozen` in the tree first. That sync builds the tree outside the sandbox, so run it only on a tree you trust. To compare base and head, make a worktree for each, sync each, and launch one instance per tree.
- `--seed` copies sample data into `<run_dir>/data`: `raw` (three images, no annotations, the default), `annotated` (the same images with five, three, and two shapes), `tutorial` (`examples/tutorial`), or `none`.
- The scratch `.labelmerc` sets the UI language to `en_US`, and the window is 1280x800.
- Everything after `--` is passed to `labelme`. `{data}` expands to the seeded folder. Pass a folder, an image, or a `.json` file, plus any labelme flag such as `--no-auto-save` or `--output '{data}/ann'`. labelme can read any path but write only inside the run dir.
- Launch returns once the window is visible, and, when the last argument is an existing path, once an image is on the canvas or the folder's Image List is known to be empty. It also returns when a dialog opens first, such as the error for an image that cannot be read. Its output carries `image_loaded` and `dialog`, so check both first. If labelme exits before then, such as on a bad flag, launch exits 1 with `exited: true` and its `exit_code`. The default timeout is 120 s.

Each launch gets a fresh run dir from `mktemp`, so instances never share state, and two or more can run side by side. A `LABELME_VERIFY_RUN` already set does not change that. `--run-dir` picks the directory instead. It must be new, empty, or made by an earlier launch and cleaned up since. Launch refuses one that still holds `home`, `data`, or `tmp`, or whose `evidence` is a symlink. It makes those three fresh, and it replaces each file it writes in the run dir and `evidence/` instead of writing through a link left at that name. Inside the run dir:

- `home/` is the process's `HOME`. It holds `.labelmerc`, the log under `.cache/labelme/`, and the window state in `qtsettings/labelme-labelme.ini`. The helper redirects Qt's window state there, because Qt's native store on macOS ignores `HOME`.
- `data/` holds the seeded images and annotation files.
- `evidence/` holds `labelme.log` (the process's stdout and stderr) and every screenshot.
- `run.json` marks the directory as made by `launch` and holds the token every request sends. The control port rejects a request without it, so keep the run dir private.
- `sandbox.sb` is the macOS sandbox profile labelme runs under, and `tmp/` is its `TMPDIR`.

The sandbox denies every file write outside the run dir and every write to the user's preferences, so labelme cannot change the user's files or `~/Library/Preferences`. A denied write fails with `Operation not permitted`, and labelme shows its own error. The sandbox blocks writes only. labelme can still read any file and reach the network, so it keeps a trusted tree from damaging files, not a hostile tree from leaking them.

## Doctor

```sh
$CTL doctor
```

Run it right after launch and whenever a reply looks wrong. It exits 0 and prints `"healthy": true` only when the PID is the one this run started, the control port answers from that PID, `labelme` imports from the checkout, `HOME` and the window state sit in the run's `home/`, the platform is `offscreen`, a write outside the run dir fails, and no uncaught exception has reached labelme's crash handler. An error dialog the app shows on purpose, such as a file that cannot be opened, does not make it unhealthy. `checkout_head` and `checkout_dirty` record which tree you are running. `checkout_dirty` is true when the tree has uncommitted changes or untracked files. Any other result exits 1 with `"ok": false`, `"healthy": false`, an `error`, and the report fields it gathered. When labelme answered, `problems` lists each failed check. Use only an instance whose doctor is healthy.

## Observe

| Command | What it reads |
| --- | --- |
| `state` | The window title, the top `dialog` (title, `modal`, labels, buttons), `focus`, `status_bar`, `toolbar` buttons with checked and enabled state, and `docks` with their list rows (`text`, `checked`, `selected`). |
| `wait --no-dialog` | Polls `state` until every condition holds: `--status`, `--no-dialog`, `--file <path>`, where a relative path starts from the current directory. It fails within its timeout, 10 s by default, even when labelme stops answering. |
| `screenshot 01-name.png` | Saves the top dialog, or the main window with `--window main`, to `evidence/`. The name is relative to `evidence/`, and a file already at that name is replaced. |

If labelme dies without exiting, such as on a Qt abort, the next command exits 1 with `labelme crashed without exiting`, and the cause is in `evidence/labelme.log`.

## Drive

Read the screen with `state`, act, then read the reply. Every action replies about 300 ms after the input with `{"did": ..., "state": ...}`, so a dialog the action opened is already in `state.dialog`.

| Command | What the user does |
| --- | --- |
| `menu` | Opens every menu and reads each item's path, enabled state, checked state, and shortcut. |
| `action 'Edit > Polygon'` | Chooses a menu bar item. It refuses a disabled item, and any item while a dialog or popup is open, as the menu bar would. |
| `key Ctrl+S` | Presses one key stroke on the open popup menu or the focused widget. Use Qt names: `Return`, `Escape`, `Delete`, `Ctrl+Z`, `D`. It refuses a multi-stroke sequence such as `'Ctrl+K, Ctrl+R'` and a name Qt does not know, so send each stroke with its own `key`. `Ctrl` is Command on macOS, matching the app's shortcuts. |
| `type 'cat'` | Types ASCII text into the focused widget. A newline presses `Return`, and the text after it goes to whatever has focus once the app has handled that `Return`, so `type $'box\nD'` names a new shape `box` and then moves to the next image. Other control characters such as tab are refused, so send them with `key`. |
| `click 'Save'` | Clicks a button or a text field in the top dialog, or in the main window when no dialog is open. It matches visible text, tooltip, accessible name, or placeholder, such as `'Next'`, `'OK'`, `'Discard'`, or `'Search Filename'`. With a context menu open, it clicks the item with that text, such as `'Delete Shapes'`. |
| `pick 'Shape List' blue_block` | Clicks a row in a dock list (`Shape List`, `Label List`, `Image List`) or a dialog list, such as `Files` in the Open File dialog. Add `--double` to double-click. It refuses a row the user cannot select, such as the `Found in files` header in the Label List. |
| `click-canvas 120 80` | Clicks the canvas at image pixel (120, 80), whatever the zoom. It refuses a point outside the visible part of the canvas, so scroll or zoom first. A point on the image's far edge lands on the last widget pixel, up to one widget pixel inside the edge. Add `--modifier shift` to hold Shift. `--button right` opens the context menu of the shape under the point, or the canvas menu on empty space. |
| `drag-canvas 300 90 320 110` | Presses the left button at one image pixel, moves, and releases at another. |

Input goes to the open popup menu, else the top dialog, modal or not, such as Settings, else the main window. Close a dialog to reach the window behind it.

Before each input the helper does what the OS would. It releases a mouse button that a modal dialog swallowed the release of, and it reactivates the top window, because the offscreen platform has no window manager to do it. Without that, a double-click that opens a dialog leaves Left held, and the next canvas move drags whatever shape is selected.

A command fails with `{"ok": false, "error": ...}` and exit code 1 when its target is missing, ambiguous, disabled, or behind an open dialog or popup, as the real input would be. Read the error, check `state`, and choose another entry point. An action that closes the app replies `{"exited": true, "exit_code": 0}`.

## Evidence

A proof is the command, its reply, and a screenshot of what it shows. Number screenshots in journey order (`01-launch.png`, `02-error-dialog.png`). For a second view, launch again on the first run's `data/` and confirm the same state returns.

Leave the app's Python objects alone. Offscreen rendering uses the Fusion style, so screenshots prove behavior and layout but not the native macOS or Windows look. For native-look screenshots, follow `docs/agents/gui-driving.md`.

## Cleanup

```sh
$CTL cleanup
```

It refuses a directory without `run.json`. It kills only the PID this run started, after checking that its command line names this run dir. Then it deletes `home/`, `data/`, `tmp/`, `sandbox.sb`, `instance.json`, and `exit_code`, and keeps `evidence/`. Report the evidence path, `<run_dir>/evidence`, with the verdict. Run cleanup after every run, failed runs included. If `doctor` reports a PID that is not ours, leave that process alone.

## Gotchas

- zsh passes `"300 100"` as one argument. Write coordinates as separate words.
- Canvas coordinates are image pixels. Read a shape's points from its annotation file, or from the image size in the file, to aim a click.
- Auto save is on by default, so each change writes `<image>.json` next to the image. Pass `--no-auto-save` to test explicit saves and the unsaved-changes dialog.
- File > Open File and Open Folder show Qt's own file dialog offscreen. It lists the folder after a moment, so poll `state` until the row shows in the `Files` list of `state.dialog`, then `pick Files <name> --double`. Or `type` the absolute path into its focused field and press `Return`. On macOS, type the path `realpath` prints: a `/var/folders/...` path, which goes through a symlink, left the dialog open and empty in testing.
- AI-Segment and AI-Find All download models into the scratch `HOME` on first use, which takes minutes and needs network access.
