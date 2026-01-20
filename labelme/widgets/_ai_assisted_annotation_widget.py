from collections.abc import Callable

from loguru import logger
from PyQt5 import QtCore
from PyQt5 import QtGui
from PyQt5 import QtWidgets

from ._info_button import InfoButton


class AiAssistedAnnotationWidget(QtWidgets.QWidget):
    _available_models: list[tuple[str, str]] = [
        ("efficientsam:10m", "EfficientSam (speed)"),
        ("efficientsam:latest", "EfficientSam (accuracy)"),
        ("sam:100m", "Sam (speed)"),
        ("sam:300m", "Sam (balanced)"),
        ("sam:latest", "Sam (accuracy)"),
        ("sam2:small", "Sam2 (speed)"),
        ("sam2:latest", "Sam2 (balanced)"),
        ("sam2:large", "Sam2 (accuracy)"),
    ]

    _model_combo: QtWidgets.QComboBox
    _body: QtWidgets.QWidget

    def __init__(
        self,
        default_model: str,
        on_model_changed: Callable[[str], None],
        parent: QtWidgets.QWidget | None = None,
    ):
        super().__init__(parent=parent)
        self._init_ui(default_model=default_model, on_model_changed=on_model_changed)

    def _init_ui(
        self, default_model: str, on_model_changed: Callable[[str], None]
    ) -> None:
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        self.setLayout(layout)

        header_layout = QtWidgets.QHBoxLayout()
        header_layout.addStretch()
        label = QtWidgets.QLabel(self.tr("AI-Assisted Annotation"))
        header_layout.addWidget(label)
        info_button = InfoButton(
            tooltip=self.tr(
                "AI suggests annotation in 'AI-Polygon' and 'AI-Mask' modes"
            )
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

        self._model_combo = QtWidgets.QComboBox()
        for model_id, model_display in self._available_models:
            self._model_combo.addItem(model_display, model_id)
        body_layout.addWidget(self._model_combo)

        layout.addWidget(body)

        model_ui_names = [model_display for _, model_display in self._available_models]
        if default_model in model_ui_names:
            model_index = model_ui_names.index(default_model)
        else:
            logger.warning("Default AI model is not found: %r", default_model)
            model_index = 0

        self._model_combo.currentIndexChanged.connect(
            lambda index: on_model_changed(self._model_combo.itemData(index))
        )
        self._model_combo.setCurrentIndex(model_index)

        self.setMaximumWidth(200)

    def setEnabled(self, a0: bool) -> None:
        self._body.setEnabled(a0)

    def eventFilter(self, a0: QtCore.QObject, a1: QtCore.QEvent) -> bool:
        if a0 == self._body and not self._body.isEnabled():
            if a1.type() == QtCore.QEvent.Enter:
                QtWidgets.QToolTip.showText(
                    QtGui.QCursor.pos(),
                    self.tr(
                        "Select 'AI-Polygon' or 'AI-Mask' mode "
                        "to enable AI-Assisted Annotation"
                    ),
                    self._body,
                )
        return super().eventFilter(a0, a1)
