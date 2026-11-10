from __future__ import annotations

from collections.abc import Callable
from typing import Final
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from .._ai_models import AI_TEXT_MODEL_OPTIONS
from ._hint_chip import RETURN_GLYPH
from ._model_picker import ModelPicker


def _keycap_outline(*, palette: QtGui.QPalette) -> QtGui.QColor:
    # Mid matches the field's background in dark themes, so mix the outline
    # from the field's own colors: 30% of the way from background to text.
    base = palette.color(QtGui.QPalette.ColorRole.Base)
    text = palette.color(QtGui.QPalette.ColorRole.Text)

    def mix(b: float, t: float) -> float:
        return b + (t - b) * 0.3

    return QtGui.QColor.fromRgbF(
        mix(base.redF(), text.redF()),
        mix(base.greenF(), text.greenF()),
        mix(base.blueF(), text.blueF()),
    )


class _RunButton(QtWidgets.QToolButton):
    """Outlines its label like a keycap.

    Unlike a search field, the query field runs nothing until asked, so Run
    has to read as clickable before the pointer finds it.
    """

    def sizeHint(self) -> QtCore.QSize:
        # Room between the outline and the label.
        return super().sizeHint() + QtCore.QSize(4, 0)

    @override
    def paintEvent(self, arg__1: QtGui.QPaintEvent, /) -> None:
        super().paintEvent(arg__1)
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(_keycap_outline(palette=self.palette()))
        painter.drawRoundedRect(
            QtCore.QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5), 4, 4
        )


class AiTextToAnnotationWidget(QtWidgets.QWidget):
    model_changed = QtCore.Signal(str)
    thresholds_changed = QtCore.Signal(bool)  # True when off their defaults
    manage_models_requested = QtCore.Signal()
    download_requested = QtCore.Signal(str)

    _default_score_threshold: float = 0.1
    _default_iou_threshold: float = 0.5
    # The Return key's symbol says Enter runs the query.
    _RUN_GLYPH: Final = RETURN_GLYPH

    _text_input: QtWidgets.QLineEdit
    _model_combo: ModelPicker
    _score_spinbox: QtWidgets.QDoubleSpinBox
    _iou_spinbox: QtWidgets.QDoubleSpinBox
    _run_button: _RunButton
    _run_reserved_width: int
    _thresholds: QtWidgets.QWidget

    def __init__(
        self,
        *,
        on_submit: Callable[[], None],
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self._init_ui(on_submit=on_submit)

    def _init_ui(self, *, on_submit: Callable[[], None]) -> None:
        # AiToolGroup lays these controls out; this widget owns their state.
        text_input = QtWidgets.QLineEdit(self)
        # The prompt is one concept and becomes the label of what it finds.
        text_input.setPlaceholderText(self.tr("What to find"))
        text_input.setAccessibleName(self.tr("Prompt"))
        text_input.setFixedHeight(24)
        text_input.returnPressed.connect(on_submit)
        self._text_input = text_input

        self._run_button = run_button = _RunButton(self)
        run_button.setAutoRaise(True)
        run_button.setAccessibleName(self.tr("Run"))
        run_button.setToolTip(self.tr("Run"))
        run_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        run_button.clicked.connect(lambda: on_submit())
        # The field reserves room for Run's widest label, so a run doesn't
        # shift the query text; Run itself fits its label, so at rest it hugs
        # the glyph.
        widths = []
        # False last, so Run ends at rest.
        for detecting in (True, False):
            self.set_detecting(detecting=detecting)
            widths.append(run_button.sizeHint().width())
        self._run_reserved_width = max(widths)

        self._model_combo = model_combo = ModelPicker(options=AI_TEXT_MODEL_OPTIONS)
        model_combo.setParent(self)
        # Windows needs an explicit name; Unix exposes the selected option instead.
        model_combo.setAccessibleName(self.tr("Model"))
        model_combo.setAccessibleDescription(self.tr("AI-Find All model"))
        model_combo.model_changed.connect(self.model_changed)
        model_combo.manage_requested.connect(self.manage_models_requested)
        model_combo.download_requested.connect(self.download_requested)

        self._thresholds = thresholds = QtWidgets.QWidget(self)
        thresholds_layout = QtWidgets.QFormLayout(thresholds)
        thresholds_layout.setContentsMargins(0, 0, 0, 0)

        def add_threshold(text: str, value: float) -> QtWidgets.QDoubleSpinBox:
            spinbox = QtWidgets.QDoubleSpinBox()
            spinbox.setRange(0, 1)
            spinbox.setSingleStep(0.05)
            spinbox.setValue(value)
            spinbox.valueChanged.connect(
                lambda: self.thresholds_changed.emit(self._thresholds_off_default())
            )
            # The label is the spinbox's buddy, which names it for screen readers.
            thresholds_layout.addRow(text, spinbox)
            return spinbox

        self._score_spinbox = add_threshold(
            self.tr("Score"), self._default_score_threshold
        )
        self._iou_spinbox = add_threshold(self.tr("IoU"), self._default_iou_threshold)

    def set_detecting(self, *, detecting: bool) -> None:
        # Run stays clickable: running again replaces the pending job.
        self._run_button.setText(self.tr("Finding…") if detecting else self._RUN_GLYPH)

    def get_text_prompt(self) -> str:
        return self._text_input.text().strip()

    def set_label_suggestions(self, *, model: QtCore.QAbstractItemModel) -> None:
        completer = QtWidgets.QCompleter(model, self._text_input)
        completer.setCaseSensitivity(QtCore.Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(QtCore.Qt.MatchFlag.MatchContains)
        self._text_input.setCompleter(completer)

    def focus_text_prompt(self) -> None:
        self._text_input.setFocus()

    def get_model_name(self) -> str:
        return self._model_combo.currentData() or ""

    def set_model_name(self, *, model_name: str) -> None:
        self._model_combo.set_model_name(model_name=model_name)

    def set_available_models(
        self, *, available: set[str], downloading: set[str]
    ) -> None:
        self._model_combo.set_available_models(
            available=available, downloading=downloading
        )

    def select_model(self, model_name: str, /) -> None:  # noqa: GR013 -- _download_and_select calls it as Callable[[str], None]
        self._model_combo.select_model(model_name=model_name)

    def set_unavailable_models(self, *, unavailable: dict[str, str]) -> None:
        self._model_combo.set_unavailable_models(unavailable=unavailable)

    def get_score_threshold(self) -> float:
        return self._score_spinbox.value()

    def get_iou_threshold(self) -> float:
        return self._iou_spinbox.value()

    def _thresholds_off_default(self) -> bool:
        return (
            self._score_spinbox.value() != self._default_score_threshold
            or self._iou_spinbox.value() != self._default_iou_threshold
        )
