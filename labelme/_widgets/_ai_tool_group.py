from __future__ import annotations

from typing import Final

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from ._ai_assisted_annotation_widget import AiAssistedAnnotationWidget
from ._ai_text_to_annotation_widget import AiTextToAnnotationWidget
from ._info_button import InfoButton


class AiToolGroup(QtWidgets.QWidget):
    """One toolbar group for the AI tools that follows the active tool.

    Every control keeps its slot for every tool, so switching tools never
    moves the Model or Output; controls the tool can't use are disabled.
    """

    hover_highlight_requested = QtCore.Signal(bool)

    _assist: AiAssistedAnnotationWidget
    _detect: AiTextToAnnotationWidget
    _title: QtWidgets.QLabel
    _info_button: InfoButton
    _model_stack: QtWidgets.QStackedWidget
    _ai_tool_active: bool
    _hinted: tuple[QtWidgets.QWidget, ...]

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

        header = QtWidgets.QHBoxLayout()
        header.addStretch()
        self._title = QtWidgets.QLabel()
        header.addWidget(self._title)
        self._info_button = InfoButton(tooltip="")
        header.addWidget(self._info_button)
        header.addWidget(assist._polygon_detail_button)
        header.addStretch()
        layout.addLayout(header)

        body = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(body)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(2)
        grid.addWidget(detect._text_input, 0, 0, 1, 2)
        grid.addWidget(detect._run_button, 0, 2)
        self._model_stack = QtWidgets.QStackedWidget()
        self._model_stack.addWidget(assist._model_combo)
        self._model_stack.addWidget(detect._model_combo)
        grid.addWidget(self._model_stack, 1, 0)
        grid.addWidget(assist._output_format_button, 1, 1)
        grid.addWidget(detect._thresholds, 1, 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        layout.addWidget(body)
        # The hint covers what needs an AI tool, not the query and Run.
        self._hinted = (self._model_stack, assist._output_format_button)
        for widget in self._hinted:
            widget.installEventFilter(self)
        # Their controls now live here; the empty widgets must not cover any.
        assist.hide()
        detect.hide()

        self.set_tool(None)
        # Fixed, so switching tools never resizes the toolbar; never narrower
        # than a language's labels need.
        COMPACT_WIDTH: Final[int] = 320
        self.setFixedWidth(max(COMPACT_WIDTH, self.minimumSizeHint().width()))

    def set_tool(self, create_mode: str | None, /) -> None:
        detect = create_mode == "ai_find_all"
        titles = {
            "ai_segment": self.tr("AI-Segment"),
            "ai_find_all": self.tr("AI-Find All"),
        }
        self._title.setText(titles.get(create_mode or "", self.tr("AI Assist")))
        self._info_button.setToolTip(
            self.tr("Find every object that matches the text prompt or an example box")
            if detect
            else self.tr("Segment one object from points and a box")
        )
        self._info_button.setAccessibleName(self._info_button.toolTip())
        self._model_stack.setCurrentWidget(
            self._detect._model_combo if detect else self._assist._model_combo
        )
        self._ai_tool_active = create_mode in titles
        # The query and Run work from any tool: running switches to AI-Find All.
        for control in (
            self._model_stack,
            self._assist._output_format_button,
            self._assist._polygon_detail_button,
        ):
            control.setEnabled(self._ai_tool_active)
        self._detect._thresholds.setEnabled(detect)
        self.hover_highlight_requested.emit(False)  # noqa: FBT003 -- Qt signal payload is positional

    def eventFilter(self, a0: QtCore.QObject, a1: QtCore.QEvent, /) -> bool:
        if a0 in self._hinted and not self._ai_tool_active:
            if a1.type() == QtCore.QEvent.Type.Enter:
                QtWidgets.QToolTip.showText(
                    QtGui.QCursor.pos(),
                    self.tr("Select 'AI-Segment' or 'AI-Find All' to enable AI Assist"),
                    self,
                )
                self.hover_highlight_requested.emit(True)  # noqa: FBT003 -- Qt signal payload is positional
            elif a1.type() == QtCore.QEvent.Type.Leave:
                self.hover_highlight_requested.emit(False)  # noqa: FBT003 -- Qt signal payload is positional
        return super().eventFilter(a0, a1)
