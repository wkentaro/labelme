from __future__ import annotations

from collections.abc import Callable

from PySide6 import QtCore
from PySide6 import QtGui
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
    _output_format_button: QtWidgets.QToolButton
    _output_format_actions: dict[_automation.AiOutputFormat, QtGui.QAction]
    _output_format_group: QtGui.QActionGroup
    _polygon_detail_panel: QtWidgets.QWidget

    def __init__(
        self,
        *,
        model_name: str,
        polygon_detail: int,
        on_model_changed: Callable[[str], None],
        on_output_format_changed: Callable[[_automation.AiOutputFormat], None],
        on_polygon_detail_changed: Callable[[int], None],
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self._init_ui(
            model_name=model_name,
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
        return self._output_format_group.checkedAction().data()

    def _init_ui(
        self,
        *,
        model_name: str,
        polygon_detail: int,
        on_model_changed: Callable[[str], None],
        on_output_format_changed: Callable[[_automation.AiOutputFormat], None],
        on_polygon_detail_changed: Callable[[int], None],
    ) -> None:
        # AiToolGroup lays these controls out; this widget owns their state.
        self._polygon_detail_panel = detail_panel = QtWidgets.QWidget(self)
        detail_layout = QtWidgets.QVBoxLayout(detail_panel)
        detail_layout.setContentsMargins(0, 0, 0, 0)
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

        # Icon only when closed, like a design tool's shape picker; the open
        # menu names each shape.
        self._output_format_button = QtWidgets.QToolButton(self)
        self._output_format_button.setAccessibleDescription(
            self.tr("AI-assisted annotation output format")
        )
        self._output_format_button.setIconSize(QtCore.QSize(16, 16))
        self._output_format_button.setPopupMode(
            QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup
        )
        output_menu = QtWidgets.QMenu(self._output_format_button)
        self._output_format_group = QtGui.QActionGroup(output_menu)
        self._output_format_actions = {}
        output_formats: list[tuple[_automation.AiOutputFormat, str, str]] = [
            ("polygon", self.tr("Polygon"), "phosphor/polygon.svg"),
            ("mask", self.tr("Mask"), "mask.svg"),
            ("rectangle", self.tr("Rectangle"), "phosphor/rectangle.svg"),
            (
                "oriented_rectangle",
                self.tr("Oriented Rectangle"),
                "oriented_rectangle.svg",
            ),
            ("circle", self.tr("Circle"), "phosphor/circle.svg"),
        ]
        for output_format, text, icon in output_formats:
            action = output_menu.addAction(new_icon(icon), text)
            action.setCheckable(True)
            action.setData(output_format)
            self._output_format_group.addAction(action)
            self._output_format_actions[output_format] = action
        self._output_format_button.setMenu(output_menu)

        self.set_current_model(model_name=model_name)
        self._model_combo.model_changed.connect(on_model_changed)
        self._model_combo.manage_requested.connect(self.manage_models_requested)
        self._model_combo.download_requested.connect(self.download_requested)

        self._show_output_format("polygon")

        # toggled, unlike triggered, stays quiet when the current shape is
        # picked again.
        def handle_output_format_toggled(checked: bool) -> None:  # noqa: FBT001 -- Qt signal payload is positional
            if not checked:
                return
            output_format = self.output_format
            self._show_output_format(output_format)
            on_output_format_changed(output_format)

        for action in self._output_format_actions.values():
            action.toggled.connect(handle_output_format_toggled)
        self._polygon_detail_slider.value_changed.connect(on_polygon_detail_changed)

    def _show_output_format(self, output_format: _automation.AiOutputFormat, /) -> None:
        action = self._output_format_actions[output_format]
        action.setChecked(True)
        self._output_format_button.setIcon(action.icon())
        self._output_format_button.setToolTip(action.text())
        # A tool button has no value, so its name carries the current shape.
        self._output_format_button.setAccessibleName(
            self.tr("Output format: {format}").format(format=action.text())
        )
        self._polygon_detail_panel.setVisible(output_format == "polygon")

    def set_current_model(self, *, model_name: str) -> None:
        if _ai_models.find_ai_assist_model_option(model_name=model_name) is None:
            model_name = ""
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
