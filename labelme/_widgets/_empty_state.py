from __future__ import annotations

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from .._utils import new_icon


class EmptyStateWidget(QtWidgets.QWidget):
    def __init__(
        self,
        *,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self._icon = new_icon("phosphor/image-square.svg")
        self._icon_label = QtWidgets.QLabel()
        self.setObjectName("emptyState")
        self.setAutoFillBackground(True)
        self.setBackgroundRole(QtGui.QPalette.ColorRole.Base)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.addStretch()

        content = QtWidgets.QWidget()
        content.setMaximumWidth(520)
        content_layout = QtWidgets.QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        icon = self._icon_label
        icon.setObjectName("emptyStateIcon")
        icon.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._refresh_icon()
        content_layout.addWidget(icon)

        heading = QtWidgets.QLabel(self.tr("Start annotating"))
        heading.setObjectName("emptyStateHeading")
        heading.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        heading_font = heading.font()
        heading_font.setPointSizeF(max(heading_font.pointSizeF() * 1.5, 18))
        heading_font.setWeight(QtGui.QFont.Weight.DemiBold)
        heading.setFont(heading_font)
        self.setAccessibleName(heading.text())
        content_layout.addWidget(heading)

        explanation = QtWidgets.QLabel(
            self.tr("Open an image or a folder of images to begin.")
        )
        explanation.setObjectName("emptyStateExplanation")
        explanation.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        explanation.setWordWrap(True)
        content_layout.addWidget(explanation)

        buttons = QtWidgets.QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addStretch()

        # The buttons take their text and icon from the File menu actions in
        # bind_open_actions, so the two entry points cannot drift apart.
        self._open_file = QtWidgets.QPushButton()
        self._open_file.setObjectName("emptyStateOpenFile")
        buttons.addWidget(self._open_file)

        self._open_folder = QtWidgets.QPushButton()
        self._open_folder.setObjectName("emptyStateOpenFolder")
        buttons.addWidget(self._open_folder)
        buttons.addStretch()
        content_layout.addLayout(buttons)

        drop_hint = QtWidgets.QLabel(self.tr("Or drag and drop image files here"))
        drop_hint.setObjectName("emptyStateDropHint")
        drop_hint.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        content_layout.addWidget(drop_hint)
        self.setAccessibleDescription(f"{explanation.text()} {drop_hint.text()}.")

        layout.addWidget(content, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()

    def bind_open_actions(
        self, *, open_file: QtGui.QAction, open_folder: QtGui.QAction
    ) -> None:
        for button, action in (
            (self._open_file, open_file),
            (self._open_folder, open_folder),
        ):
            button.setText(action.text())
            button.setIcon(action.icon())
            button.clicked.connect(action.trigger)

    def _refresh_icon(self) -> None:
        self._icon_label.setPixmap(self._icon.pixmap(56, 56))

    def changeEvent(self, event: QtCore.QEvent, /) -> None:
        super().changeEvent(event)
        if event.type() in (
            QtCore.QEvent.Type.ApplicationPaletteChange,
            QtCore.QEvent.Type.PaletteChange,
        ):
            self._refresh_icon()
