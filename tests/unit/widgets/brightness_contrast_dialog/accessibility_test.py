from __future__ import annotations

import PIL.Image
from PySide6 import QtGui
from pytestqt.qtbot import QtBot

from labelme._widgets.brightness_contrast_dialog import BrightnessContrastDialog


def test_sliders_expose_names_values_and_keyboard_steps(*, qtbot: QtBot) -> None:
    dialog = BrightnessContrastDialog(
        img=PIL.Image.new("RGB", (1, 1)), callback=lambda _image: None
    )
    qtbot.addWidget(dialog)
    with qtbot.waitExposed(dialog):
        dialog.show()

    for slider, name in (
        (dialog.slider_brightness, dialog.tr("Brightness:")),
        (dialog.slider_contrast, dialog.tr("Contrast:")),
    ):
        interface = QtGui.QAccessible.queryAccessibleInterface(slider)
        assert interface.text(QtGui.QAccessible.Text.Name) == name
        assert interface.valueInterface().currentValue() == 100
        assert slider.singleStep() == 2
        assert slider.pageStep() == 20
