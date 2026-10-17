from __future__ import annotations

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets
from PySide6.QtCore import Qt

from ._label_list_widget import LABEL_COLOR_ROLE
from ._label_list_widget import TrailingColorDotDelegate


class _EscapableQListWidget(QtWidgets.QListWidget):
    def keyPressEvent(self, keyEvent: QtGui.QKeyEvent, /) -> None:
        super().keyPressEvent(keyEvent)
        if keyEvent.key() == Qt.Key.Key_Escape:
            self.clearSelection()


class UniqueLabelQListWidget(_EscapableQListWidget):
    label_remove_requested = QtCore.Signal(str)

    def __init__(self, *, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent=parent)
        self.setItemDelegate(TrailingColorDotDelegate(parent=self))

    def mousePressEvent(self, mouseEvent: QtGui.QMouseEvent, /) -> None:
        super().mousePressEvent(mouseEvent)
        if not self.indexAt(mouseEvent.position().toPoint()).isValid():
            self.clearSelection()

    def keyPressEvent(self, keyEvent: QtGui.QKeyEvent, /) -> None:
        if keyEvent.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            item = self.currentItem()
            if item is not None:
                label = item.data(Qt.ItemDataRole.UserRole)
                if isinstance(label, str):
                    self.label_remove_requested.emit(label)
                    keyEvent.accept()
                    return
        super().keyPressEvent(keyEvent)

    @property
    def labels(self) -> list[str]:
        res: list[str] = []
        for i in range(self.count()):
            item = self.item(i)
            if item is None:
                continue
            val = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(val, str):
                res.append(val)
        return res

    def find_label_item(self, *, label: str) -> QtWidgets.QListWidgetItem | None:
        items = self.findItems(
            label, Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchCaseSensitive
        )
        return items[0] if items else None

    def add_label_item(self, *, label: str, color: tuple[int, int, int]) -> None:
        if self.find_label_item(label=label):
            raise ValueError(f"Item for label '{label}' already exists")

        item = QtWidgets.QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, label)  # for find_label_item
        item.setData(LABEL_COLOR_ROLE, QtGui.QColor(*color))
        item.setText(label)
        self.addItem(item)

    def remove_label_item(self, *, label: str) -> None:
        item = self.find_label_item(label=label)
        if item is None:
            raise ValueError(f"Item for label '{label}' not found")
        row = self.row(item)
        self.takeItem(row)
