from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from .._utils._qt import new_icon


class _ElidedLabel(QtWidgets.QLabel):
    def paintEvent(self, event: QtGui.QPaintEvent, /) -> None:  # noqa: ARG002 -- fixed by the base class
        rect = self.contentsRect()
        text = self.fontMetrics().elidedText(
            self.text(), QtCore.Qt.TextElideMode.ElideRight, rect.width()
        )
        self.style().drawItemText(
            QtGui.QPainter(self),
            rect,
            int(self.alignment()),
            self.palette(),
            self.isEnabled(),
            text,
            self.foregroundRole(),
        )


class AnnotationFolderFooter(QtWidgets.QWidget):
    # Colors come from palette roles, never a stylesheet, so the row follows a
    # live color-scheme change (see AiTextToAnnotationWidget).
    def __init__(
        self,
        *,
        on_choose: Callable[[], None],
        on_next_to_images: Callable[[], None],
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self.setAccessibleName(self.tr("Annotation Folder"))
        self._folder: Path | None = None
        self._missing: str | None = None
        self._on_next_to_images_callback = on_next_to_images

        self._icon = QtWidgets.QLabel()
        self._text = _ElidedLabel()
        self._text.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self._text.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Ignored,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )

        menu = QtWidgets.QMenu(self)
        self._next_to_images = menu.addAction(self.tr("Next to Images"))
        self._next_to_images.setCheckable(True)
        self._next_to_images.triggered.connect(self._on_next_to_images)
        menu.addAction(self.tr("Choose Annotation Folder…")).triggered.connect(
            on_choose
        )

        button = QtWidgets.QToolButton()
        button.setObjectName("annotationFolderButton")
        button.setAccessibleName(self.tr("Annotation Folder"))
        button.setArrowType(QtCore.Qt.ArrowType.DownArrow)
        button.setAutoRaise(True)
        # Not setMenu(): that draws a second arrow beside this one.
        button.clicked.connect(self._show_menu)
        self._menu = menu

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 2, 2)
        layout.setSpacing(4)
        layout.addWidget(self._icon)
        layout.addWidget(self._text, 1)
        layout.addWidget(button)

        self.set_folder(None)

    def set_folder(self, folder: Path | None, /) -> None:
        self._folder = folder
        self._sync()

    def set_missing(self, missing: str | None, /) -> None:
        # The warning shows while no folder is set, and only the caller
        # clears it, so a rolled-back folder change brings it back.
        self._missing = missing
        self._sync()

    def _sync(self) -> None:
        folder = self._folder
        self._next_to_images.setChecked(folder is None)
        font = self._text.font()
        font.setBold(folder is not None)
        self._text.setFont(font)
        if folder is not None:
            self._text.setText(folder.name or str(folder))
            self._text.setForegroundRole(QtGui.QPalette.ColorRole.WindowText)
            self.setToolTip(str(folder))
        elif self._missing is not None:
            self._text.setText(
                self.tr("Not found: %s · next to images")
                % (Path(self._missing).name or self._missing)
            )
            self._text.setForegroundRole(QtGui.QPalette.ColorRole.WindowText)
            self.setToolTip(self._missing)
        else:
            self._text.setText(self.tr("Next to images"))
            self._text.setForegroundRole(QtGui.QPalette.ColorRole.PlaceholderText)
            self.setToolTip("")
        self._sync_icon()
        self.update()

    def _show_menu(self) -> None:
        self._menu.popup(self.mapToGlobal(self.rect().bottomLeft()))

    def _on_next_to_images(self) -> None:
        self._on_next_to_images_callback()
        # Unchecking the active rule is not a choice; resync to the folder.
        self._next_to_images.setChecked(self._folder is None)

    def _sync_icon(self) -> None:
        if self._folder is not None:
            icon = new_icon("phosphor/folders.svg")
        elif self._missing is not None:
            icon = self.style().standardIcon(
                QtWidgets.QStyle.StandardPixmap.SP_MessageBoxWarning
            )
        else:
            icon = None
        self._icon.setVisible(icon is not None)
        if icon is not None:
            self._icon.setPixmap(icon.pixmap(16, 16))

    def mousePressEvent(self, event: QtGui.QMouseEvent, /) -> None:
        # The whole row opens the menu, not only the arrow.
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._show_menu()
            return
        super().mousePressEvent(event)

    def changeEvent(self, event: QtCore.QEvent, /) -> None:
        super().changeEvent(event)
        if event.type() == QtCore.QEvent.Type.PaletteChange:
            self._sync_icon()

    def paintEvent(self, event: QtGui.QPaintEvent, /) -> None:
        if self._folder is not None:
            # A highlight tint over the window color reads as a set state in
            # both light and dark schemes.
            palette = self.palette()
            tint = QtGui.QColor(palette.color(QtGui.QPalette.ColorRole.Highlight))
            tint.setAlphaF(0.18)
            painter = QtGui.QPainter(self)
            painter.fillRect(self.rect(), tint)
        super().paintEvent(event)
