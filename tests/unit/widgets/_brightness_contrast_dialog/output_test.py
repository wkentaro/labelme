from __future__ import annotations

import numpy as np
import PIL.Image
from PySide6 import QtWidgets
from pytestqt.qtbot import QtBot

from labelme._utils._image import img_qt_to_arr
from labelme._widgets._brightness_contrast_dialog import BrightnessContrastDialog


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

    dialog.slider_brightness.setValue(200)
    dialog.slider_contrast.setValue(0)

    expected = np.full((1, 2, 3), 128, dtype=np.uint8)
    np.testing.assert_array_equal(captured[-1], expected)


def test_restore_defaults_publishes_the_original_image(*, qtbot: QtBot) -> None:
    pixels = np.array([[[10, 20, 30], [200, 150, 100]]], dtype=np.uint8)
    captured: list[np.ndarray] = []
    dialog = BrightnessContrastDialog(
        img=PIL.Image.fromarray(pixels, mode="RGB"),
        callback=lambda image: captured.append(img_qt_to_arr(image)),
    )
    qtbot.addWidget(dialog)
    dialog.slider_brightness.setValue(200)
    dialog.slider_contrast.setValue(50)

    buttons = dialog.findChild(QtWidgets.QDialogButtonBox)
    assert buttons is not None
    restore = buttons.button(QtWidgets.QDialogButtonBox.StandardButton.RestoreDefaults)
    assert restore is not None
    restore.click()

    assert dialog.slider_brightness.value() == 100
    assert dialog.slider_contrast.value() == 100
    np.testing.assert_array_equal(captured[-1], pixels)
