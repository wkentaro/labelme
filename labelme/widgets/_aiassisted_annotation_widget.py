from collections.abc import Callable

from loguru import logger
from PyQt5 import QtCore
from PyQt5 import QtWidgets


class AiassistedAnnotationWidget(QtWidgets.QWidget):
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
        self.setLayout(layout)

        label = QtWidgets.QLabel(self.tr("AI-assisted annotation"))
        label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(label)

        self._model_combo = QtWidgets.QComboBox()
        for model_id, model_display in self._available_models:
            self._model_combo.addItem(model_display, model_id)
        layout.addWidget(self._model_combo)

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

        self.setMaximumWidth(320)
