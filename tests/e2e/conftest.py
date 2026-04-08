from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from PyQt5.QtCore import QPoint
from PyQt5.QtCore import QPointF
from PyQt5.QtCore import QSettings
from pytestqt.qtbot import QtBot

import labelme.app
from labelme.widgets.canvas import Canvas


def image_to_widget_pos(canvas: Canvas, image_pos: QPointF) -> QPoint:
    widget_pos = (image_pos + canvas.offsetToCenter()) * canvas.scale
    return QPoint(int(widget_pos.x()), int(widget_pos.y()))


@pytest.fixture(autouse=True)
def _isolated_qtsettings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[None, None, None]:
    settings_file = tmp_path / "qtsettings.ini"
    settings: QSettings = QSettings(str(settings_file), QSettings.IniFormat)
    monkeypatch.setattr(
        labelme.app.QtCore, "QSettings", lambda *args, **kwargs: settings
    )
    yield


def show_window_and_wait_for_imagedata(
    qtbot: QtBot, win: labelme.app.MainWindow
) -> None:
    win.show()

    def check_imageData() -> None:
        assert hasattr(win, "imageData")
        assert win.imageData is not None

    qtbot.waitUntil(check_imageData)
