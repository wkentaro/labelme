from __future__ import annotations

import html
from collections.abc import Iterator
from typing import TYPE_CHECKING
from typing import cast

if TYPE_CHECKING:
    from labelme.shape import Shape

from PyQt5 import QtCore
from PyQt5 import QtGui
from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPalette
from PyQt5.QtWidgets import QStyle


def format_label_with_color_dot(text: str, color: tuple[int, int, int]) -> str:
    r, g, b = color
    return f'{html.escape(text)} <font color="#{r:02x}{g:02x}{b:02x}">●</font>'


def format_shape_label(shape: Shape) -> str:
    assert shape.label is not None
    if shape.group_id is None:
        text = shape.label
    else:
        text = f"{shape.label} ({shape.group_id})"
    return format_label_with_color_dot(text=text, color=shape.fill_color.getRgb()[:3])


class HTMLDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)

    def paint(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> None:
        opt = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        html = opt.text
        opt.text = ""

        widget_style = (
            opt.widget.style() if opt.widget else QtWidgets.QApplication.style()
        )
        widget_style.drawControl(QStyle.CE_ItemViewItem, opt, painter)

        doc = QtGui.QTextDocument()
        if opt.state & QStyle.State_Selected:
            text_color = opt.palette.color(QPalette.Active, QPalette.HighlightedText)
        else:
            text_color = opt.palette.color(QPalette.Active, QPalette.Text)
        doc.setDefaultStyleSheet(f"body {{ color: {text_color.name()}; }}")
        doc.setHtml(f"<body>{html}</body>")

        text_rect = widget_style.subElementRect(QStyle.SE_ItemViewItemText, opt)
        if index.column() != 0:
            text_rect.adjust(5, 0, 0, 0)

        VERT_FUDGE = 4
        margin = (option.rect.height() - opt.fontMetrics.height()) // 2 - VERT_FUDGE
        text_rect.setTop(text_rect.top() + margin)

        painter.save()
        painter.translate(text_rect.topLeft())
        painter.setClipRect(text_rect.translated(-text_rect.topLeft()))
        doc.drawContents(painter)
        painter.restore()

    def sizeHint(
        self,
        option: QtWidgets.QStyleOptionViewItem | None,
        index: QtCore.QModelIndex | None,
    ) -> QtCore.QSize:
        VERT_FUDGE = 4
        if option is not None and index is not None:
            opt = QtWidgets.QStyleOptionViewItem(option)
            self.initStyleOption(opt, index)
            doc = QtGui.QTextDocument()
            doc.setHtml(opt.text)
            height = int(doc.size().height()) - VERT_FUDGE
            return QtCore.QSize(int(doc.idealWidth()), height)
        doc = QtGui.QTextDocument()
        height = int(doc.size().height()) - VERT_FUDGE
        return QtCore.QSize(int(doc.idealWidth()), height)


class LabelListWidgetItem(QtGui.QStandardItem):
    def __init__(self, text: str | None = None, shape: Shape | None = None) -> None:
        super().__init__()
        self.setText(text or "")
        self.set_shape(shape)

        self.setCheckable(True)
        self.setCheckState(Qt.Checked)
        self.setEditable(False)
        self.setTextAlignment(Qt.AlignBottom)

    def clone(self) -> LabelListWidgetItem:
        return LabelListWidgetItem(self.text(), self.shape())

    def set_shape(self, shape: Shape | None) -> None:
        self.setData(shape, Qt.UserRole)

    def shape(self) -> Shape | None:
        return self.data(Qt.UserRole)

    def __hash__(self) -> int:
        return id(self)

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}("{self.text()}")'


class _ItemModel(QtGui.QStandardItemModel):
    item_dropped = QtCore.pyqtSignal()

    def removeRows(
        self,
        row: int,
        count: int,
        parent: QtCore.QModelIndex = QtCore.QModelIndex(),
    ) -> bool:
        ret = super().removeRows(row, count, parent)
        self.item_dropped.emit()
        return ret

    def dropMimeData(
        self,
        data: QtCore.QMimeData,
        action: Qt.DropAction,
        row: int,
        column: int,
        parent: QtCore.QModelIndex,
    ) -> bool:
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
    item_double_clicked = QtCore.pyqtSignal(LabelListWidgetItem)
    item_selection_changed = QtCore.pyqtSignal(list, list)

    def __init__(self) -> None:
        super().__init__()

        self.setWindowFlags(Qt.Window)

        self._model: _ItemModel = _ItemModel()
        self._model.setItemPrototype(LabelListWidgetItem())
        self.setModel(self._model)

        self.setItemDelegate(HTMLDelegate())
        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)

        self.doubleClicked.connect(self._on_item_double_clicked)
        self.selectionModel().selectionChanged.connect(self._on_item_selection_changed)

    def __len__(self) -> int:
        return self._model.rowCount()

    def __getitem__(self, i: int) -> LabelListWidgetItem:
        return cast(LabelListWidgetItem, self._model.item(i))

    def __iter__(self) -> Iterator[LabelListWidgetItem]:
        for i in range(len(self)):
            yield self[i]

    @property
    def item_dropped(self) -> QtCore.pyqtBoundSignal:
        return self._model.item_dropped

    @property
    def item_changed(self) -> QtCore.pyqtBoundSignal:
        return self._model.itemChanged

    def _on_item_selection_changed(
        self,
        selected: QtCore.QItemSelection,
        deselected: QtCore.QItemSelection,
    ) -> None:
        selected_items = [self._model.itemFromIndex(i) for i in selected.indexes()]
        deselected_items = [self._model.itemFromIndex(i) for i in deselected.indexes()]
        self.item_selection_changed.emit(selected_items, deselected_items)

    def _on_item_double_clicked(self, index: QtCore.QModelIndex) -> None:
        self.item_double_clicked.emit(self._model.itemFromIndex(index))

    def selected_items(self) -> list[LabelListWidgetItem]:
        return [
            cast(LabelListWidgetItem, self._model.itemFromIndex(i))
            for i in self.selectedIndexes()
        ]

    def scroll_to_item(self, item: LabelListWidgetItem) -> None:
        self.scrollTo(self._model.indexFromItem(item))

    def add_item(self, item: LabelListWidgetItem) -> None:
        if not isinstance(item, LabelListWidgetItem):
            raise TypeError("item must be LabelListWidgetItem")
        self._model.setItem(self._model.rowCount(), 0, item)
        item.setSizeHint(self.itemDelegate().sizeHint(None, None))  # ty: ignore[invalid-argument-type]

    def remove_item(self, item: LabelListWidgetItem) -> None:
        index = self._model.indexFromItem(item)
        self._model.removeRows(index.row(), 1)

    def select_item(self, item: LabelListWidgetItem) -> None:
        index = self._model.indexFromItem(item)
        self.selectionModel().select(index, QtCore.QItemSelectionModel.Select)

    def find_item_by_shape(self, shape: Shape) -> LabelListWidgetItem:
        for row in range(self._model.rowCount()):
            item = self._model.item(row, 0)
            item = cast(LabelListWidgetItem, item)
            if item.shape() == shape:
                return item
        raise ValueError(f"cannot find shape: {shape}")

    def clear(self) -> None:
        self._model.clear()
