from __future__ import annotations

from collections.abc import Callable

from PySide6 import QtCore
from PySide6 import QtWidgets

from .. import _ai_models
from .. import _automation
from .._utils import new_icon
from ._integer_slider import IntegerSlider
from ._model_picker import ModelPicker


class AiAssistedAnnotationWidget(QtWidgets.QWidget):
    manage_models_requested = QtCore.Signal()
    download_requested = QtCore.Signal(str)

    _model_combo: ModelPicker
    _output_format_combo: QtWidgets.QComboBox
    _polygon_detail_button: QtWidgets.QToolButton

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
        # AiToolGroup lays these controls out; this widget owns their state.
        self._polygon_detail_button = QtWidgets.QToolButton(self)
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

        self._model_combo = ModelPicker(
            options=[
                (option.model_name, option.display_name)
                for option in _ai_models.AI_ASSIST_MODEL_OPTIONS
            ]
        )
        self._model_combo.setParent(self)
        # Windows needs an explicit name; Unix exposes the selected option instead.
        self._model_combo.setAccessibleName(self.tr("Model"))
        self._model_combo.setAccessibleDescription(
            self.tr("AI-assisted annotation model")
        )

        self._output_format_combo = QtWidgets.QComboBox(self)
        self._output_format_combo.setAccessibleName(self.tr("Output format"))
        self._output_format_combo.setAccessibleDescription(
            self.tr("AI-assisted annotation output format")
        )
        self._output_format_combo.addItem(self.tr("Polygon"), "polygon")
        self._output_format_combo.addItem(self.tr("Mask"), "mask")
        self._output_format_combo.addItem(self.tr("Rectangle"), "rectangle")
        self._output_format_combo.addItem(
            self.tr("Oriented Rectangle"), "oriented_rectangle"
        )
        self._output_format_combo.addItem(self.tr("Circle"), "circle")

        self.set_current_model(model_display=default_model)
        self._model_combo.model_changed.connect(on_model_changed)
        self._model_combo.manage_requested.connect(self.manage_models_requested)
        self._model_combo.download_requested.connect(self.download_requested)

        self._output_format_combo.setCurrentIndex(0)

        def handle_output_format_changed(index: int) -> None:
            output_format = self._output_format_combo.itemData(index)
            self._polygon_detail_button.setVisible(output_format == "polygon")
            on_output_format_changed(output_format)

        self._output_format_combo.currentIndexChanged.connect(
            handle_output_format_changed
        )
        self._polygon_detail_slider.value_changed.connect(on_polygon_detail_changed)

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

    def set_available_models(
        self, *, available: set[str], downloading: set[str]
    ) -> None:
        self._model_combo.set_available_models(
            available=available, downloading=downloading
        )

    def select_model(self, model_name: str, /) -> None:
        self._model_combo.select_model(model_name)

    def set_polygon_detail(self, detail: int, /) -> None:
        with QtCore.QSignalBlocker(self._polygon_detail_slider):
            self._polygon_detail_slider.set_value(detail)
