# -*- encoding: utf-8 -*-

from PyQt5.QtGui import QColor, QFont, QPalette, qRgb
from qtpy.QtCore import Qt
from qtpy import QtWidgets

from .escapable_qlist_widget import EscapableQListWidget


class UniqueLabelQListWidget(EscapableQListWidget):

    def __init__(self) -> None:
        super(EscapableQListWidget, self).__init__(),

    def mousePressEvent(self, event):
        super(UniqueLabelQListWidget, self).mousePressEvent(event)
        if not self.indexAt(event.pos()).isValid():
            self.clearSelection()

    def findItemsByLabel(self, label):
        items = []
        for row in range(self.count()):
            item = self.item(row)
            if item.data(Qt.UserRole) == label:
                items.append(item)
        return items

    def createItemFromLabel(self, label):
        item = QtWidgets.QListWidgetItem()
        item.setData(Qt.UserRole, label)
        return item

    def setItemLabel(self, item, label, color=None):
        qlabel = QtWidgets.QLabel()
        if color is None:
            qlabel.setText("{}".format(label))
        else:
            qlabel.setText(" " + label)
        qlabel.setFont(QFont("Arial", 12))
        palette = QPalette()

        palette.setColor(QPalette.Text, QColor(qRgb(*[c for c in color])))

        qlabel.setMargin(3)
        qlabel.setPalette(palette)
        qlabel.setAlignment(Qt.AlignBottom)

        item.setSizeHint(qlabel.sizeHint())
        #item.setBackground(QColor(qRgb(*[c for c in color])))
        self.setItemWidget(item, qlabel)
