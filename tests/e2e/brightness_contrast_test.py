from __future__ import annotations

from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

import labelme.utils
from labelme.widgets.brightness_contrast_dialog import BrightnessContrastDialog

from ..conftest import close_or_pause
from .conftest import MainWinFactory
from .conftest import show_window_and_wait_for_imagedata


@pytest.mark.gui
def test_brightness_contrast_dialog(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    pause: bool,
) -> None:
    win = main_win(
        file_or_dir=str(data_path / "annotated/2011_000003.json"),
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    canvas = win._canvas_widgets.canvas
    original_pixmap = canvas.pixmap.copy()

    assert win._image_data is not None
    dialog = BrightnessContrastDialog(
        img=labelme.utils.img_data_to_pil(win._image_data),
        callback=win._on_brightness_contrast_changed,
        parent=win,
    )
    qtbot.addWidget(dialog)

    dialog.slider_brightness.setValue(75)
    dialog.slider_contrast.setValue(25)
    dialog.apply()

    updated_pixmap = canvas.pixmap
    assert original_pixmap.toImage() != updated_pixmap.toImage()

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)
