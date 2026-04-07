from __future__ import annotations

from PyQt5 import QtCore
from PyQt5 import QtGui
from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt

from .. import utils


class ToolBar(QtWidgets.QToolBar):
    def __init__(
        self,
        title: str,
        actions: list[QtWidgets.QAction | None],
        orientation: Qt.Orientation = Qt.Horizontal,
        button_style: Qt.ToolButtonStyle = Qt.ToolButtonTextUnderIcon,
        font_base: QtGui.QFont | None = None,
    ) -> None:
        super().__init__(title)

        if font_base:
            font = QtGui.QFont(font_base)
            font.setPointSizeF(font_base.pointSizeF() * 0.875)
            self.setFont(font)

        toolbar_layout = self.layout()
        zero_margins = (0, 0, 0, 0)
        toolbar_layout.setSpacing(0)
        toolbar_layout.setContentsMargins(*zero_margins)
        self.setContentsMargins(*zero_margins)
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.FramelessWindowHint)
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
        utils.addActions(widget=self, actions=actions)

    def addAction(self, action: QtWidgets.QAction) -> None:  # type: ignore[override]
        if isinstance(action, QtWidgets.QWidgetAction):
            return super().addAction(action)
        tool_btn = QtWidgets.QToolButton()
        tool_btn.setDefaultAction(action)
        tool_btn.setToolButtonStyle(self.toolButtonStyle())
        self.addWidget(tool_btn)

        # center-align all tool buttons
        toolbar_layout = self.layout()
        for idx in range(toolbar_layout.count()):
            widget = toolbar_layout.itemAt(idx).widget()
            if isinstance(widget, QtWidgets.QToolButton):
                toolbar_layout.itemAt(idx).setAlignment(QtCore.Qt.AlignCenter)
