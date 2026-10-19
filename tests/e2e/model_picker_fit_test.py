from __future__ import annotations

import pytest
from PySide6 import QtWidgets

from labelme._locale import TRANSLATE_DIR
from labelme._widgets._model_picker import ModelPicker

from .conftest import MainWinFactory


@pytest.mark.gui
@pytest.mark.parametrize(
    "language", ["en_US", *sorted(path.stem for path in TRANSLATE_DIR.glob("*.qm"))]
)
def test_model_picker_text_fits(*, main_win: MainWinFactory, language: str) -> None:
    # Before its model is downloaded, a picker shows the model name as its
    # placeholder; neither that nor a selected name may be cut off.
    win = main_win(config_overrides={"language": language})
    win.resize(1800, 800)
    win.show()
    for picker in win.findChildren(ModelPicker):
        text = (
            picker.placeholderText()
            if picker.currentIndex() < 0
            else picker.currentText()
        )
        option = QtWidgets.QStyleOptionComboBox()
        picker.initStyleOption(option)
        field = picker.style().subControlRect(
            QtWidgets.QStyle.ComplexControl.CC_ComboBox,
            option,
            QtWidgets.QStyle.SubControl.SC_ComboBoxEditField,
            picker,
        )
        assert picker.fontMetrics().horizontalAdvance(text) <= field.width(), text
