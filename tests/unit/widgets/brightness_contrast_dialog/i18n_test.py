from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from xml.etree import ElementTree

import PIL.Image
import pytest
from PySide6 import QtWidgets
from PySide6.QtCore import QCoreApplication
from PySide6.QtCore import QTranslator
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from labelme import _locale
from labelme._widgets import brightness_contrast_dialog
from labelme._widgets.brightness_contrast_dialog import BrightnessContrastDialog

_LOCALE = "ja_JP"
_SLIDER_LABELS = ("Brightness:", "Contrast:")


@pytest.fixture()
def japanese_translator(qapp: QApplication) -> Iterator[None]:
    translator = QTranslator()
    assert translator.load(str(_locale.TRANSLATE_DIR / f"{_LOCALE}.qm"))
    qapp.installTranslator(translator)
    yield
    qapp.removeTranslator(translator)


def test_slider_labels_are_extractable_by_lupdate(tmp_path: Path) -> None:
    lupdate = shutil.which(
        "pyside6-lupdate", path=str(Path(sys.executable).parent)
    ) or shutil.which("pyside6-lupdate")
    assert lupdate is not None, "pyside6-lupdate ships with the pyside6 dependency"

    ts_path = tmp_path / "extracted.ts"
    result = subprocess.run(
        [lupdate, brightness_contrast_dialog.__file__, "-ts", str(ts_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    sources = {element.text for element in ElementTree.parse(ts_path).iter("source")}
    assert set(_SLIDER_LABELS) <= sources


@pytest.mark.usefixtures("japanese_translator")
def test_slider_labels_render_the_installed_translation(qtbot: QtBot) -> None:
    translated = {
        source: QCoreApplication.translate("BrightnessContrastDialog", source)
        for source in _SLIDER_LABELS
    }
    for source, text in translated.items():
        assert text != source, f"{source!r} is missing from the {_LOCALE} catalog"

    dialog = BrightnessContrastDialog(
        img=PIL.Image.new("RGB", (8, 8)), callback=lambda _qimage: None
    )
    qtbot.addWidget(dialog)

    label_texts = {label.text() for label in dialog.findChildren(QtWidgets.QLabel)}
    assert set(translated.values()) <= label_texts
