from __future__ import annotations

from typing import Final

from PySide6 import QtGui
from PySide6 import QtWidgets
from PySide6.QtCore import Qt

from .._utils import ONE_LINE_ICON_TEXT


class ToolBar(QtWidgets.QToolBar):
    def __init__(
        self,
        *,
        title: str,
        name: str | None = None,
        actions: list[QtGui.QAction],
        orientation: Qt.Orientation = Qt.Orientation.Horizontal,
        button_style: Qt.ToolButtonStyle = Qt.ToolButtonStyle.ToolButtonTextUnderIcon,
        font_base: QtGui.QFont | None = None,
        overflow_label: str | None = None,
    ) -> None:
        OBJECT_NAME_SUFFIX: Final = "ToolBar"
        FONT_SCALE_FACTOR: Final = 0.8
        VERTICAL_SEPARATOR_STYLE: Final = (
            "QToolBar::separator { height: 1px; background: palette(mid); "
            "margin: 2px 4px; }"
        )

        super().__init__(title)
        # The object name keys saved window state, so it must not change with
        # the translated title.
        self.setObjectName((name or title) + OBJECT_NAME_SUFFIX)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint)
        self.setMovable(False)
        self.setFloatable(False)
        self.setOrientation(orientation)
        self.setToolButtonStyle(button_style)
        overflow = self.findChild(QtWidgets.QToolButton, "qt_toolbar_ext_button")
        if overflow is not None:
            overflow.setAccessibleName(overflow_label or self.tr("More actions"))

        layout = self.layout()
        if layout is not None:
            layout.setSpacing(0)
            layout.setContentsMargins(0, 0, 0, 0)

        if font_base is not None:
            scaled_font = QtGui.QFont(font_base)
            scaled_font.setPointSizeF(font_base.pointSizeF() * FONT_SCALE_FACTOR)
            self.setFont(scaled_font)

        if orientation == Qt.Orientation.Vertical:
            self.setStyleSheet(VERTICAL_SEPARATOR_STYLE)

        if orientation == Qt.Orientation.Horizontal and any(
            "\n" in action.iconText() for action in actions
        ):
            # Qt centers a button's icon and label as one block, so a one-line
            # label drops its icon below its two-line neighbours'. An empty
            # second line keeps every icon on one row.
            for action in actions:
                if action.iconText() and "\n" not in action.iconText():
                    action.setIconText(action.iconText() + "\n")

        for action in actions:
            self.addAction(action)

        if orientation == Qt.Orientation.Vertical:
            self._equalize_button_widths()

    def _equalize_button_widths(self) -> None:
        buttons = [
            b
            for b in self.findChildren(QtWidgets.QToolButton)
            if b.objectName() != "qt_toolbar_ext_button"
        ]
        if not buttons:
            return
        max_width = max(b.sizeHint().width() for b in buttons)
        # Labels wrap so a row stays one height; down a column, a label that
        # fits the column's width on one line keeps its button one line tall.
        for button in buttons:
            action = button.defaultAction()
            one_line = action.property(ONE_LINE_ICON_TEXT) if action else None
            if not one_line or one_line == action.iconText():
                continue
            wrapped = action.iconText()
            action.setIconText(one_line)
            if button.sizeHint().width() > max_width:
                action.setIconText(wrapped)
        for button in buttons:
            button.setMinimumWidth(max_width)
