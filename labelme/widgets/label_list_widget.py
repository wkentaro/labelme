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
        super().__init__()
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
        style.drawControl(QStyle.CE_ItemViewItem, options, painter)

        ctx = QtGui.QAbstractTextDocumentLayout.PaintContext()

        if option.state & QStyle.State_Selected:
            ctx.palette.setColor(
                QPalette.Text,
                option.palette.color(QPalette.Active, QPalette.HighlightedText),
            )
        else:
            ctx.palette.setColor(
                QPalette.Text,
                option.palette.color(QPalette.Active, QPalette.Text),
            )

        textRect = style.subElementRect(QStyle.SE_ItemViewItemText, options)

        if index.column() != 0:
            textRect.adjust(5, 0, 0, 0)

        thefuckyourshitup_constant = 4
        margin = (option.rect.height() - options.fontMetrics.height()) // 2
        margin = margin - thefuckyourshitup_constant
        textRect.setTop(textRect.top() + margin)

        painter.translate(textRect.topLeft())
        painter.setClipRect(textRect.translated(-textRect.topLeft()))
        self.doc.documentLayout().draw(painter, ctx)

        painter.restore()

    def sizeHint(self, option, index):
        thefuckyourshitup_constant = 4
        return QtCore.QSize(
            int(self.doc.idealWidth()),
            int(self.doc.size().height() - thefuckyourshitup_constant),
        )


class LabelListWidgetItem(QtGui.QStandardItem):
    def __init__(self, text=None, shape=None):
        super().__init__()
        self.setText(text or "")
        self.setShape(shape)

        self.setCheckable(True)
        self.setCheckState(Qt.Checked)
        self.setEditable(False)
        self.setTextAlignment(Qt.AlignBottom)

    def clone(self):
        return LabelListWidgetItem(self.text(), self.shape())

    def setShape(self, shape):
        self.setData(shape, Qt.UserRole)

    def shape(self):
        return self.data(Qt.UserRole)

    def __hash__(self):
        return id(self)

    def __repr__(self):
        return f'{self.__class__.__name__}("{self.text()}")'


class _ItemModel(QtGui.QStandardItemModel):
    itemDropped = QtCore.pyqtSignal()

    def removeRows(self, *args, **kwargs):
        ret = super().removeRows(*args, **kwargs)
        self.itemDropped.emit()
        return ret

    def dropMimeData(self, data, action, row: int, column: int, parent):
        # NOTE: By default, PyQt will overwrite items when dropped on them, so we need
        # to adjust the row/parent to insert after the item instead.

        # If row is -1, we're dropping on an item (which would overwrite)
        # Instead, we want to insert after it
        if row == -1 and parent.isValid():
            row = parent.row() + 1
            parent = parent.parent()

        # If still -1, append to end
        if row == -1:
            row = self.rowCount(parent)

        return super().dropMimeData(data, action, row, column, parent)


class LabelListWidget(QtWidgets.QListView):
    itemDoubleClicked = QtCore.pyqtSignal(LabelListWidgetItem)
    itemSelectionChanged = QtCore.pyqtSignal(list, list)

    def __init__(self):
        super().__init__()
        self._selectedItems = []

        self.setWindowFlags(Qt.Window)

        self._model: _ItemModel = _ItemModel()
        self._model.setItemPrototype(LabelListWidgetItem())
        self.setModel(self._model)

        self.setItemDelegate(HTMLDelegate())
        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)

        self.doubleClicked.connect(self.itemDoubleClickedEvent)
        self.selectionModel().selectionChanged.connect(self.itemSelectionChangedEvent)

    def __len__(self):
        return self._model.rowCount()

    def __getitem__(self, i):
        return self._model.item(i)

    def __iter__(self):
        for i in range(len(self)):
            yield self[i]

    @property
    def itemDropped(self):
        return self._model.itemDropped

    @property
    def itemChanged(self):
        return self._model.itemChanged

    def itemSelectionChangedEvent(self, selected, deselected):
        selected = [self._model.itemFromIndex(i) for i in selected.indexes()]
        deselected = [self._model.itemFromIndex(i) for i in deselected.indexes()]
        self.itemSelectionChanged.emit(selected, deselected)

    def itemDoubleClickedEvent(self, index):
        self.itemDoubleClicked.emit(self._model.itemFromIndex(index))

    def selectedItems(self):
        return [self._model.itemFromIndex(i) for i in self.selectedIndexes()]

    def scrollToItem(self, item):
        self.scrollTo(self._model.indexFromItem(item))

    def addItem(self, item):
        if not isinstance(item, LabelListWidgetItem):
            raise TypeError("item must be LabelListWidgetItem")
        self._model.setItem(self._model.rowCount(), 0, item)
        item.setSizeHint(self.itemDelegate().sizeHint(None, None))  # type: ignore[arg-type,union-attr]

    def removeItem(self, item):
        index = self._model.indexFromItem(item)
        self._model.removeRows(index.row(), 1)

    def selectItem(self, item):
        index = self._model.indexFromItem(item)
        self.selectionModel().select(index, QtCore.QItemSelectionModel.Select)

    def findItemByShape(self, shape):
        for row in range(self._model.rowCount()):
            item = self._model.item(row, 0)
            item = cast(LabelListWidgetItem, item)
            if item.shape() == shape:
                return item
        raise ValueError(f"cannot find shape: {shape}")

    def clear(self):
        self._model.clear()
