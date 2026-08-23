from __future__ import annotations

from collections.abc import Callable

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from .. import _ai_models
from ._info_button import InfoButton
from .download import show_ai_model_info


class AiTextToAnnotationWidget(QtWidgets.QWidget):
    _default_model_name: str = "yoloworld:latest"
    _default_score_threshold: float = 0.1
    _default_iou_threshold: float = 0.5

    _text_input: QtWidgets.QLineEdit
    _model_combo: QtWidgets.QComboBox
    _score_spinbox: QtWidgets.QDoubleSpinBox
    _iou_spinbox: QtWidgets.QDoubleSpinBox
    _body: QtWidgets.QWidget

    def __init__(
        self,
        on_submit: Callable[[bool], None],
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self._init_ui(on_submit)

    def _init_ui(self, on_submit: Callable[[bool], None]) -> None:
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        self.setLayout(layout)

        header_layout = QtWidgets.QHBoxLayout()
        header_layout.addStretch()
        label = QtWidgets.QLabel(self.tr("AI Text-to-Annotation"))
        header_layout.addWidget(label)
        info_button = InfoButton(
            tooltip=self.tr(
                "AI creates annotations from the text prompt. "
                "Click for model license and source."
            )
        )
        info_button.setAccessibleName(self.tr("Model license and source"))
        header_layout.addWidget(info_button)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        self._body = body = QtWidgets.QWidget()
        body.installEventFilter(self)
        body_layout = QtWidgets.QVBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        body.setLayout(body_layout)

        grid = QtWidgets.QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(2)

        text_input = QtWidgets.QLineEdit()
        text_input.setPlaceholderText(self.tr("e.g., dog,cat,bird"))
        text_input.setFixedHeight(24)
        grid.addWidget(text_input, 0, 0)
        self._text_input = text_input

        run_button = QtWidgets.QToolButton()
        run_button.setText(self.tr("Run"))
        run_button.setFixedHeight(24)
        run_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        run_button.clicked.connect(on_submit)
        grid.addWidget(run_button, 0, 1)

        settings_layout = QtWidgets.QHBoxLayout()
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings_layout.setSpacing(4)

        self._model_combo = model_combo = QtWidgets.QComboBox()
        for model_name, display_name in (
            ("sam3:latest", "SAM3 (smart)"),
            ("yoloworld:latest", "YOLO-World (fast)"),
        ):
            if _ai_models.is_model_available(model_name=model_name):
                model_combo.addItem(display_name, model_name)
        model_combo.setCurrentIndex(
            max(model_combo.findData(self._default_model_name), 0)
        )
        if model_combo.count() == 0:
            body.setToolTip(self.tr("No text-to-annotation model is included."))
        info_button.setEnabled(model_combo.count() > 0)
        info_button.clicked.connect(
            lambda: show_ai_model_info(model_name=self.get_model_name(), parent=self)
        )
        settings_layout.addWidget(model_combo, stretch=1)

        # Size and mute these via QFont and a palette role, never a stylesheet:
        # a stylesheet switches the widget to QStyleSheetStyle, which pins its
        # resolved colors at polish time and does not re-resolve them on a live
        # color-scheme change, leaving the text faded after a mid-session theme
        # switch.
        small_font = self.font()
        small_font.setPixelSize(10)

        def make_threshold_label(text: str) -> QtWidgets.QLabel:
            label = QtWidgets.QLabel(text)
            label.setFont(small_font)
            label.setForegroundRole(QtGui.QPalette.ColorRole.PlaceholderText)
            return label

        settings_layout.addWidget(make_threshold_label(self.tr("Score")))
        #
        self._score_spinbox = score_spinbox = QtWidgets.QDoubleSpinBox()
        score_spinbox.setFont(small_font)
        score_spinbox.setFixedWidth(50)
        score_spinbox.setRange(0, 1)
        score_spinbox.setSingleStep(0.05)
        score_spinbox.setValue(self._default_score_threshold)
        settings_layout.addWidget(score_spinbox)

        settings_layout.addWidget(make_threshold_label(self.tr("IoU")))
        #
        self._iou_spinbox = iou_spinbox = QtWidgets.QDoubleSpinBox()
        iou_spinbox.setFont(small_font)
        iou_spinbox.setFixedWidth(50)
        iou_spinbox.setRange(0, 1)
        iou_spinbox.setSingleStep(0.05)
        iou_spinbox.setValue(self._default_iou_threshold)
        settings_layout.addWidget(iou_spinbox)

        grid.addLayout(settings_layout, 1, 0, 1, 2)

        body_layout.addLayout(grid)
        layout.addWidget(body)

        self.setMaximumWidth(320)

    def get_text_prompt(self) -> str:
        return self._text_input.text()

    def get_model_name(self) -> str:
        model_name = self._model_combo.currentData()
        if model_name is None:
            raise ValueError(self._body.toolTip())
        return model_name

    def get_model_display_name(self) -> str:
        return self._model_combo.currentText()

    def get_score_threshold(self) -> float:
        return self._score_spinbox.value()

    def get_iou_threshold(self) -> float:
        return self._iou_spinbox.value()

    def setEnabled(self, a0: bool) -> None:
        self._body.setEnabled(a0 and self._model_combo.count() > 0)

    def eventFilter(self, a0: QtCore.QObject, a1: QtCore.QEvent) -> bool:
        if a0 == self._body and not self._body.isEnabled():
            if a1.type() == QtCore.QEvent.Type.Enter:
                QtWidgets.QToolTip.showText(
                    QtGui.QCursor.pos(),
                    self._body.toolTip()
                    or self.tr(
                        "Select 'Polygon', 'Rectangle', or 'AI-Points' mode to enable"
                    ),
                    self._body,
                )
        return super().eventFilter(a0, a1)
