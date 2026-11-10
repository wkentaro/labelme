from __future__ import annotations

from typing import Final
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from .._ai_models import AI_ASSIST_FOLDED_MODELS
from .._ai_models import AI_MODEL_DOWNLOAD_SIZES
from .._ai_models import AI_MODEL_TIERS
from .._ai_models import AI_MODEL_TOOLTIPS
from .._ai_models import AI_TEXT_BOX_ONLY_MODELS
from .._utils import new_icon
from ._ai_assisted_annotation_widget import AiAssistedAnnotationWidget
from ._ai_text_to_annotation_widget import AiTextToAnnotationWidget
from ._model_picker import ModelPicker


class _OptionsButton(QtWidgets.QToolButton):
    """Shows a dot while an AI-Find All threshold is off its default."""

    _changed: bool = False

    def set_changed(self, changed: bool, /) -> None:  # noqa: FBT001 -- state flag
        self._changed = changed
        self.update()

    @override
    def paintEvent(self, arg__1: QtGui.QPaintEvent, /) -> None:
        super().paintEvent(arg__1)
        if not self._changed:
            return
        DOT: Final = 5
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(self.palette().color(QtGui.QPalette.ColorRole.Accent))
        painter.drawEllipse(QtCore.QRectF(self.width() - DOT - 2, 2, DOT, DOT))


class _PanelMenu(QtWidgets.QMenu):
    """A menu that holds a form, where Tab moves between its fields."""

    @override
    def focusNextPrevChild(self, next: bool, /) -> bool:  # noqa: A002 -- Qt override
        # QMenu takes Tab to step through its actions, which strands focus on
        # the menu itself when a widget action holds several fields.
        return QtWidgets.QWidget.focusNextPrevChild(self, next)


