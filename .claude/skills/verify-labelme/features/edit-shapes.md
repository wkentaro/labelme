# Edit shapes

A user selects an existing shape, moves it, renames it, deletes it, and undoes a change. Each edit shows in the Shape List and the canvas, and with auto save on it reaches the annotation file.

## Sub-features

- `select` selects a shape from the Shape List or by clicking it on the canvas.
- `move` drags a selected shape to a new position.
- `relabel` changes a shape's label through the label dialog.
- `delete` removes the selected shapes.
- `undo` restores the state before the last edit.

## How to get to it (user POV)

- Click a row in the Shape List, or click inside a shape on the canvas in Edit Shapes mode.
- Drag a shape on the canvas.
- Double-click a Shape List row, choose Edit > Edit Label (`Ctrl+E`), press `Ctrl+E`, or right-click the shape and choose `Edit Label…`.
- Press `Delete`, choose Edit > Delete Shapes, click the `Delete` toolbar button, or right-click the shape and choose `Delete Shapes`.
- Press `Ctrl+Z`, choose Edit > Undo, or click the `Undo` toolbar button.

## Driving it with labelme_ctl

Preconditions:

- Launched with `--seed annotated -- '{data}/2011_000003.jpg'`, and `doctor` is healthy.
- The annotation file has `amber_kite` with first point (55, 65) and `blue_block`, a rectangle from (245, 45) to (355, 135).

Steps:

- **Select from the list.** Run `$CTL pick 'Shape List' blue_block`. The `blue_block` row is `selected` and the `Delete` toolbar button is enabled.
- **Delete.** Run `$CTL key Delete`. The Shape List drops `blue_block`. With auto save on, the status bar shows `Saved` and the file no longer has `blue_block`.
- **Undo.** Run `$CTL key Ctrl+Z`. `blue_block` returns to the Shape List and to the file.
- **Delete from the context menu.** Run `$CTL click-canvas 300 90 --button right`. `state.popup.items` lists `Delete Shapes`. Run `$CTL click 'Delete Shapes'`. The Shape List drops `blue_block`. Run `$CTL key Ctrl+Z` to bring it back.
- **Move.** Run `$CTL drag-canvas 300 90 320 110`. `blue_block` becomes `selected`, and after `$CTL wait --status Saved` its first point in the file is near (265, 65). `amber_kite` keeps its first point (55, 65).
- **Relabel by double-click.** Run `$CTL pick 'Shape List' amber_kite --double`. `state.dialog.title` is `Shape Label` and the `Label` field holds `amber_kite`. Run `$CTL key Ctrl+A`, `$CTL type kite`, and `$CTL key Return`. The Shape List shows `kite` and the file's first shape has `label` `kite` with unchanged points.
- **Relabel by shortcut.** Run `$CTL pick 'Shape List' kite` and `$CTL key Ctrl+E`. The `Shape Label` dialog opens on `kite`. Run `$CTL key Escape`. The label stays `kite`.
- **Proof.** Run `$CTL screenshot 01-edited.png --window main` and copy `2011_000003.json` to `evidence/`.

## Gotchas

- Undo clears the selection, so a second `Delete` right after `Ctrl+Z` does nothing. Pick the shape again first.
- A press on the canvas selects the shape under the point. Aim well inside the target and away from other shapes.
- Auto save writes the file in the background after each edit. The status bar shows `Saving…` at once and `Saved` when the latest edit is on disk, so run `$CTL wait --status Saved` before you read the file or copy it to `evidence/`.
