from __future__ import annotations

import json
from pathlib import Path

from .conftest import MainWinFactory


def test_keep_prev_leaves_an_empty_annotation_file_empty(
    *, main_win: MainWinFactory, data_path: Path
) -> None:
    empty = data_path / "annotated" / "2011_000006.json"
    raw = json.loads(empty.read_text(encoding="utf-8"))
    raw["shapes"] = []
    empty.write_text(json.dumps(raw), encoding="utf-8")

    win = main_win(
        file_or_dir=data_path / "annotated/2011_000003.jpg",
        config_overrides={"keep_prev": True, "auto_save": False},
    )
    assert win._canvas_widgets.canvas.shapes

    assert win._load_file(
        image_or_label_path=str(data_path / "annotated/2011_000006.jpg")
    )

    shapes = list(win._canvas_widgets.canvas.shapes)
    is_changed = win._is_changed
    # A dirty window would block teardown on the Unsaved Changes dialog.
    win.mark_clean()

    assert shapes == []
    assert not is_changed


def test_keep_prev_carries_shapes_onto_an_image_without_a_file(
    *, main_win: MainWinFactory, data_path: Path
) -> None:
    win = main_win(
        file_or_dir=data_path / "annotated/2011_000003.jpg",
        config_overrides={"keep_prev": True, "auto_save": False},
    )
    carried = len(win._canvas_widgets.canvas.shapes)
    assert carried

    assert win._load_file(image_or_label_path=str(data_path / "raw/2011_000003.jpg"))

    assert len(win._canvas_widgets.canvas.shapes) == carried
    assert win._is_changed
    win.mark_clean()


def test_keep_prev_does_not_carry_shapes_onto_the_reloaded_image(
    *, main_win: MainWinFactory, data_path: Path, tmp_path: Path
) -> None:
    win = main_win(
        file_or_dir=data_path / "annotated",
        config_overrides={"keep_prev": True, "auto_save": False},
    )
    assert win._canvas_widgets.canvas.shapes
    empty_folder = tmp_path / "empty"
    empty_folder.mkdir()

    # Changing the Annotation Folder reloads the open Image against it.
    assert win._switch_output_dir(output_dir=empty_folder)

    shapes = list(win._canvas_widgets.canvas.shapes)
    is_changed = win._is_changed
    win.mark_clean()

    assert shapes == []
    assert not is_changed
