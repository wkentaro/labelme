import html

from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt

from .escapable_qlist_widget import EscapableQListWidget


class UniqueLabelQListWidget(EscapableQListWidget):
    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if not self.indexAt(event.pos()).isValid():
            self.clearSelection()

    def findItemByLabel(self, label):
        for row in range(self.count()):
            item = self.item(row)
            if item.data(Qt.UserRole) == label:  # type: ignore[attr-defined,union-attr]
                return item

    def addItemForLabel(self, label: str, color: tuple[int, int, int]) -> None:
        if self.findItemByLabel(label):
            raise ValueError(f"Item for label '{label}' already exists")

        item = QtWidgets.QListWidgetItem()
        item.setData(Qt.UserRole, label)

        self.addItem(item)

        qlabel = QtWidgets.QLabel()
        qlabel.setText(
            f"{html.escape(label)} "
            f"<font color='#{color[0]:02x}{color[1]:02x}{color[2]:02x}'>●</font>"
        )
        qlabel.setAlignment(Qt.AlignBottom)

        item.setSizeHint(qlabel.sizeHint())

        self.setItemWidget(item, qlabel)
