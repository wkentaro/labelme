from __future__ import annotations

from PySide6 import QtGui
from PySide6 import QtWidgets
from pytestqt.qtbot import QtBot

from labelme._widgets._ai_text_to_annotation_widget import AiTextToAnnotationWidget
from labelme._widgets._info_button import InfoButton


def test_focusable_controls_expose_accessible_names(*, qtbot: QtBot) -> None:
    widget = AiTextToAnnotationWidget(on_submit=lambda _checked: None)
    qtbot.addWidget(widget)

    run_button = next(
        button
        for button in widget.findChildren(QtWidgets.QToolButton)
        if button.text() == widget.tr("Run")
    )
    info_button = widget.findChild(InfoButton)
    assert info_button is not None

    for control, name in (
        (widget._text_input, widget.tr("Prompt")),
        (widget._model_combo, "YOLO-World (fast)"),
        (widget._score_spinbox, widget.tr("Score")),
        (widget._iou_spinbox, widget.tr("IoU")),
        (run_button, widget.tr("Run")),
        (info_button, widget.tr("AI creates annotations from the text prompt")),
    ):
        interface = QtGui.QAccessible.queryAccessibleInterface(control)
        assert interface.text(QtGui.QAccessible.Text.Name) == name

    interface = QtGui.QAccessible.queryAccessibleInterface(widget._model_combo)
    assert interface.text(QtGui.QAccessible.Text.Description) == widget.tr(
        "Text-to-annotation model"
    )
