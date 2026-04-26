from __future__ import annotations

from pathlib import Path

import pytest
from PyQt5.QtCore import QMimeData
from PyQt5.QtCore import QPoint
from PyQt5.QtCore import QPointF
from PyQt5.QtCore import Qt
from PyQt5.QtCore import QUrl
from PyQt5.QtGui import QDragEnterEvent
from PyQt5.QtGui import QDropEvent
from PyQt5.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from labelme.app import MainWindow

from ..conftest import close_or_pause
from .conftest import MainWinFactory


def _make_drop_mime(paths: list[Path]) -> QMimeData:
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
    return mime


def _drag_enter_accepted(win: MainWindow, mime: QMimeData) -> bool:
    event = QDragEnterEvent(
        QPoint(0, 0),
        Qt.CopyAction,
        mime,
        Qt.LeftButton,
        Qt.NoModifier,
    )
    QApplication.sendEvent(win, event)
    return event.isAccepted()


def _send_drop(win: MainWindow, mime: QMimeData) -> None:
    event = QDropEvent(
        QPointF(0, 0),
        Qt.CopyAction,
        mime,
        Qt.LeftButton,
        Qt.NoModifier,
    )
    QApplication.sendEvent(win, event)


@pytest.mark.gui
def test_drop_image_files_loads_them(
    qtbot: QtBot,
    main_win: MainWinFactory,
    data_path: Path,
    pause: bool,
) -> None:
    win = main_win()
    win.show()
    qtbot.waitUntil(win.isVisible)

    first_image = data_path / "raw/2011_000003.jpg"
    second_image = data_path / "raw/2011_000006.jpg"

    mime = _make_drop_mime(paths=[first_image, second_image])
    assert _drag_enter_accepted(win=win, mime=mime)
    _send_drop(win=win, mime=mime)

    def check_image_list_populated() -> None:
        assert len(win.image_list) == 2
        assert str(first_image) in win.image_list
        assert str(second_image) in win.image_list

    qtbot.waitUntil(check_image_list_populated)
    assert first_image.name in win.windowTitle()

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_drag_enter_rejects_non_image_and_keeps_state(
    qtbot: QtBot,
    raw_win: MainWindow,
    data_path: Path,
    tmp_path: Path,
    pause: bool,
) -> None:
    original_title = raw_win.windowTitle()
    original_image_list = list(raw_win.image_list)

    non_image_file = tmp_path / "notes.txt"
    non_image_file.write_text("not an image")
    directory = data_path / "raw"

    for path in [directory, non_image_file]:
        mime = _make_drop_mime(paths=[path])
        assert not _drag_enter_accepted(win=raw_win, mime=mime)

    assert raw_win.windowTitle() == original_title
    assert list(raw_win.image_list) == original_image_list

    close_or_pause(qtbot=qtbot, widget=raw_win, pause=pause)
