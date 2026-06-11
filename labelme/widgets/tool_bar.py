from __future__ import annotations

from PySide6 import QtGui
from PySide6 import QtWidgets
from PySide6.QtCore import Qt

from .. import utils


class ToolBar(QtWidgets.QToolBar):
    def __init__(
        self,
        title: str,
        actions: list[QtGui.QAction | None],
        orientation: Qt.Orientation = Qt.Horizontal,
        button_style: Qt.ToolButtonStyle = Qt.ToolButtonTextUnderIcon,
        font_base: QtGui.QFont | None = None,
    ) -> None:
        super().__init__(title)

        if font_base is not None:
            font = QtGui.QFont(font_base)
            font.setPointSizeF(font_base.pointSizeF() * 0.875)
            self.setFont(font)

        layout = self.layout()
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)
        self.setMovable(False)
        self.setFloatable(False)

        self.setObjectName(f"{title}ToolBar")
        self.setOrientation(orientation)
        self.setToolButtonStyle(button_style)
        if orientation == Qt.Vertical:
            self.setStyleSheet(
                "QToolBar::separator { height: 1px; margin: 4px 2px;"
                " background: palette(mid); }"
            )
        utils.add_actions(widget=self, actions=actions)
        if orientation == Qt.Vertical:
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
        self.layout().setAlignment(button, Qt.AlignCenter)

    def _equalize_button_widths(self) -> None:
        layout = self.layout()
        buttons: list[QtWidgets.QToolButton] = []
        for i in range(layout.count()):
            widget = layout.itemAt(i).widget()
            if isinstance(widget, QtWidgets.QToolButton):
                buttons.append(widget)
        if not buttons:
            return
        max_width = 0
        for btn in buttons:
            btn.ensurePolished()
            max_width = max(max_width, btn.sizeHint().width())
        for btn in buttons:
            btn.setMinimumWidth(max_width)
