from __future__ import annotations

import numpy as np
import PIL.Image
from pytestqt.qtbot import QtBot

from labelme._utils.image import img_qt_to_arr
from labelme._widgets.brightness_contrast_dialog import BrightnessContrastDialog


def test_combined_adjustment_preserves_clipped_brightness_pivot(
    *, qtbot: QtBot
) -> None:
    source = PIL.Image.fromarray(
        np.array([[[0, 0, 0], [255, 255, 255]]], dtype=np.uint8), mode="RGB"
    )
    captured: list[np.ndarray] = []
    dialog = BrightnessContrastDialog(
        img=source, callback=lambda image: captured.append(img_qt_to_arr(image))
    )
    qtbot.addWidget(dialog)

    dialog.slider_brightness.setValue(100)
    dialog.slider_contrast.setValue(0)

    expected = np.full((1, 2, 3), 128, dtype=np.uint8)
    np.testing.assert_array_equal(captured[-1], expected)
