from __future__ import annotations

from pathlib import Path

import pytest
from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from labelme.app import MainWindow

from ..conftest import close_or_pause
from .conftest import MainWinFactory
from .conftest import show_window_and_wait_for_imagedata


@pytest.mark.gui
def test_close_file(
    annotated_win: MainWindow,
    qtbot: QtBot,
    pause: bool,
) -> None:
    assert annotated_win._annotation is not None
    assert annotated_win._canvas_widgets.canvas.isEnabled()

    annotated_win.close_file()
    qtbot.wait(50)

    assert not annotated_win._canvas_widgets.canvas.isEnabled()
    assert annotated_win._annotation is None
    assert annotated_win.windowTitle() == "Labelme"

    close_or_pause(qtbot=qtbot, widget=annotated_win, pause=pause)


@pytest.mark.gui
def test_delete_label_file(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    pause: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win = main_win(
        file_or_dir=str(data_path / "annotated"),
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    label_file = data_path / "annotated/2011_000003.json"
    assert label_file.exists()

    item = win._docks.file_list.currentItem()
    assert item is not None
    assert item.checkState() == Qt.CheckState.Checked

    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "warning",
        lambda *args, **kwargs: QtWidgets.QMessageBox.StandardButton.Yes,
    )
    win.delete_file()
    qtbot.wait(50)

    assert not label_file.exists()

    item = win._docks.file_list.currentItem()
    assert item is not None
    assert item.checkState() == Qt.CheckState.Unchecked

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_delete_label_file_keeps_image(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    pause: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win = main_win(
        file_or_dir=str(data_path / "annotated"),
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    canvas = win._canvas_widgets.canvas
    assert not canvas.pixmap.isNull()
    assert canvas.shapes
    assert len(win._docks.label_list) > 0

    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "warning",
        lambda *args, **kwargs: QtWidgets.QMessageBox.Yes,
    )
    win.delete_file()
    qtbot.wait(50)

    # The annotations are cleared, but the image stays on the canvas.
    assert not canvas.pixmap.isNull()
    assert canvas.isEnabled()
    assert canvas.shapes == []
    assert len(win._docks.label_list) == 0
    assert win._image_path is not None
    assert win._annotation is not None

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)
