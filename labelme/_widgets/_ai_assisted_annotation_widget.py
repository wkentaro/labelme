from __future__ import annotations

from collections.abc import Callable
from typing import cast

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from .. import _ai_models
from .. import _automation
from .._utils._qt import new_icon
from ._info_button import InfoButton
from ._integer_slider import IntegerSlider
from ._model_picker import ModelPicker


class AiAssistedAnnotationWidget(QtWidgets.QWidget):
    hover_highlight_requested = QtCore.Signal(bool)
    manage_models_requested = QtCore.Signal()

    _model_combo: ModelPicker
    _output_format_combo: QtWidgets.QComboBox
    _body: QtWidgets.QWidget

    def __init__(
        self,
        *,
        default_model: str,
        polygon_detail: int,
        on_model_changed: Callable[[str], None],
        on_output_format_changed: Callable[[_automation.AiOutputFormat], None],
        on_polygon_detail_changed: Callable[[int], None],
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self._is_point_prompt_mode = False
        self._init_ui(
            default_model=default_model,
            polygon_detail=polygon_detail,
            on_model_changed=on_model_changed,
            on_output_format_changed=on_output_format_changed,
            on_polygon_detail_changed=on_polygon_detail_changed,
        )

    @property
    def current_model_id(self) -> str:
        return self._model_combo.currentData() or ""

    @property
    def is_point_prompt_mode(self) -> bool:
        return self._is_point_prompt_mode

    @property
    def output_format(self) -> _automation.AiOutputFormat:
        return self._output_format_combo.currentData()

    def _init_ui(
        self,
        *,
        default_model: str,
        polygon_detail: int,
        on_model_changed: Callable[[str], None],
        on_output_format_changed: Callable[[_automation.AiOutputFormat], None],
        on_polygon_detail_changed: Callable[[int], None],
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
        self._polygon_detail_button = QtWidgets.QToolButton()
        self._polygon_detail_button.setAutoRaise(True)
        self._polygon_detail_button.setIcon(new_icon("phosphor/sliders-horizontal.svg"))
        self._polygon_detail_button.setIconSize(QtCore.QSize(16, 16))
        self._polygon_detail_button.setAccessibleName(self.tr("Polygon detail"))
        self._polygon_detail_button.setToolTip(self.tr("Adjust polygon detail"))
        self._polygon_detail_button.setPopupMode(
            QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup
        )
        detail_menu = QtWidgets.QMenu(self._polygon_detail_button)
        detail_panel = QtWidgets.QWidget()
        detail_layout = QtWidgets.QVBoxLayout(detail_panel)
        detail_layout.addWidget(QtWidgets.QLabel(self.tr("Polygon detail")))
        self._polygon_detail_slider = IntegerSlider(
            minimum=0,
            maximum=100,
            value=polygon_detail,
        )
        self._polygon_detail_slider.setAccessibleName(self.tr("Polygon detail"))
        self._polygon_detail_slider.setMinimumWidth(200)
        detail_layout.addWidget(self._polygon_detail_slider)
        endpoints = QtWidgets.QHBoxLayout()
        endpoints.addWidget(QtWidgets.QLabel(self.tr("Smoother")))
        endpoints.addStretch(1)
        endpoints.addWidget(QtWidgets.QLabel(self.tr("More detail")))
        detail_layout.addLayout(endpoints)
        detail_action = QtWidgets.QWidgetAction(detail_menu)
        detail_action.setDefaultWidget(detail_panel)
        detail_menu.addAction(detail_action)
        self._polygon_detail_button.setMenu(detail_menu)
        header_layout.addWidget(self._polygon_detail_button)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        self._body = body = QtWidgets.QWidget()
        self.installEventFilter(self)
        body.installEventFilter(self)
        body_layout = QtWidgets.QVBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        body.setLayout(body_layout)

        self._model_combo = ModelPicker(
            options=[
                (option.model_name, option.display_name)
                for option in _ai_models.AI_ASSIST_MODEL_OPTIONS
            ]
        )
        # Windows needs an explicit name; Unix exposes the selected option instead.
        self._model_combo.setAccessibleName(self.tr("Model"))
        self._model_combo.setAccessibleDescription(
            self.tr("AI-assisted annotation model")
        )
        body_layout.addWidget(self._model_combo)

        self._output_format_combo = QtWidgets.QComboBox()
        self._output_format_combo.setAccessibleName(self.tr("Output format"))
        self._output_format_combo.setAccessibleDescription(
            self.tr("AI-assisted annotation output format")
        )
        self._output_format_combo.addItem("Polygon", "polygon")
        self._output_format_combo.addItem("Mask", "mask")
        self._output_format_combo.addItem("Rectangle", "rectangle")
        self._output_format_combo.addItem("Oriented Rectangle", "oriented_rectangle")
        self._output_format_combo.addItem("Circle", "circle")
        body_layout.addWidget(self._output_format_combo)

        layout.addWidget(body)

        self.set_current_model(model_display=default_model)
        self._model_combo.model_changed.connect(on_model_changed)
        self._model_combo.manage_requested.connect(self.manage_models_requested)

        self._output_format_combo.setCurrentIndex(0)

        def handle_output_format_changed(index: int) -> None:
            output_format = self._output_format_combo.itemData(index)
            self._polygon_detail_button.setVisible(output_format == "polygon")
            on_output_format_changed(output_format)

        self._output_format_combo.currentIndexChanged.connect(
            handle_output_format_changed
        )
        self._polygon_detail_slider.value_changed.connect(on_polygon_detail_changed)

        self.setMaximumWidth(200)

    def set_current_model(self, *, model_display: str) -> None:
        model_name = next(
            (
                option.model_name
                for option in _ai_models.AI_ASSIST_MODEL_OPTIONS
                if option.display_name == model_display
            ),
            "",
        )
        self._model_combo.set_model_name(model_name=model_name)

    def set_available_models(self, *, available: set[str]) -> None:
        self._model_combo.set_available_models(available=available)

    def set_polygon_detail(self, detail: int, /) -> None:
        with QtCore.QSignalBlocker(self._polygon_detail_slider):
            self._polygon_detail_slider.set_value(detail)

    def set_point_prompt_mode(self, *, enabled: bool) -> None:
        self._is_point_prompt_mode = enabled
        model = cast(QtGui.QStandardItemModel, self._model_combo.model())
        for index in range(self._model_combo.count()):
            option = _ai_models.find_ai_assist_model_option(
                model_name=self._model_combo.itemData(index)
            )
            item = model.item(index)
            assert item is not None
            item.setEnabled(
                option is None or not enabled or option.supports_point_prompts
            )

    def setEnabled(self, a0: bool, /) -> None:  # noqa: FBT001 -- QWidget.setEnabled override
        self._body.setEnabled(a0)
        self._polygon_detail_button.setEnabled(a0)
        self.hover_highlight_requested.emit(False)  # noqa: FBT003 -- Qt signal payload is positional

    def eventFilter(self, a0: QtCore.QObject, a1: QtCore.QEvent, /) -> bool:
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
                self.hover_highlight_requested.emit(True)  # noqa: FBT003 -- Qt signal payload is positional
            elif a1.type() == QtCore.QEvent.Type.Leave:
                self.hover_highlight_requested.emit(False)  # noqa: FBT003 -- Qt signal payload is positional
        return super().eventFilter(a0, a1)
