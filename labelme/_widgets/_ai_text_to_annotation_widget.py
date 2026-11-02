from __future__ import annotations

from collections.abc import Callable

from PySide6 import QtCore
from PySide6 import QtWidgets

from .._ai_models import AI_TEXT_MODEL_OPTIONS
from ._model_picker import ModelPicker


class AiTextToAnnotationWidget(QtWidgets.QWidget):
    model_changed = QtCore.Signal(str)
    thresholds_changed = QtCore.Signal(bool)  # True when off their defaults
    manage_models_requested = QtCore.Signal()
    download_requested = QtCore.Signal(str)

    _default_score_threshold: float = 0.1
    _default_iou_threshold: float = 0.5

    _text_input: QtWidgets.QLineEdit
    _model_combo: ModelPicker
    _score_spinbox: QtWidgets.QDoubleSpinBox
    _iou_spinbox: QtWidgets.QDoubleSpinBox
    _run_button: QtWidgets.QToolButton
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

        self._run_button = run_button = QtWidgets.QToolButton(self)
        run_button.setText(self.tr("Run"))
        run_button.setFixedHeight(24)
        run_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        run_button.clicked.connect(lambda: on_submit())
        # Fits "Finding…" too, so a run doesn't shift the row.
        run_button.setMinimumWidth(
            max(
                run_button.fontMetrics().horizontalAdvance(text)
                for text in (self.tr("Run"), self.tr("Finding…"))
            )
            + 16
        )

        self._model_combo = model_combo = ModelPicker(options=AI_TEXT_MODEL_OPTIONS)
        model_combo.setParent(self)
        # Windows needs an explicit name; Unix exposes the selected option instead.
        model_combo.setAccessibleName(self.tr("Model"))
        model_combo.setAccessibleDescription(self.tr("AI-Find All model"))
        model_combo.model_changed.connect(self.model_changed)
        model_combo.manage_requested.connect(self.manage_models_requested)
        model_combo.download_requested.connect(self.download_requested)
        # Room for the longest model name, which shows even before its download.
        model_combo.ensurePolished()
        metrics = model_combo.fontMetrics()
        longest = max(
            metrics.horizontalAdvance(display) for _, display in AI_TEXT_MODEL_OPTIONS
        )
        option = QtWidgets.QStyleOptionComboBox()
        model_combo.initStyleOption(option)
        model_combo.setMinimumWidth(
            model_combo.style()
            .sizeFromContents(
                QtWidgets.QStyle.ContentsType.CT_ComboBox,
                option,
                QtCore.QSize(longest, metrics.height()),
                model_combo,
            )
            .width()
        )

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

    def set_detecting(self, detecting: bool, /) -> None:  # noqa: FBT001 -- state flag
        # Run stays clickable: running again replaces the pending job.
        self._run_button.setText(self.tr("Finding…") if detecting else self.tr("Run"))

    def get_text_prompt(self) -> str:
        return self._text_input.text().strip()

    def set_label_suggestions(self, model: QtCore.QAbstractItemModel, /) -> None:
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

    def select_model(self, model_name: str, /) -> None:
        self._model_combo.select_model(model_name)

    def set_unavailable_models(self, unavailable: dict[str, str], /) -> None:
        self._model_combo.set_unavailable_models(unavailable)

    def get_score_threshold(self) -> float:
        return self._score_spinbox.value()

    def get_iou_threshold(self) -> float:
        return self._iou_spinbox.value()

    def _thresholds_off_default(self) -> bool:
        return (
            self._score_spinbox.value() != self._default_score_threshold
            or self._iou_spinbox.value() != self._default_iou_threshold
        )
