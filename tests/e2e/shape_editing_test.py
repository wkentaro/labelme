from __future__ import annotations

from pathlib import Path

import pytest
from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt
from pytestqt.qtbot import QtBot

import labelme.app
from labelme.widgets.canvas import Canvas

from ..conftest import assert_labelfile_sanity
from ..conftest import close_or_pause
from .conftest import image_to_widget_pos
from .conftest import show_window_and_wait_for_imagedata


def _open_and_select_shape(
    qtbot: QtBot,
    data_path: Path,
    shape_index: int = 0,
    config_overrides: dict[str, bool] | None = None,
    output_dir: str | None = None,
) -> tuple[labelme.app.MainWindow, Canvas]:
    win = labelme.app.MainWindow(
        file_or_dir=str(data_path / "annotated/2011_000003.json"),
        config_overrides=config_overrides,
        output_dir=output_dir,
    )
    qtbot.addWidget(win)
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    canvas = win._canvas_widgets.canvas
    assert len(canvas.shapes) == 5

    shape_center = canvas.shapes[shape_index].boundingRect().center()
    pos = image_to_widget_pos(canvas=canvas, image_pos=shape_center)
    qtbot.mouseMove(canvas, pos=pos)
    qtbot.wait(50)
    qtbot.mouseClick(canvas, Qt.LeftButton, pos=pos)
    qtbot.wait(50)

    assert len(canvas.selectedShapes) == 1
    return win, canvas


def _delete_selected_shape(
    win: labelme.app.MainWindow,
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
) -> None:
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "warning",
        lambda *args, **kwargs: QtWidgets.QMessageBox.Yes,
    )
    win.deleteSelectedShape()
    qtbot.wait(50)


@pytest.mark.gui
def test_select_shape(
    qtbot: QtBot,
    data_path: Path,
    pause: bool,
) -> None:
    win, canvas = _open_and_select_shape(qtbot=qtbot, data_path=data_path)

    assert canvas.selectedShapes[0].label == "person"

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_delete_shape(
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    pause: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win, canvas = _open_and_select_shape(
        qtbot=qtbot,
        data_path=data_path,
        config_overrides=dict(auto_save=True),
        output_dir=str(tmp_path),
    )

    _delete_selected_shape(win=win, monkeypatch=monkeypatch, qtbot=qtbot)

    assert len(canvas.shapes) == 4

    win._save_label_file()
    assert_labelfile_sanity(str(tmp_path / "2011_000003.json"))

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_delete_undo_shape(
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pause: bool,
) -> None:
    win, canvas = _open_and_select_shape(
        qtbot=qtbot,
        data_path=data_path,
        config_overrides=dict(auto_save=True),
        output_dir=str(tmp_path),
    )

    _delete_selected_shape(win=win, monkeypatch=monkeypatch, qtbot=qtbot)
    assert len(canvas.shapes) == 4

    win.undoShapeEdit()
    qtbot.wait(50)
    assert len(canvas.shapes) == 5
    assert canvas.shapes[0].label == "person"

    win._save_label_file()
    assert_labelfile_sanity(str(tmp_path / "2011_000003.json"))

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)
