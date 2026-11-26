# labelme verification map

This directory is the maintained source for verifying labelme's user-facing behavior. Read this index, then the feature file that matches the journey, and drive it with `labelme_ctl.py` as `../SKILL.md` describes.

## Baseline preconditions

- Launch with `$CTL launch --checkout <tree> --seed <seed> -- <labelme args>`, export `LABELME_VERIFY_RUN`, and require `$CTL doctor` to report `"healthy": true`.
- Each feature names its seed and labelme arguments. Start every recipe from a fresh launch unless the recipe continues one.
- Never drive a labelme window that this run did not launch, including the user's own app.

## Driving conventions

- Reach features the way a user does: `action` for menu items, `key` for shortcuts, `click` for toolbar and dialog buttons, `pick` for list rows, `click-canvas` and `drag-canvas` for the canvas.
- Treat names in commands as literal. They match the English UI, which `launch` selects by default with `--language en_US`.
- Read each action's reply before the next action. When a reply shows an unexpected `dialog`, handle or report the dialog before going on.
- Canvas coordinates are image pixels.

## Proof and skip reporting

- Capture the action and the resulting state: the reply's `state`, plus a screenshot under `evidence/`.
- For anything that saves, read the annotation file under `$LABELME_VERIFY_RUN/data` and copy it into `evidence/`.
- Confirm a saved change from a second view: switch images and come back, or reopen the file.
- Name the entry point used with each artifact, such as `key Ctrl+S` or `action 'File > Save'`.
- Report an entry point you could not reach with the command you ran and its error. Do not count it as verified through another entry point.

## Feature entry contract

Each feature file starts with an H1 title and one paragraph on the user-visible behavior, then four H2 sections in this order:

1. `Sub-features` lists short IDs, one line each.
2. `How to get to it (user POV)` lists every user entry point.
3. `Driving it with labelme_ctl` lists `Preconditions:`, then `Steps:` that pair each user action with an exact command and its observable result.
4. `Gotchas` lists traps that waste or invalidate a run.

Keep implementation details out of the map. Name user paths, stable handles, required state, commands, and observable proof.

## Features

- [Open and navigate images](./open-and-navigate.md) covers opening from the command line and File menu, moving between images, picking from the Image List, and filtering by filename.
- [Draw shapes](./draw-shapes.md) covers polygon and rectangle creation, the label dialog, and cancelling a shape in progress.
- [Edit shapes](./edit-shapes.md) covers selecting, moving, relabeling, deleting, and undoing.
- [Save annotations](./save-annotations.md) covers auto save, explicit save, and the unsaved-changes dialog.

Not mapped yet: AI-Segment, AI-Find All, AI text-to-annotation, Settings, Brightness/Contrast, flags, shape conversion, copy and paste, and the Annotation Folder.
