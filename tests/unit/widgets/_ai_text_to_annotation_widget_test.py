from __future__ import annotations

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

    assert widget._text_input.accessibleName() == widget.tr("Prompt")
    assert widget._model_combo.accessibleName() == widget.tr("Model")
    assert widget._model_combo.accessibleDescription() == widget.tr(
        "Text-to-annotation model"
    )
    assert widget._score_spinbox.accessibleName() == widget.tr("Score")
    assert widget._iou_spinbox.accessibleName() == widget.tr("IoU")
    assert run_button.accessibleName() == widget.tr("Run")
    assert info_button.accessibleName() == info_button.toolTip()

    labels = widget.findChildren(QtWidgets.QLabel)
    score_label = next(label for label in labels if label.text() == widget.tr("Score"))
    iou_label = next(label for label in labels if label.text() == widget.tr("IoU"))
    assert score_label.buddy() is widget._score_spinbox
    assert iou_label.buddy() is widget._iou_spinbox
