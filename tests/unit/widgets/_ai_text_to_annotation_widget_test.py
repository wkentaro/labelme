from __future__ import annotations

import sys

import pytest
from PySide6 import QtGui
from pytestqt.qtbot import QtBot

from labelme._widgets._ai_text_to_annotation_widget import AiTextToAnnotationWidget
from labelme._widgets._ai_text_to_annotation_widget import _keycap_outline


def test_focusable_controls_expose_accessible_names(*, qtbot: QtBot) -> None:
    widget = AiTextToAnnotationWidget(on_submit=lambda: None)
    qtbot.addWidget(widget)
    widget.set_model_name(model_name="sam3:latest")

    run_button = widget._run_button

    model_name = widget.tr("Model") if sys.platform == "win32" else "SAM 3"
    for control, name in (
        (widget._text_input, widget.tr("Prompt")),
        (widget._model_combo, model_name),
        (widget._score_spinbox, widget.tr("Score")),
        (widget._iou_spinbox, widget.tr("IoU")),
        (run_button, widget.tr("Run")),
    ):
        interface = QtGui.QAccessible.queryAccessibleInterface(control)
        assert interface.text(QtGui.QAccessible.Text.Name) == name

    interface = QtGui.QAccessible.queryAccessibleInterface(widget._model_combo)
    assert interface.text(QtGui.QAccessible.Text.Value) == "SAM 3"
    assert interface.text(QtGui.QAccessible.Text.Description) == widget.tr(
        "AI-Find All model"
    )


@pytest.mark.parametrize(
    ("base", "text"),
    [
        ("#ffffff", "#000000"),
        # macOS's dark palette, where Mid (#151515) all but matches Base.
        ("#171717", "#ffffff"),
    ],
    ids=["light", "macos-dark"],
)
def test_keycap_outline_stands_out_from_the_field(*, base: str, text: str) -> None:
    palette = QtGui.QPalette()
    palette.setColor(QtGui.QPalette.ColorRole.Base, QtGui.QColor(base))
    palette.setColor(QtGui.QPalette.ColorRole.Text, QtGui.QColor(text))

    outline = _keycap_outline(palette)

    assert abs(outline.lightness() - QtGui.QColor(base).lightness()) > 60
