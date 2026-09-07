from __future__ import annotations

import PIL.Image
from PySide6 import QtGui
from PySide6 import QtWidgets
from pytestqt.qtbot import QtBot

from labelme._widgets.brightness_contrast_dialog import BrightnessContrastDialog


def test_sliders_have_names_and_visible_buddy_labels(*, qtbot: QtBot) -> None:
    dialog = BrightnessContrastDialog(
        img=PIL.Image.new("RGB", (1, 1)), callback=lambda _image: None
    )
    qtbot.addWidget(dialog)
    with qtbot.waitExposed(dialog):
        dialog.show()

    labels = {label.text(): label for label in dialog.findChildren(QtWidgets.QLabel)}
    brightness_label = labels[dialog.tr("Brightness:")]
    contrast_label = labels[dialog.tr("Contrast:")]

    assert dialog.slider_brightness.accessibleName() == dialog.tr("Brightness")
    assert dialog.slider_contrast.accessibleName() == dialog.tr("Contrast")
    assert dialog.slider_brightness.singleStep() == 2
    assert dialog.slider_brightness.pageStep() == 20
    assert (
        QtGui.QAccessible.queryAccessibleInterface(dialog.slider_brightness)
        .valueInterface()
        .currentValue()
        == 100
    )
    assert (
        QtGui.QAccessible.queryAccessibleInterface(dialog.slider_contrast)
        .valueInterface()
        .currentValue()
        == 100
    )
    assert brightness_label.isVisibleTo(dialog)
    assert contrast_label.isVisibleTo(dialog)
    assert brightness_label.buddy() is dialog.slider_brightness
    assert contrast_label.buddy() is dialog.slider_contrast
