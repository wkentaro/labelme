from __future__ import annotations

from typing import Final

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets


class ToolBar(QtWidgets.QToolBar):
    def __init__(
        self,
        *,
        title: str,
        actions: list[QtGui.QAction],
        orientation: QtCore.Qt.Orientation = QtCore.Qt.Orientation.Horizontal,
        button_style: QtCore.Qt.ToolButtonStyle = (
            QtCore.Qt.ToolButtonStyle.ToolButtonTextUnderIcon
        ),
        font_base: QtGui.QFont | None = None,
    ) -> None:
        super().__init__(title)

        # Tracking only user-action buttons avoids Qt's private overflow control.
        self._buttons: list[QtWidgets.QToolButton] = []

        # Qt persists toolbar placement under this compatibility key.
        self.setObjectName(f"{title}ToolBar")
        self.setMovable(False)
        self.setFloatable(False)
        self.setWindowFlags(
            self.windowFlags() | QtCore.Qt.WindowType.FramelessWindowHint
        )

        layout = self.layout()
        assert layout is not None, "QToolBar always owns a layout"
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        self.setOrientation(orientation)
        self.setToolButtonStyle(button_style)

        if font_base is not None:
            FONT_SIZE_SCALE: Final = 0.9
            font = QtGui.QFont(font_base)
            font.setPointSizeF(font_base.pointSizeF() * FONT_SIZE_SCALE)
            self.setFont(font)

        if orientation == QtCore.Qt.Orientation.Vertical:
            self.setStyleSheet(
                "QToolBar::separator { background: palette(mid); height: 1px; "
                "margin: 2px 4px; }"
            )

        for action in actions:
            self.addAction(action)

        if orientation == QtCore.Qt.Orientation.Vertical:
            self._equalize_button_widths()

    def addAction(self, action: QtGui.QAction, /) -> None:  # ty: ignore[invalid-method-override]
        if action.isSeparator() or isinstance(action, QtWidgets.QWidgetAction):
            super().addAction(action)
            return

        button = QtWidgets.QToolButton(self)
        button.setDefaultAction(action)
        button.setToolButtonStyle(self.toolButtonStyle())
        self.toolButtonStyleChanged.connect(button.setToolButtonStyle)
        self.addWidget(button)
        self._buttons.append(button)
        layout = self.layout()
        assert layout is not None
        layout.setAlignment(button, QtCore.Qt.AlignmentFlag.AlignCenter)

    def _equalize_button_widths(self) -> None:
        if not self._buttons:
            return
        width = max(button.sizeHint().width() for button in self._buttons)
        for button in self._buttons:
            button.setMinimumWidth(width)
