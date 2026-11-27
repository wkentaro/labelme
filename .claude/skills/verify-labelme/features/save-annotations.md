# Save annotations

labelme writes an image's shapes to `<image>.json` next to it. With auto save on, it writes after each change. With auto save off, the title gains `*`, the status bar shows `Unsaved changes`, and leaving the image or quitting asks whether to save.

## Sub-features

- `auto-save` writes the annotation file after each change when File > Save Automatically is checked.
- `save` writes the open image's annotation file on demand.
- `unsaved-prompt` asks `Save`, `Cancel`, or `Discard` before quitting with unsaved changes.

## How to get to it (user POV)

- Toggle File > Save Automatically, or launch with `--no-auto-save`.
- Press `Ctrl+S`, choose File > Save, or click the `Save` toolbar button.
- Quit with File > Quit (`Ctrl+Q`) while the title shows `*`.

## Driving it with labelme_ctl

Preconditions:

- Launched with `--seed annotated -- --no-auto-save '{data}'`, and `doctor` is healthy.

Steps:

- **Auto save is off.** Run `$CTL menu`. `File > Save Automatically` has `"checked": false`.
- **Make a change.** Run `$CTL pick 'Shape List' blue_block` and `$CTL key Delete`. The title ends in `*` and the status bar shows `Unsaved changes`. The file still has `blue_block`.
- **Save by shortcut.** Run `$CTL key Ctrl+S`. The `*` leaves the title, and the file no longer has `blue_block`.
- **Change again, then quit.** Run `$CTL pick 'Shape List' amber_kite`, `$CTL key Delete`, and `$CTL action 'File > Quit'`. `state.dialog.text` reads `Save annotation changes to "2011_000003.jpg"?` with buttons `Save`, `Cancel`, and `Discard`. With the prompt still open, the file on disk still has `amber_kite`. Run `$CTL screenshot 01-unsaved-dialog.png`.
- **Choose Save.** Run `$CTL click Save`. The reply includes `"exited": true` and `"exit_code": 0`. The file's shapes are `green_hexagon`, `red_triangle`, and `purple_diamond`, with neither `blue_block` nor `amber_kite`.
- **Proof.** Copy `2011_000003.json` to `evidence/`.
- **Reopen in a fresh launch.** Run `FIRST=$LABELME_VERIFY_RUN`, then launch again with `--seed none -- "$FIRST/data/2011_000003.json"` and export the new run dir. The Shape List rows are `green_hexagon`, `red_triangle`, and `purple_diamond`. Run `$CTL cleanup` for the new run, then `$CTL cleanup --run-dir "$FIRST"`.

## Gotchas

- Quitting closes the process, so take screenshots before the last click. Afterwards `doctor` and `wait` exit 1 with `"ok": false` and `"exit_code": 0`. Run `cleanup` anyway.
- `Cancel` keeps the app open with the change unsaved, and `Discard` quits without writing.
- With auto save on, the title can show `*` while a save is still writing. Read the title after `$CTL wait --status Saved` returns. It has no `*` then, and quitting asks nothing, so test the prompt only with `--no-auto-save`.
