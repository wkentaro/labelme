from __future__ import annotations

import pytest
from PySide6 import QtGui
from PySide6 import QtWidgets
from pytestqt.qtbot import QtBot

from labelme._utils import new_icon
from labelme._widgets.empty_state import EmptyStateWidget


def _ignore_checked(_checked: bool) -> None:
    return


@pytest.fixture()
def empty_state(qtbot: QtBot) -> EmptyStateWidget:
    widget = EmptyStateWidget(
        on_open_image=_ignore_checked,
        on_open_directory=_ignore_checked,
    )
    qtbot.addWidget(widget)
    widget.resize(640, 480)
    return widget


@pytest.mark.parametrize(
    "background",
    [
        pytest.param("#ffffff", id="light"),
        pytest.param("#202124", id="dark"),
    ],
)
def test_empty_state_renders_theme_background(
    empty_state: EmptyStateWidget,
    qtbot: QtBot,
    background: str,
) -> None:
    palette = empty_state.palette()
    palette.setColor(QtGui.QPalette.ColorRole.Base, QtGui.QColor(background))
    empty_state.setPalette(palette)

    empty_state.show()
    qtbot.waitExposed(empty_state)
    rendered = empty_state.grab().toImage()

    assert rendered.pixelColor(0, 0) == QtGui.QColor(background)


def test_empty_state_icon_rethemes_with_application_palette(
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


def test_empty_state_visual_hierarchy_is_centered(
    empty_state: EmptyStateWidget,
    qtbot: QtBot,
) -> None:
    empty_state.show()
    qtbot.waitExposed(empty_state)

    heading = empty_state.findChild(QtWidgets.QLabel, "emptyStateHeading")
    explanation = empty_state.findChild(QtWidgets.QLabel, "emptyStateExplanation")
    open_image = empty_state.findChild(QtWidgets.QPushButton, "emptyStateOpenImage")
    drop_hint = empty_state.findChild(QtWidgets.QLabel, "emptyStateDropHint")

    assert heading is not None
    assert explanation is not None
    assert open_image is not None
    assert drop_hint is not None
    assert heading.font().pointSizeF() > explanation.font().pointSizeF()
    assert heading.geometry().bottom() < explanation.geometry().top()
    assert explanation.geometry().bottom() < open_image.geometry().top()
    assert open_image.geometry().bottom() < drop_hint.geometry().top()
    heading_center = heading.mapTo(empty_state, heading.rect().center())
    assert abs(heading_center.x() - empty_state.rect().center().x()) <= 1
