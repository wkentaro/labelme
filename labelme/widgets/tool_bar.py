from PyQt5 import QtCore
from PyQt5 import QtWidgets


class ToolBar(QtWidgets.QToolBar):
    def __init__(self, title):
        super(ToolBar, self).__init__(title)
        layout = self.layout()
        m = (0, 0, 0, 0)
        layout.setSpacing(0)  # type: ignore[union-attr]
        layout.setContentsMargins(*m)  # type: ignore[union-attr]
        self.setContentsMargins(*m)
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.FramelessWindowHint)  # type: ignore[attr-defined]

    def addAction(self, action):  # type: ignore[override]
        if isinstance(action, QtWidgets.QWidgetAction):
            return super(ToolBar, self).addAction(action)
        btn = QtWidgets.QToolButton()
        btn.setDefaultAction(action)
        btn.setToolButtonStyle(self.toolButtonStyle())
        self.addWidget(btn)

        # center align
        for i in range(self.layout().count()):  # type: ignore[union-attr]
            if isinstance(self.layout().itemAt(i).widget(), QtWidgets.QToolButton):  # type: ignore[union-attr]
                self.layout().itemAt(i).setAlignment(QtCore.Qt.AlignCenter)  # type: ignore[attr-defined,union-attr]
