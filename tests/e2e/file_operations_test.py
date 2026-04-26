from __future__ import annotations

from pathlib import Path

import pytest
from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt
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
    assert annotated_win._image_data is not None
    assert annotated_win._canvas_widgets.canvas.isEnabled()

    annotated_win.close_file()
    qtbot.wait(50)

    assert not annotated_win._canvas_widgets.canvas.isEnabled()
    assert annotated_win._image_data is None
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
    assert item.checkState() == Qt.Checked

    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "warning",
        lambda *args, **kwargs: QtWidgets.QMessageBox.Yes,
    )
    win.delete_file()
    qtbot.wait(50)

    assert not label_file.exists()

    item = win._docks.file_list.currentItem()
    assert item is not None
    assert item.checkState() == Qt.Unchecked

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)
