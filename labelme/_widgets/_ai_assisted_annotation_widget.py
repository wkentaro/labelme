from __future__ import annotations

from collections.abc import Callable
from typing import cast

from loguru import logger
from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from .. import _ai_models
from .. import _automation
from ._info_button import InfoButton


class AiAssistedAnnotationWidget(QtWidgets.QWidget):
    hover_highlight_requested = QtCore.Signal(bool)

    _model_combo: QtWidgets.QComboBox
    _output_format_combo: QtWidgets.QComboBox
    _body: QtWidgets.QWidget

    def __init__(
        self,
        default_model: str,
        on_model_changed: Callable[[str], None],
        on_output_format_changed: Callable[[_automation.AiOutputFormat], None],
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self._is_point_prompt_mode = False
        self._init_ui(
            default_model=default_model,
            on_model_changed=on_model_changed,
            on_output_format_changed=on_output_format_changed,
        )

    @property
    def current_model_id(self) -> str:
        return self._model_combo.currentData()

    @property
    def is_point_prompt_mode(self) -> bool:
        return self._is_point_prompt_mode

    @property
    def output_format(self) -> _automation.AiOutputFormat:
        return self._output_format_combo.currentData()

    def _init_ui(
        self,
        default_model: str,
        on_model_changed: Callable[[str], None],
        on_output_format_changed: Callable[[_automation.AiOutputFormat], None],
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
        self.installEventFilter(self)
        body.installEventFilter(self)
        body_layout = QtWidgets.QVBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        body.setLayout(body_layout)

        self._model_combo = QtWidgets.QComboBox()
        for option in _ai_models.AI_ASSIST_MODEL_OPTIONS:
            self._model_combo.addItem(option.display_name, option.model_name)
        body_layout.addWidget(self._model_combo)

        self._output_format_combo = QtWidgets.QComboBox()
        self._output_format_combo.addItem("Polygon", "polygon")
        self._output_format_combo.addItem("Mask", "mask")
        self._output_format_combo.addItem("Rectangle", "rectangle")
        self._output_format_combo.addItem("Oriented Rectangle", "oriented_rectangle")
        self._output_format_combo.addItem("Circle", "circle")
        body_layout.addWidget(self._output_format_combo)

        layout.addWidget(body)

        model_ui_names = [
            option.display_name for option in _ai_models.AI_ASSIST_MODEL_OPTIONS
        ]
        if default_model in model_ui_names:
            model_index = model_ui_names.index(default_model)
        else:
            logger.warning("Default AI model is not found: {!r}", default_model)
            model_index = 0

        self._model_combo.setCurrentIndex(model_index)
        self._model_combo.currentIndexChanged.connect(
            lambda index: on_model_changed(self._model_combo.itemData(index))
        )

        self._output_format_combo.currentIndexChanged.connect(
            lambda index: on_output_format_changed(
                self._output_format_combo.itemData(index)
            )
        )
        self._output_format_combo.setCurrentIndex(0)

        self.setMaximumWidth(200)

    def set_current_model(self, model_display: str) -> None:
        index = self._model_combo.findText(model_display)
        if index < 0 or self._model_combo.currentIndex() == index:
            return
        self._model_combo.setCurrentIndex(index)

    def set_point_prompt_mode(self, enabled: bool) -> None:
        self._is_point_prompt_mode = enabled
        model = cast(QtGui.QStandardItemModel, self._model_combo.model())
        for index, option in enumerate(_ai_models.AI_ASSIST_MODEL_OPTIONS):
            item = model.item(index)
            assert item is not None
            item.setEnabled(not enabled or option.supports_point_prompts)

    def setEnabled(self, a0: bool) -> None:
        self._body.setEnabled(a0)
        self.hover_highlight_requested.emit(False)

    def eventFilter(self, a0: QtCore.QObject, a1: QtCore.QEvent) -> bool:
        if a0 in (self, self._body) and not self._body.isEnabled():
            if a1.type() == QtCore.QEvent.Type.Enter:
                QtWidgets.QToolTip.showText(
                    QtGui.QCursor.pos(),
                    self.tr(
                        "Select 'AI-Points' or 'AI-Box' mode "
                        "to enable AI-Assisted Annotation"
                    ),
                    self,
                )
                self.hover_highlight_requested.emit(True)
            elif a1.type() == QtCore.QEvent.Type.Leave:
                self.hover_highlight_requested.emit(False)
        return super().eventFilter(a0, a1)
