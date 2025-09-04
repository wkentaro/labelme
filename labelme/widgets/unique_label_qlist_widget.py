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

    def createItemFromLabel(self, label):
        if self.findItemByLabel(label):
            raise ValueError(f"Item for label '{label}' already exists")

        item = QtWidgets.QListWidgetItem()
        item.setData(Qt.UserRole, label)
        return item

    def setItemLabel(self, item, label, color=None):
        qlabel = QtWidgets.QLabel()
        if color is None:
            qlabel.setText(f"{label}")
        else:
            r, g, b = color
            qlabel.setText(
                f'{html.escape(label)} <font color="#{r:02x}{g:02x}{b:02x}">●</font>'
            )
        qlabel.setAlignment(Qt.AlignBottom)

        item.setSizeHint(qlabel.sizeHint())

        self.setItemWidget(item, qlabel)
