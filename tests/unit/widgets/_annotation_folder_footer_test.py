from __future__ import annotations

from pathlib import Path

import pytest
from PySide6 import QtGui
from PySide6 import QtWidgets
from pytestqt.qtbot import QtBot

from labelme._widgets._annotation_folder_footer import AnnotationFolderFooter


def _ignore() -> None:
    return


def _palette(*, window: str, text: str, highlight: str) -> QtGui.QPalette:
    palette = QtGui.QPalette()
    palette.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor(window))
    palette.setColor(QtGui.QPalette.ColorRole.WindowText, QtGui.QColor(text))
    palette.setColor(QtGui.QPalette.ColorRole.Highlight, QtGui.QColor(highlight))
    return palette


def _text(footer: AnnotationFolderFooter, /) -> str:
    labels = footer.findChildren(QtWidgets.QLabel)
    return " ".join(
        label.text() for label in labels if label.isVisibleTo(footer) and label.text()
    )


def _menu(footer: AnnotationFolderFooter, /) -> QtWidgets.QMenu:
    menu = footer.findChild(QtWidgets.QMenu)
    assert menu is not None
    return menu


@pytest.mark.parametrize(
    "palette",
    [
        _palette(window="#efefef", text="#000000", highlight="#308cc6"),
        _palette(window="#353535", text="#ffffff", highlight="#2a82da"),
    ],
    ids=["light", "dark"],
)
def test_set_state_is_tinted(
    *,
    qtbot: QtBot,
    qapp: QtWidgets.QApplication,
    palette: QtGui.QPalette,
) -> None:
    original_palette = qapp.palette()
    footer = AnnotationFolderFooter(on_choose=_ignore, on_next_to_images=_ignore)
    qtbot.addWidget(footer)
    footer.resize(240, 32)
    try:
        # A live theme switch arrives as an application palette change.
        qapp.setPalette(palette)
        window = palette.color(QtGui.QPalette.ColorRole.Window)
        qtbot.waitUntil(lambda: footer.grab().toImage().pixelColor(1, 1) == window)

        footer.set_folder(Path("/data/annotations"))
        tint = footer.grab().toImage().pixelColor(1, 1)
        assert tint != window
        # The tint stays close to the window color so text keeps its contrast.
        assert abs(tint.lightness() - window.lightness()) < 40
    finally:
        qapp.setPalette(original_palette)


def test_states_and_menu(*, qtbot: QtBot) -> None:
    footer = AnnotationFolderFooter(on_choose=_ignore, on_next_to_images=_ignore)
    qtbot.addWidget(footer)
    next_to_images, choose = _menu(footer).actions()
    assert choose.text() == "Choose Annotation Folder…"

    assert _text(footer) == "0 of 0 annotated · next to images"
    assert next_to_images.isChecked()

    footer.set_folder(Path("/data/out"))
    assert "out" in _text(footer)
    assert footer.toolTip() == str(Path("/data/out"))
    assert not next_to_images.isChecked()

    footer.set_folder(None)
    footer.set_missing("/mnt/usb/out")
    assert "Not found: out · next to images" in _text(footer)
    assert footer.toolTip() == "/mnt/usb/out"
    assert next_to_images.isChecked()

    # A folder hides the warning; going back without clearing shows it again.
    footer.set_folder(Path("/data/out"))
    assert "out" in _text(footer)
    footer.set_folder(None)
    assert "Not found" in _text(footer)

    footer.set_missing(None)
    assert _text(footer) == "0 of 0 annotated · next to images"


def test_next_to_images_stays_checked_when_the_switch_is_refused(
    *, qtbot: QtBot
) -> None:
    footer = AnnotationFolderFooter(on_choose=_ignore, on_next_to_images=_ignore)
    qtbot.addWidget(footer)
    footer.set_folder(Path("/data/out"))
    next_to_images = _menu(footer).actions()[0]

    next_to_images.trigger()

    assert not next_to_images.isChecked()


def test_count_text(*, qtbot: QtBot) -> None:
    footer = AnnotationFolderFooter(on_choose=_ignore, on_next_to_images=_ignore)
    qtbot.addWidget(footer)

    footer.set_count(annotated=3, total=5)
    assert _text(footer) == "3 of 5 annotated · next to images"

    footer.set_folder(Path("/data/out"))
    assert _text(footer) == "3 of 5 annotated in out"

    # The warning replaces the count.
    footer.set_folder(None)
    footer.set_missing("/mnt/usb/out")
    assert _text(footer) == "Not found: out · next to images"
