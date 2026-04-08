from __future__ import annotations

import typing
from collections.abc import Callable
from typing import Literal

from loguru import logger
from PyQt5 import QtCore
from PyQt5 import QtGui
from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt

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
        ("sam3:latest", "Sam3"),
    ]

    _model_combo: QtWidgets.QComboBox
    _output_format_combo: QtWidgets.QComboBox
    _body: QtWidgets.QWidget

    def __init__(
        self,
        default_model: str,
        on_model_changed: Callable[[str], None],
        on_output_format_changed: Callable[[Literal["polygon", "mask"]], None],
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self._init_ui(
            default_model=default_model,
            on_model_changed=on_model_changed,
            on_output_format_changed=on_output_format_changed,
        )

    @property
    def output_format(self) -> Literal["polygon", "mask"]:
        return self._output_format_combo.currentData()

    def _init_ui(
        self,
        default_model: str,
        on_model_changed: Callable[[str], None],
        on_output_format_changed: Callable[[Literal["polygon", "mask"]], None],
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
            tooltip=self.tr("AI suggests annotation in 'AI-Points' and 'AI-Box' modes")
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

        self._output_format_combo = QtWidgets.QComboBox()
        self._output_format_combo.addItem("Polygon", "polygon")
        self._output_format_combo.addItem("Mask", "mask")
        body_layout.addWidget(self._output_format_combo)

        layout.addWidget(body)

        model_ui_names = [model_display for _, model_display in self._available_models]
        if default_model in model_ui_names:
            model_index = model_ui_names.index(default_model)
        else:
            logger.warning("Default AI model is not found: {!r}", default_model)
            model_index = 0

        self._model_combo.currentIndexChanged.connect(
            lambda index: on_model_changed(self._model_combo.itemData(index))
        )
        self._model_combo.setCurrentIndex(model_index)

        self._output_format_combo.currentIndexChanged.connect(
            lambda index: on_output_format_changed(
                self._output_format_combo.itemData(index)
            )
        )
        self._output_format_combo.setCurrentIndex(0)

        self.setMaximumWidth(200)

    def set_disabled_models(self, disabled_models: tuple[str, ...]) -> None:
        model = typing.cast(QtGui.QStandardItemModel, self._model_combo.model())
        for i in range(self._model_combo.count()):
            model_id = self._model_combo.itemData(i)
            item = model.item(i)
            assert item is not None
            if model_id in disabled_models:
                item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
            else:
                item.setFlags(item.flags() | Qt.ItemIsEnabled)

    def setEnabled(self, a0: bool) -> None:
        self._body.setEnabled(a0)

    def eventFilter(self, a0: QtCore.QObject, a1: QtCore.QEvent) -> bool:
        if a0 == self._body and not self._body.isEnabled():
            if a1.type() == QtCore.QEvent.Enter:
                QtWidgets.QToolTip.showText(
                    QtGui.QCursor.pos(),
                    self.tr(
                        "Select 'AI-Points' or 'AI-Box' mode "
                        "to enable AI-Assisted Annotation"
                    ),
                    self._body,
                )
        return super().eventFilter(a0, a1)
