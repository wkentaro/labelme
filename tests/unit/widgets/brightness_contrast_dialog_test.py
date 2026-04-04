from __future__ import annotations

import numpy as np
import PIL.Image
import pytest
from PyQt5.QtGui import QImage

from labelme.widgets.brightness_contrast_dialog import BrightnessContrastDialog


@pytest.mark.gui
def test_open_rgb_image_no_error(qtbot):
    """RGB images open without exception."""
    img = PIL.Image.new("RGB", (64, 64), (128, 128, 128))
    received: list[QImage] = []
    dialog = BrightnessContrastDialog(img, callback=received.append)
    qtbot.addWidget(dialog)
    assert dialog.img.mode == "RGB"
    assert dialog._alpha is None


@pytest.mark.gui
def test_open_rgba_image_no_error(qtbot):
    """RGBA images open without exception (post-PR-#1872 regression guard)."""
    img = PIL.Image.new("RGBA", (64, 64), (128, 128, 128, 200))
    received: list[QImage] = []
    # Should not raise ValueError
    dialog = BrightnessContrastDialog(img, callback=received.append)
    qtbot.addWidget(dialog)
    # Internal storage should be RGB (alpha stored separately)
    assert dialog.img.mode == "RGB"
    assert dialog._alpha is not None


@pytest.mark.gui
def test_brightness_value_applied(qtbot):
    """Setting brightness slider emits a QImage with changed mean brightness."""
    img = PIL.Image.new("RGB", (64, 64), (100, 100, 100))
    received: list[QImage] = []
    dialog = BrightnessContrastDialog(img, callback=received.append)
    qtbot.addWidget(dialog)

    # Move brightness slider to maximum (3x)
    dialog.slider_brightness.setValue(dialog.slider_brightness.maximum())

    assert len(received) >= 1
    qimage = received[-1]
    # Convert QImage to numpy array to check brightness
    assert qimage.format() == QImage.Format_RGB888
    width, height = qimage.width(), qimage.height()
    ptr = qimage.bits()
    ptr.setsize(height * width * 3)
    arr = np.frombuffer(ptr, dtype=np.uint8).reshape((height, width, 3))
    mean_bright = arr.mean()
    # Original was 100/255 ≈ 0.39; at 3x brightness should be significantly higher
    assert mean_bright > 150, f"Expected mean > 150 after brightness boost, got {mean_bright}"


@pytest.mark.gui
def test_contrast_value_applied(qtbot):
    """Setting contrast slider changes emitted QImage pixel spread."""
    # Use a gradient image so contrast changes have visible effect
    arr_base = np.zeros((64, 64, 3), dtype=np.uint8)
    arr_base[:, :32] = 64
    arr_base[:, 32:] = 192
    img = PIL.Image.fromarray(arr_base, mode="RGB")

    # Capture at default contrast (trigger callback by moving brightness slider)
    received_default: list[QImage] = []
    dialog_default = BrightnessContrastDialog(img, callback=received_default.append)
    qtbot.addWidget(dialog_default)
    # Trigger callback by moving brightness slider slightly from default
    dialog_default.slider_brightness.setValue(dialog_default._base_value + 1)
    assert len(received_default) >= 1
    qimage_default = received_default[-1]
    ptr_d = qimage_default.bits()
    ptr_d.setsize(64 * 64 * 3)
    arr_d = np.frombuffer(ptr_d, dtype=np.uint8).reshape((64, 64, 3)).astype(float)
    std_default = arr_d.std()

    # Capture at high contrast
    received_high: list[QImage] = []
    dialog_high = BrightnessContrastDialog(img, callback=received_high.append)
    qtbot.addWidget(dialog_high)
    dialog_high.slider_contrast.setValue(dialog_high.slider_contrast.maximum())
    assert len(received_high) >= 1
    qimage_high = received_high[-1]
    ptr_h = qimage_high.bits()
    ptr_h.setsize(64 * 64 * 3)
    arr_h = np.frombuffer(ptr_h, dtype=np.uint8).reshape((64, 64, 3)).astype(float)
    std_high = arr_h.std()

    assert std_high > std_default, (
        f"Expected higher std at max contrast ({std_high:.1f}) vs default ({std_default:.1f})"
    )
