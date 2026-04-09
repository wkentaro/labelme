from __future__ import annotations

from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

import labelme.app
import labelme.utils
from labelme.widgets.brightness_contrast_dialog import BrightnessContrastDialog

from ..conftest import close_or_pause
from .conftest import show_window_and_wait_for_imagedata


@pytest.mark.gui
def test_brightness_contrast_dialog(
    qtbot: QtBot,
    data_path: Path,
    pause: bool,
) -> None:
    win = labelme.app.MainWindow(
        file_or_dir=str(data_path / "annotated/2011_000003.json"),
    )
    qtbot.addWidget(win)
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    canvas = win._canvas_widgets.canvas
    original_pixmap = canvas.pixmap.copy()

    assert win.imageData is not None
    dialog = BrightnessContrastDialog(
        img=labelme.utils.img_data_to_pil(win.imageData),
        callback=win.onNewBrightnessContrast,
        parent=win,
    )
    qtbot.addWidget(dialog)

    dialog.slider_brightness.setValue(75)
    dialog.slider_contrast.setValue(25)
    dialog.onNewValue(None)

    updated_pixmap = canvas.pixmap
    assert original_pixmap.toImage() != updated_pixmap.toImage()

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)
