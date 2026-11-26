# Draw shapes

A user picks a shape tool, clicks points on the image, and names the shape in the label dialog. The shape appears in the Shape List and, with auto save on, in the image's annotation file.

## Sub-features

- `draw-polygon` creates a polygon from clicked points, closed by clicking the first point.
- `draw-rectangle` creates a rectangle from two clicked corners.
- `label-dialog` names the new shape, with `OK` disabled until the label has text.
- `draw-cancel` discards a shape in progress with `Escape`.

## How to get to it (user POV)

- Choose a tool from the Edit menu (`Edit > Polygon`, `Edit > Rectangle`, and the other shape types), press `Ctrl+N` for Polygon or `Ctrl+R` for Rectangle, or click the tool in the left toolbar.
- Click on the image to place points.
- Type the label in the `Shape Label` dialog and press `Return` or click `OK`.

## Driving it with labelme_ctl

Preconditions:

- Launched with `--seed raw -- '{data}/2011_000003.jpg'`, and `doctor` is healthy.
- `$LABELME_VERIFY_RUN/data/2011_000003.json` does not exist.

Steps:

- **Pick Polygon.** Run `$CTL action 'Edit > Polygon'`. The `Polygon` toolbar button is `checked` and the status bar reads `Polygon • Click to add point`.
- **Place points.** Run `$CTL click-canvas 100 100`, `$CTL click-canvas 300 100`, and `$CTL click-canvas 300 250`. After the third click the status bar adds `Enter or Space to finalize`. Run `$CTL screenshot 01-drawing.png --window main`.
- **Close the polygon.** Run `$CTL click-canvas 100 100`. `state.modal.title` is `Shape Label`, the `Label` field is focused and empty, and the `OK` button has `"enabled": false`. Run `$CTL screenshot 02-label-dialog.png`.
- **Name it.** Run `$CTL type cat`, then `$CTL key Return`. The dialog closes, the Shape List has a row `cat`, the status bar shows `Saved`, and the `2011_000003.jpg` row in the Image List is `checked`.
- **Check the file.** Run `$CTL wait --file "$LABELME_VERIFY_RUN/data/2011_000003.json" --no-dialog`. The file has one shape with `label` `cat`, `shape_type` `polygon`, and three points within a pixel of (100, 100), (300, 100), and (300, 250). Copy it to `evidence/`.
- **Rectangle by shortcut.** Run `$CTL key Ctrl+R`, `$CTL click-canvas 20 200`, and `$CTL click-canvas 60 320`. The label dialog opens. Run `$CTL type box` and `$CTL key Return`. The file gains a `rectangle` shape `box` with points (20, 200) and (60, 320).
- **Cancel.** Run `$CTL key Ctrl+N`, `$CTL click-canvas 200 20`, `$CTL click-canvas 240 20`, and `$CTL key Escape`. The status bar returns to `Polygon • Click to add point`, and the file gains no shape.
- **Proof.** Run `$CTL screenshot 03-saved.png --window main`. The canvas shows the outlined shapes and the Shape List lists them.

## Gotchas

- Clicks land on the nearest screen pixel, so saved points can differ from the requested image pixel by a fraction of a pixel at zoom levels other than 100%.
- Closing a polygon needs a click near the first point. A click elsewhere adds another point.
- A tool stays active after a shape is created. Choose `Edit > Edit Shapes` (`Ctrl+J`) before clicking shapes to select them.
- After the first shape, the label dialog prefills the last label with its text selected, so `type` replaces it.
