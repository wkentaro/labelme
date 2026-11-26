# Open and navigate images

A user opens an image, an annotation file, or a folder, then moves between images. The title shows the open file and its position, such as `2011_000006.jpg [2/3]`, and the Image List marks annotated images with a check.

## Sub-features

- `open-cli` opens a folder, an image, or an annotation file passed on the command line.
- `open-file` opens one file through File > Open File.
- `navigate` moves to the next or previous image.
- `image-list` opens an image by clicking its row and shows a check for each annotated image.
- `file-search` filters the Image List by filename.

## How to get to it (user POV)

- Run `labelme <folder>`, `labelme <image>`, or `labelme <image>.json`.
- Choose File > Open File (`Ctrl+O`) or the `Open File` toolbar button.
- Press `D` or `A`, choose File > Next Image or File > Previous Image, or click the `Next` or `Previous` toolbar button.
- Click a row in the Image List dock.
- Click the `Search Filename` field above the Image List and type.

## Driving it with labelme_ctl

Preconditions:

- Launched with `--seed annotated -- '{data}'`, and `doctor` is healthy.

Steps:

- **Open a folder.** Launch as above. The title ends in `2011_000003.jpg [1/3]`. The Image List rows are `2011_000003.jpg`, `2011_000006.jpg`, and `2011_000025.jpg`, all `checked`, with the first `selected`. The Shape List has five rows starting with `amber_kite`.
- **Next by key.** Run `$CTL key D`. The title ends in `2011_000006.jpg [2/3]` and the Shape List shows `orange_pentagon`, `blue_trapezoid`, and `green_diamond`.
- **Previous by toolbar.** Run `$CTL click Previous`. The title ends in `[1/3]` again.
- **Next by menu.** Run `$CTL action 'File > Next Image'`. The title ends in `[2/3]`.
- **Pick from the list.** Run `$CTL pick 'Image List' 2011_000025.jpg`. The title ends in `2011_000025.jpg [3/3]` and the Shape List shows `amber_arch` and `blue_marker`.
- **Filter.** Run `$CTL click 'Search Filename'` and `$CTL type 0006`. The Image List shows only `2011_000006.jpg`, and the `Search Filename` field holds `0006`.
- **Open one file.** In a fresh launch with `--seed annotated` and no path, run `$CTL action 'File > Open File'`. `state.modal.title` is `Open File`. Run `$CTL type "$LABELME_VERIFY_RUN/data/2011_000006.json"` and `$CTL key Return`. The dialog closes, the title ends in `2011_000006.jpg`, and the status bar reads `Loaded 2011_000006.json`.
- **Proof.** After each move you report, run `$CTL screenshot <NN>-<move>.png --window main` with a new number, such as `01-next-key.png` and `02-previous-toolbar.png`.

## Gotchas

- Launching with an image path lists every image in its folder, so the title shows a position such as `[1/3]`. Launching with an annotation file, or opening one through File > Open File in a fresh launch, leaves the Image List empty and Next Image and Previous Image disabled, so `action` refuses them.
- With a filter, the title's `[n/m]` counts only the listed images, and it drops out when the filter hides the open image.
- `D` and `A` type into the `Search Filename` field while it has focus, and `Escape` does not move focus out. Run `$CTL click-canvas 5 5` first, in Edit Shapes mode so the click draws nothing.
- `--seed raw` images have no annotation files, so no Image List row is checked until a save.
