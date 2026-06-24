from __future__ import annotations

from typing import Final

from PySide6 import QtGui
from PySide6 import QtWidgets
from PySide6.QtCore import Qt

_OBJECT_NAME_SUFFIX: Final = "ToolBar"
_FONT_SCALE_FACTOR: Final = 0.8
_VERTICAL_SEPARATOR_STYLE: Final = (
    "QToolBar::separator { height: 1px; background: palette(mid); margin: 2px 4px; }"
)


class ToolBar(QtWidgets.QToolBar):
    def __init__(
        self,
        title: str,
        actions: list[QtGui.QAction | None],
        orientation: Qt.Orientation = Qt.Orientation.Horizontal,
        button_style: Qt.ToolButtonStyle = Qt.ToolButtonStyle.ToolButtonTextUnderIcon,
        font_base: QtGui.QFont | None = None,
    ) -> None:
        super().__init__(title)
        self.setObjectName(title + _OBJECT_NAME_SUFFIX)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint)
        self.setMovable(False)
        self.setFloatable(False)
        self.setOrientation(orientation)
        self.setToolButtonStyle(button_style)

        layout = self.layout()
        if layout is not None:
            layout.setSpacing(0)
            layout.setContentsMargins(0, 0, 0, 0)

        if font_base is not None:
            scaled_font = QtGui.QFont(font_base)
            scaled_font.setPointSizeF(font_base.pointSizeF() * _FONT_SCALE_FACTOR)
            self.setFont(scaled_font)

        if orientation == Qt.Orientation.Vertical:
            self.setStyleSheet(_VERTICAL_SEPARATOR_STYLE)

        for action in actions:
            if action is None:
                self.addSeparator()
            else:
                self.addAction(action)

        if orientation == Qt.Orientation.Vertical:
            self._equalize_button_widths()

    def addAction(self, action: QtGui.QAction) -> None:  # ty: ignore[invalid-method-override]
        if isinstance(action, QtWidgets.QWidgetAction):
            super().addAction(action)
            return

        button = QtWidgets.QToolButton(self)
        button.setDefaultAction(action)
        button.setToolButtonStyle(self.toolButtonStyle())
        self.toolButtonStyleChanged.connect(button.setToolButtonStyle)
        self.addWidget(button)
        layout = self.layout()
        if layout is not None:
            layout.setAlignment(button, Qt.AlignmentFlag.AlignCenter)

    def _equalize_button_widths(self) -> None:
        buttons = [
            b
            for b in self.findChildren(QtWidgets.QToolButton)
            if b.objectName() != "qt_toolbar_ext_button"
        ]
        if not buttons:
            return
        max_width = max(b.sizeHint().width() for b in buttons)
        for button in buttons:
            button.setMinimumWidth(max_width)
