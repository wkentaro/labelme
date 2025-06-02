from typing import cast

from PyQt5 import QtCore
from PyQt5 import QtGui
from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPalette
from PyQt5.QtWidgets import QStyle


# https://stackoverflow.com/a/2039745/4158863
class HTMLDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, parent=None):
        super(HTMLDelegate, self).__init__()
        self.doc = QtGui.QTextDocument(self)

    def paint(self, painter, option, index):
        painter.save()

        options = QtWidgets.QStyleOptionViewItem(option)

        self.initStyleOption(options, index)
        self.doc.setHtml(options.text)
        options.text = ""

        style = (
            QtWidgets.QApplication.style()
            if options.widget is None
            else options.widget.style()
        )
        style.drawControl(QStyle.CE_ItemViewItem, options, painter)  # type: ignore[attr-defined,union-attr]

        ctx = QtGui.QAbstractTextDocumentLayout.PaintContext()

        if option.state & QStyle.State_Selected:  # type: ignore[attr-defined]
            ctx.palette.setColor(
                QPalette.Text,
                option.palette.color(QPalette.Active, QPalette.HighlightedText),
            )
        else:
            ctx.palette.setColor(
                QPalette.Text,
                option.palette.color(QPalette.Active, QPalette.Text),
            )

        textRect = style.subElementRect(QStyle.SE_ItemViewItemText, options)  # type: ignore[attr-defined,union-attr]

        if index.column() != 0:
            textRect.adjust(5, 0, 0, 0)

        thefuckyourshitup_constant = 4
        margin = (option.rect.height() - options.fontMetrics.height()) // 2
        margin = margin - thefuckyourshitup_constant
        textRect.setTop(textRect.top() + margin)

        painter.translate(textRect.topLeft())
        painter.setClipRect(textRect.translated(-textRect.topLeft()))
        self.doc.documentLayout().draw(painter, ctx)  # type: ignore[union-attr]

        painter.restore()

    def sizeHint(self, option, index):
        thefuckyourshitup_constant = 4
        return QtCore.QSize(
            int(self.doc.idealWidth()),
            int(self.doc.size().height() - thefuckyourshitup_constant),
        )


class LabelListWidgetItem(QtGui.QStandardItem):
    def __init__(self, text=None, shape=None):
        super(LabelListWidgetItem, self).__init__()
        self.setText(text or "")
        self.setShape(shape)

        self.setCheckable(True)
        self.setCheckState(Qt.Checked)  # type: ignore[attr-defined]
        self.setEditable(False)
        self.setTextAlignment(Qt.AlignBottom)  # type: ignore[attr-defined]

    def clone(self):
        return LabelListWidgetItem(self.text(), self.shape())

    def setShape(self, shape):
        self.setData(shape, Qt.UserRole)  # type: ignore[attr-defined]

    def shape(self):
        return self.data(Qt.UserRole)  # type: ignore[attr-defined]

    def __hash__(self):
        return id(self)

    def __repr__(self):
        return '{}("{}")'.format(self.__class__.__name__, self.text())


class StandardItemModel(QtGui.QStandardItemModel):
    itemDropped = QtCore.pyqtSignal()

    def removeRows(self, *args, **kwargs):
        ret = super().removeRows(*args, **kwargs)
        self.itemDropped.emit()
        return ret


class LabelListWidget(QtWidgets.QListView):
    itemDoubleClicked = QtCore.pyqtSignal(LabelListWidgetItem)
    itemSelectionChanged = QtCore.pyqtSignal(list, list)

    def __init__(self):
        super(LabelListWidget, self).__init__()
        self._selectedItems = []

        self.setWindowFlags(Qt.Window)  # type: ignore[attr-defined]

        self._model: StandardItemModel = StandardItemModel()
        self._model.setItemPrototype(LabelListWidgetItem())  # type: ignore[union-attr]
        self.setModel(self._model)

        self.setItemDelegate(HTMLDelegate())
        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)  # type: ignore[attr-defined]

        self.doubleClicked.connect(self.itemDoubleClickedEvent)
        self.selectionModel().selectionChanged.connect(self.itemSelectionChangedEvent)  # type: ignore[union-attr]

    def __len__(self):
        return self._model.rowCount()  # type: ignore[union-attr]

    def __getitem__(self, i):
        return self._model.item(i)  # type: ignore[union-attr]

    def __iter__(self):
        for i in range(len(self)):
            yield self[i]

    @property
    def itemDropped(self):
        return self._model.itemDropped  # type: ignore[union-attr]

    @property
    def itemChanged(self):
        return self._model.itemChanged  # type: ignore[union-attr]

    def itemSelectionChangedEvent(self, selected, deselected):
        selected = [self._model.itemFromIndex(i) for i in selected.indexes()]  # type: ignore[union-attr]
        deselected = [self._model.itemFromIndex(i) for i in deselected.indexes()]  # type: ignore[union-attr]
        self.itemSelectionChanged.emit(selected, deselected)

    def itemDoubleClickedEvent(self, index):
        self.itemDoubleClicked.emit(self._model.itemFromIndex(index))  # type: ignore[union-attr]

    def selectedItems(self):
        return [self._model.itemFromIndex(i) for i in self.selectedIndexes()]  # type: ignore[union-attr]

    def scrollToItem(self, item):
        self.scrollTo(self._model.indexFromItem(item))  # type: ignore[union-attr]

    def addItem(self, item):
        if not isinstance(item, LabelListWidgetItem):
            raise TypeError("item must be LabelListWidgetItem")
        self._model.setItem(self._model.rowCount(), 0, item)  # type: ignore[union-attr]
        item.setSizeHint(self.itemDelegate().sizeHint(None, None))  # type: ignore[arg-type,union-attr]

    def removeItem(self, item):
        index = self._model.indexFromItem(item)  # type: ignore[union-attr]
        self._model.removeRows(index.row(), 1)  # type: ignore[union-attr]

    def selectItem(self, item):
        index = self._model.indexFromItem(item)  # type: ignore[union-attr]
        self.selectionModel().select(index, QtCore.QItemSelectionModel.Select)  # type: ignore[attr-defined,union-attr]

    def findItemByShape(self, shape):
        for row in range(self._model.rowCount()):  # type: ignore[union-attr]
            item = self._model.item(row, 0)  # type: ignore[union-attr]
            item = cast(LabelListWidgetItem, item)
            if item.shape() == shape:
                return item
        raise ValueError("cannot find shape: {}".format(shape))

    def clear(self):
        self._model.clear()  # type: ignore[union-attr]
