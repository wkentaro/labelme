from __future__ import annotations

import pytest
from pytestqt.qtbot import QtBot

import labelme.utils
from labelme.app import MainWindow
from labelme.widgets.brightness_contrast_dialog import BrightnessContrastDialog

from ..conftest import close_or_pause


@pytest.mark.gui
def test_brightness_contrast_dialog(
    annotated_win: MainWindow,
    qtbot: QtBot,
    pause: bool,
) -> None:
    canvas = annotated_win._canvas_widgets.canvas
    original_pixmap = canvas.pixmap.copy()

    assert annotated_win._image_data is not None
    dialog = BrightnessContrastDialog(
        img=labelme.utils.img_data_to_pil(annotated_win._image_data),
        callback=annotated_win._on_brightness_contrast_changed,
        parent=annotated_win,
    )
    qtbot.addWidget(dialog)

    dialog.slider_brightness.setValue(75)
    dialog.slider_contrast.setValue(25)
    dialog.apply()

    updated_pixmap = canvas.pixmap
    assert original_pixmap.toImage() != updated_pixmap.toImage()

    close_or_pause(qtbot=qtbot, widget=annotated_win, pause=pause)
