from __future__ import annotations

import PIL.Image
from pytestqt.qtbot import QtBot

from labelme._widgets.brightness_contrast_dialog import BrightnessContrastDialog


def test_initial_width_includes_slider_padding(qtbot: QtBot) -> None:
    dialog = BrightnessContrastDialog(
        img=PIL.Image.new("RGB", (8, 8)), callback=lambda _qimage: None
    )
    qtbot.addWidget(dialog)

    assert dialog.width() == dialog.sizeHint().width() + 300
