from __future__ import annotations

from typing import Final

from PySide6 import QtGui
from PySide6 import QtWidgets
from PySide6.QtCore import Qt


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
        self._button_style = button_style
        self._labeled_width = 0
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

        for action in actions:
            self.addAction(action)

        if orientation == Qt.Orientation.Vertical:
            self._equalize_button_widths()

    def resizeEvent(self, event: QtGui.QResizeEvent, /) -> None:
        super().resizeEvent(event)
        if (
            self.orientation() != Qt.Orientation.Horizontal
            or self._button_style == Qt.ToolButtonStyle.ToolButtonIconOnly
        ):
            return
        # Long translations can push the trailing widgets into the overflow
        # menu, so the buttons drop their text when the labeled bar won't fit.
        # ponytail: the labeled width is measured only while labeled, so a
        # widget that grows while icon-only shows up on the next labeled pass.
        if self.toolButtonStyle() == self._button_style:
            self._labeled_width = self.sizeHint().width()
        self.setToolButtonStyle(
            self._button_style
            if self.width() >= self._labeled_width
            else Qt.ToolButtonStyle.ToolButtonIconOnly
        )

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
