from __future__ import annotations

import pytest
from PySide6.QtCore import QPointF
from pytestqt.qtbot import QtBot

import labelme._utils
from labelme._app import MainWindow
from labelme._widgets.brightness_contrast_dialog import BrightnessContrastDialog

from ..conftest import close_or_pause


@pytest.mark.gui
def test_brightness_contrast_dialog(
    *,
    annotated_win: MainWindow,
    qtbot: QtBot,
    pause: bool,
) -> None:
    canvas = annotated_win._canvas_widgets.canvas
    original_pixmap = canvas.pixmap.copy()
    canvas.pan_view(step=QPointF(17, 23), constrain_to_center=False)
    expected_view_offset = canvas.get_view_offset()

    assert annotated_win._annotation is not None
    dialog = BrightnessContrastDialog(
        img=labelme._utils.img_data_to_pil(annotated_win._annotation.image_data),
        callback=annotated_win._on_brightness_contrast_changed,
        parent=annotated_win,
    )
    qtbot.addWidget(dialog)

    dialog.slider_brightness.setValue(75)
    dialog.slider_contrast.setValue(25)
    dialog.apply()

    updated_pixmap = canvas.pixmap
    assert original_pixmap.toImage() != updated_pixmap.toImage()
    assert canvas.get_view_offset() == expected_view_offset

    close_or_pause(qtbot=qtbot, widget=annotated_win, pause=pause)