class _ModelMenuButton(QtWidgets.QComboBox):
    """One picker for both AI tools' models, in a section per tool.

    The tools' own ModelPickers stay the source of truth, hidden; this combo
    shows their models in one menu and names both in its single item.
    """

    _pickers: tuple[tuple[str, ModelPicker], ...]

    def __init__(self, *, pickers: tuple[tuple[str, ModelPicker], ...]) -> None:
        super().__init__()
        self._pickers = pickers
        self.addItem("")
        self.setSizeAdjustPolicy(
            QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.setMinimumContentsLength(len("SAM 2 Base+"))
        self.setAccessibleName(self.tr("Model"))
        for _, picker in self._pickers:
            picker.display_changed.connect(self._refresh)
            picker.currentIndexChanged.connect(self._refresh)
        self._refresh()

    def _refresh(self) -> None:
        # One name when both tools use the same model.
        labels = dict.fromkeys(picker.label() for _, picker in self._pickers)
        self.setItemText(0, " · ".join(labels))
        self.setToolTip(
            "\n".join(
                self.tr("{tool}: {model}").format(
                    tool=tool, model=picker.toolTip() or picker.label()
                )
                for tool, picker in self._pickers
            )
        )

    @override
    def initStyleOption(self, option: QtWidgets.QStyleOptionComboBox, /) -> None:
        super().initStyleOption(option)
        # Two model names can outgrow the fixed width; end them with "…".
        field = self.style().subControlRect(
            QtWidgets.QStyle.ComplexControl.CC_ComboBox,
            option,
            QtWidgets.QStyle.SubControl.SC_ComboBoxEditField,
            self,
        )
        option.currentText = self.fontMetrics().elidedText(
            option.currentText, QtCore.Qt.TextElideMode.ElideRight, field.width()
        )

    def showPopup(self) -> None:
        menu = self._build_menu()
        menu.aboutToHide.connect(menu.deleteLater)
        menu.popup(self.mapToGlobal(self.rect().bottomLeft()))

    def _build_menu(self) -> QtWidgets.QMenu:
        menu = QtWidgets.QMenu(self)
        menu.setToolTipsVisible(True)
        notes = {name: self.tr(tier) for name, tier in AI_MODEL_TIERS.items()}
        tips = {name: self.tr(tip) for name, tip in AI_MODEL_TOOLTIPS.items()}
        boxes_only = self.tr("Boxes only")
        for name in AI_TEXT_BOX_ONLY_MODELS:
            notes[name] = " · ".join(filter(None, [notes.get(name), boxes_only]))
        for tool, picker in self._pickers:
            if not menu.isEmpty():
                menu.addSeparator()
            menu.addAction(tool).setEnabled(False)
            picker.add_actions(
                menu=menu,
                folded=AI_ASSIST_FOLDED_MODELS,
                notes=notes,
                sizes=AI_MODEL_DOWNLOAD_SIZES,
                tips=tips,
            )
        menu.addSeparator()
        segment = self._pickers[0][1]
        manage = segment.findData("manage")
        menu.addAction(segment.itemText(manage)).triggered.connect(
            lambda: segment.manage_requested.emit()
        )
        return menu


class AiToolGroup(QtWidgets.QWidget):
    """One toolbar group for the AI tools, in two rows.

    The query, its model, the Output and Options work from any tool: running
    switches to AI-Find All. So nothing here is ever disabled, and the group
    keeps one width for every tool.
    """

    _assist: AiAssistedAnnotationWidget
    _detect: AiTextToAnnotationWidget
    _options_button: _OptionsButton
    _model_button: _ModelMenuButton

    def __init__(
        self,
        *,
        assist: AiAssistedAnnotationWidget,
        detect: AiTextToAnnotationWidget,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self._assist = assist
        self._detect = detect

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        # Run sits inside the query field, where its status reads in place.
        text_input = detect._text_input
        text_input.addAction(
            new_icon(name="phosphor/magnifying-glass.svg"),
            QtWidgets.QLineEdit.ActionPosition.LeadingPosition,
        )
        field_layout = QtWidgets.QHBoxLayout(text_input)
        field_layout.setContentsMargins(0, 0, 2, 0)
        field_layout.addStretch(1)
        field_layout.addWidget(detect._run_button)
        # Layouts mirror for right-to-left languages; text margins don't.
        run_width = detect._run_reserved_width
        if text_input.isRightToLeft():
            text_input.setTextMargins(run_width, 0, 0, 0)
        else:
            text_input.setTextMargins(0, 0, run_width, 0)
        layout.addWidget(text_input)

        controls = QtWidgets.QHBoxLayout()
        controls.setSpacing(2)
        self._model_button = _ModelMenuButton(
            pickers=(
                (self.tr("AI-Segment"), assist._model_combo),
                (self.tr("AI-Find All"), detect._model_combo),
            )
        )
        controls.addWidget(self._model_button, 1)
        controls.addWidget(assist._output_format_button)
        self._options_button = self._make_options_button()
        controls.addWidget(self._options_button)
        layout.addLayout(controls)
        # Their controls now live here; the empty widgets must not cover any.
        assist.hide()
        detect.hide()

        # Fixed, so a longer model name or a run's status never resizes the
        # toolbar; never narrower than a language's labels need.
        self.setFixedWidth(self.minimumSizeHint().width())

    def _make_options_button(self) -> _OptionsButton:
        # Settings changed once per project, not per click, so they stay out
        # of the toolbar.
        button = _OptionsButton()
        button.setAutoRaise(True)
        button.setIcon(new_icon(name="phosphor/sliders-horizontal.svg"))
        button.setIconSize(QtCore.QSize(16, 16))
        button.setAccessibleName(self.tr("Options"))
        button.setToolTip(self.tr("Options"))
        button.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = _PanelMenu(button)
        panel = QtWidgets.QWidget()
        panel_layout = QtWidgets.QFormLayout(panel)
        panel_layout.addRow(self.tr("AI-Find All"), self._detect._thresholds)
        panel_layout.addRow(self._assist._polygon_detail_panel)
        action = QtWidgets.QWidgetAction(menu)
        action.setDefaultWidget(panel)
        menu.addAction(action)
        button.setMenu(menu)
        self._detect.thresholds_changed.connect(button.set_changed)
        return button
