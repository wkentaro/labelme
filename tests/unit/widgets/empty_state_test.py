from __future__ import annotations

import pytest
from PySide6 import QtGui
from PySide6 import QtWidgets
from pytestqt.qtbot import QtBot

from labelme._utils import new_icon
from labelme._widgets.empty_state import EmptyStateWidget


def _ignore_click() -> None:
    return


@pytest.fixture()
def empty_state(*, qtbot: QtBot) -> EmptyStateWidget:
    widget = EmptyStateWidget(
        on_open_image=_ignore_click,
        on_open_directory=_ignore_click,
    )
    qtbot.addWidget(widget)
    widget.resize(640, 480)
    return widget


def test_empty_state_icon_rethemes_with_application_palette(
    *,
    empty_state: EmptyStateWidget,
    qtbot: QtBot,
    qapp: QtWidgets.QApplication,
) -> None:
    original_palette = qapp.palette()
    icon = empty_state.findChild(QtWidgets.QLabel, "emptyStateIcon")
    assert icon is not None
    try:
        palette = qapp.palette()
        palette.setColor(QtGui.QPalette.ColorRole.WindowText, QtGui.QColor("#cc0000"))
        qapp.setPalette(palette)
        qtbot.waitUntil(lambda: icon.pixmap() is not None)
        red = icon.pixmap().toImage()

        palette.setColor(QtGui.QPalette.ColorRole.WindowText, QtGui.QColor("#0066cc"))
        qapp.setPalette(palette)
        qtbot.waitUntil(
            lambda: icon.pixmap() is not None and icon.pixmap().toImage() != red
        )

        expected = new_icon("phosphor/image-square.svg").pixmap(56, 56).toImage()
        assert icon.pixmap().toImage() == expected
    finally:
        qapp.setPalette(original_palette)
