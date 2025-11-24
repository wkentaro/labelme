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

        layout = self.layout()
        m = (0, 0, 0, 0)
        layout.setSpacing(0)
        layout.setContentsMargins(*m)
        self.setContentsMargins(*m)
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.FramelessWindowHint)
        self.setMovable(False)
        self.setFloatable(False)

        self.setObjectName(f"{title}ToolBar")
        self.setOrientation(orientation)
        self.setToolButtonStyle(button_style)
        utils.addActions(widget=self, actions=actions)

    def addAction(self, action):  # type: ignore[override]
        if isinstance(action, QtWidgets.QWidgetAction):
            return super().addAction(action)
        btn = QtWidgets.QToolButton()
        btn.setDefaultAction(action)
        btn.setToolButtonStyle(self.toolButtonStyle())
        self.addWidget(btn)

        # center align
        for i in range(self.layout().count()):
            if isinstance(self.layout().itemAt(i).widget(), QtWidgets.QToolButton):
                self.layout().itemAt(i).setAlignment(QtCore.Qt.AlignCenter)
