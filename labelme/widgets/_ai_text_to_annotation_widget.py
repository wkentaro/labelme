from collections.abc import Callable

from PyQt5 import QtCore
from PyQt5 import QtGui
from PyQt5 import QtWidgets

from ._info_button import InfoButton


class AiTextToAnnotationWidget(QtWidgets.QWidget):
    _available_models: list[tuple[str, str]] = [
        ("sam3:latest", "SAM3 (smart)"),
        ("yoloworld:latest", "YOLO-World (fast)"),
    ]
    _default_model_name: str = "yoloworld:latest"
    _default_score_threshold: float = 0.1
    _default_iou_threshold: float = 0.5

    _text_input: QtWidgets.QLineEdit
    _model_combo: QtWidgets.QComboBox
    _score_spinbox: QtWidgets.QDoubleSpinBox
    _iou_spinbox: QtWidgets.QDoubleSpinBox
    _body: QtWidgets.QWidget

    def __init__(self, on_submit, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent=parent)
        self._init_ui(on_submit)

    def _init_ui(self, on_submit: Callable[[], None]) -> None:
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        self.setLayout(layout)

        header_layout = QtWidgets.QHBoxLayout()
        header_layout.addStretch()
        label = QtWidgets.QLabel(self.tr("AI Text-to-Annotation"))
        header_layout.addWidget(label)
        info_button = InfoButton(
            tooltip=self.tr("AI creates annotations from the text prompt")
        )
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
        run_button.setCursor(QtCore.Qt.PointingHandCursor)
        run_button.clicked.connect(on_submit)
        grid.addWidget(run_button, 0, 1)

        settings_layout = QtWidgets.QHBoxLayout()
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings_layout.setSpacing(4)

        self._model_combo = model_combo = QtWidgets.QComboBox()
        for model_id, model_display in self._available_models:
            model_combo.addItem(model_display, model_id)
        model_index = next(
            (
                i
                for i, (mid, _) in enumerate(self._available_models)
                if mid == self._default_model_name
            ),
            0,
        )
        model_combo.setCurrentIndex(model_index)
        settings_layout.addWidget(model_combo, stretch=1)

        score_label = QtWidgets.QLabel(self.tr("Score"))
        score_label.setStyleSheet("color: gray; font-size: 10px;")
        settings_layout.addWidget(score_label)
        #
        self._score_spinbox = score_spinbox = QtWidgets.QDoubleSpinBox()
        score_spinbox.setStyleSheet("font-size: 10px;")
        score_spinbox.setFixedWidth(50)
        score_spinbox.setRange(0, 1)
        score_spinbox.setSingleStep(0.05)
        score_spinbox.setValue(self._default_score_threshold)
        settings_layout.addWidget(score_spinbox)

        iou_label = QtWidgets.QLabel(self.tr("IoU"))
        iou_label.setStyleSheet("color: gray; font-size: 10px;")
        settings_layout.addWidget(iou_label)
        #
        self._iou_spinbox = iou_spinbox = QtWidgets.QDoubleSpinBox()
        iou_spinbox.setStyleSheet("font-size: 10px;")
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
        return self._model_combo.currentData()

    def get_score_threshold(self) -> float:
        return self._score_spinbox.value()

    def get_iou_threshold(self) -> float:
        return self._iou_spinbox.value()

    def setEnabled(self, a0: bool) -> None:
        self._body.setEnabled(a0)

    def eventFilter(self, a0: QtCore.QObject, a1: QtCore.QEvent) -> bool:
        if a0 == self._body and not self._body.isEnabled():
            if a1.type() == QtCore.QEvent.Enter:
                QtWidgets.QToolTip.showText(
                    QtGui.QCursor.pos(),
                    self.tr(
                        "Select 'Polygon', 'Rectangle', 'AI-Polygon', or 'AI-Mask' "
                        "mode to enable"
                    ),
                    self._body,
                )
        return super().eventFilter(a0, a1)
