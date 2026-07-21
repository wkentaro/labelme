from __future__ import annotations

import numpy as np
import PIL.Image
import pytest
from numpy.typing import NDArray
from pytestqt.qtbot import QtBot

from labelme._utils.image import img_qt_to_arr
from labelme._widgets.brightness_contrast_dialog import BrightnessContrastDialog


@pytest.fixture
def rgba_img() -> PIL.Image.Image:
    arr = np.zeros((3, 4, 4), dtype=np.uint8)
    arr[..., 0] = 100
    arr[..., 1] = 150
    arr[..., 2] = 200
    arr[..., 3] = np.arange(12, dtype=np.uint8).reshape(3, 4) * 20
    return PIL.Image.fromarray(arr, mode="RGBA")


def _make_dialog(
    qtbot: QtBot, img: PIL.Image.Image
) -> tuple[BrightnessContrastDialog, list[NDArray[np.uint8]]]:
    captured: list[NDArray[np.uint8]] = []
    dialog = BrightnessContrastDialog(
        img=img, callback=lambda qimage: captured.append(img_qt_to_arr(qimage))
    )
    qtbot.addWidget(dialog)
    return dialog, captured


def test_apply_preserves_rgba_at_identity(
    qtbot: QtBot, rgba_img: PIL.Image.Image
) -> None:
    dialog, captured = _make_dialog(qtbot, rgba_img)

    dialog.apply()

    src = np.asarray(rgba_img)
    assert captured[-1].shape == src.shape
    np.testing.assert_array_equal(captured[-1], src)


def test_slider_change_preserves_alpha_while_brightening(
    qtbot: QtBot, rgba_img: PIL.Image.Image
) -> None:
    dialog, captured = _make_dialog(qtbot, rgba_img)

    dialog.slider_brightness.setValue(75)

    assert captured, "moving a slider should re-run apply() via valueChanged"
    src = np.asarray(rgba_img)
    np.testing.assert_array_equal(captured[-1][..., 3], src[..., 3])
    assert not np.array_equal(captured[-1][..., :3], src[..., :3])


def test_apply_outputs_rgb_without_alpha_channel(qtbot: QtBot) -> None:
    rgb_img = PIL.Image.new("RGB", (4, 3), color=(100, 150, 200))
    dialog, captured = _make_dialog(qtbot, rgb_img)

    dialog.apply()

    assert captured[-1].shape == (3, 4, 3)
    np.testing.assert_array_equal(captured[-1], np.asarray(rgb_img))
