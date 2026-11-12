from __future__ import annotations

import json
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from .conftest import MainWinFactory
from .conftest import schedule_on_dialog
from .conftest import select_shape
from .conftest import show_window_and_wait_for_imagedata
from .conftest import submit_label_dialog


@pytest.mark.parametrize("auto_save", [False, True])
def test_accepting_another_shapes_label_preserves_it_in_the_saved_file(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    auto_save: bool,
) -> None:
    saved = data_path / "annotated/2011_000003.json"
    win = main_win(file_or_dir=saved, config_overrides={"auto_save": auto_save})
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    canvas = win._canvas_widgets.canvas
    dialog = win._label_dialog
    expected = json.loads(saved.read_text())["shapes"][1]

    select_shape(qtbot=qtbot, canvas=canvas, shape_index=0)
    submit_label_dialog(qtbot=qtbot, label_dialog=dialog, label="previous-label")
    win._actions.edit.trigger()
    assert canvas.shapes[0].label == "previous-label"

    select_shape(qtbot=qtbot, canvas=canvas, shape_index=1)
    accepted: list[bool] = []

    def accept_displayed_label() -> None:
        try:
            assert dialog.edit.text() == expected["label"]
            qtbot.keyClick(dialog.edit, Qt.Key.Key_Return)
            accepted.append(not dialog.isVisible())
        finally:
            if dialog.isVisible():
                dialog.reject()

    schedule_on_dialog(label_dialog=dialog, action=accept_displayed_label)
    win._actions.edit.trigger()
    if not auto_save:
        win._save_label_file(save_as=False)
    qtbot.waitUntil(lambda: not win._save_writer.is_busy)
    win.mark_clean()

    assert accepted == [True]
    assert json.loads(saved.read_text())["shapes"][1] == expected
    assert win._load_file(image_or_label_path=str(saved))
    assert canvas.shapes[1].label == expected["label"]
