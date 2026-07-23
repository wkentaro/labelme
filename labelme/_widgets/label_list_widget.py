from __future__ import annotations

import html
import math
from collections.abc import Iterator
from typing import Final
from typing import NamedTuple
from typing import cast

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QStyle

from .._shape import Shape


def format_label_with_color_dot(text: str, color: tuple[int, int, int]) -> str:
    r, g, b = color
    return f'{html.escape(text)} <font color="#{r:02x}{g:02x}{b:02x}">●</font>'


def format_shape_label(shape: Shape, fill_rgb: tuple[int, int, int]) -> str:
    assert shape.label is not None
    text = shape.label
    if shape.group_id is not None:
        text += f" ({shape.group_id})"
    enabled_flags = [key for key, value in (shape.flags or {}).items() if value]
    if enabled_flags:
        text += f" [{', '.join(enabled_flags)}]"
    return format_label_with_color_dot(text=text, color=fill_rgb)


class HTMLDelegate(QtWidgets.QStyledItemDelegate):
    _VERT_FUDGE: Final = 4

    def paint(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
    ) -> None:
        opt = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        html = opt.text
        opt.text = ""

        widget_style = (
            opt.widget.style() if opt.widget else QtWidgets.QApplication.style()
        )
        widget_style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter)

        doc = QtGui.QTextDocument()
        if opt.state & QStyle.StateFlag.State_Selected:
            text_color = opt.palette.color(
                QPalette.ColorGroup.Active, QPalette.ColorRole.HighlightedText
            )
        else:
            text_color = opt.palette.color(
                QPalette.ColorGroup.Active, QPalette.ColorRole.Text
            )
        doc.setDefaultStyleSheet(f"body {{ color: {text_color.name()}; }}")
        doc.setHtml(f"<body>{html}</body>")

        text_rect = widget_style.subElementRect(
            QStyle.SubElement.SE_ItemViewItemText, opt
        )
        if index.column() != 0:
            text_rect.adjust(5, 0, 0, 0)

        # opt.text was emptied above, so some styles (e.g. Adwaita) return a
        # text sub-rect too narrow for the rendered HTML and clip the label.
        # Widen it to the document's ideal width so the text stays visible.
        text_rect.setWidth(max(text_rect.width(), math.ceil(doc.idealWidth())))

        margin = (
            option.rect.height() - opt.fontMetrics.height()
        ) // 2 - self._VERT_FUDGE
        text_rect.setTop(text_rect.top() + margin)

        painter.save()
        painter.translate(text_rect.topLeft())
        painter.setClipRect(text_rect.translated(-text_rect.topLeft()))
        doc.drawContents(painter)
        painter.restore()

    def sizeHint(
        self,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
    ) -> QtCore.QSize:
        opt = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        doc = QtGui.QTextDocument()
        doc.setHtml(opt.text)
        height = int(doc.size().height()) - self._VERT_FUDGE
        return QtCore.QSize(int(doc.idealWidth()), height)

    def default_size_hint(self) -> QtCore.QSize:
        doc = QtGui.QTextDocument()
        height = int(doc.size().height()) - self._VERT_FUDGE
        return QtCore.QSize(int(doc.idealWidth()), height)


class LabelListWidgetItem(QtGui.QStandardItem):
    def __init__(self, text: str | None = None, shape: Shape | None = None) -> None:
        super().__init__()
        self.setText(text or "")
        self.set_shape(shape)

        self.setCheckable(True)
        self.setCheckState(
            Qt.CheckState.Checked
            if shape is None or shape.visible
            else Qt.CheckState.Unchecked
        )
        self.setEditable(False)
        self.setTextAlignment(Qt.AlignmentFlag.AlignBottom)

    def clone(self) -> LabelListWidgetItem:
        return LabelListWidgetItem(self.text(), self.shape())

    def set_shape(self, shape: Shape | None) -> None:
        self.setData(shape, Qt.ItemDataRole.UserRole)

    def shape(self) -> Shape | None:
        return self.data(Qt.ItemDataRole.UserRole)

    def __hash__(self) -> int:
        return id(self)

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}("{self.text()}")'


class _ItemModel(QtGui.QStandardItemModel):
    item_dropped = QtCore.Signal()

    def removeRows(
        self,
        row: int,
        count: int,
        parent: QtCore.QModelIndex
        | QtCore.QPersistentModelIndex = QtCore.QModelIndex(),
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
        parent: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
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


class _ItemSnapshot(NamedTuple):
    # A persistent index, not the item itself: the model owns the item and
    # deletes it on row removal, which would leave a dead wrapper here.
    index: QtCore.QPersistentModelIndex
    check_state: Qt.CheckState


class LabelListWidget(QtWidgets.QListView):
    item_double_clicked = QtCore.Signal(LabelListWidgetItem)
    item_selection_changed = QtCore.Signal(list, list)

    def __init__(self) -> None:
        super().__init__()

        self.setWindowFlags(Qt.WindowType.Window)

        self._model: _ItemModel = _ItemModel()
        self._model.setItemPrototype(LabelListWidgetItem())
        self.setModel(self._model)

        self.setItemDelegate(HTMLDelegate())
        self.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)

        self.doubleClicked.connect(self._on_item_double_clicked)
        self.selectionModel().selectionChanged.connect(self._on_item_selection_changed)

        self._press_snapshot: tuple[_ItemSnapshot, ...] = ()

    def mousePressEvent(self, e: QtGui.QMouseEvent) -> None:
        self._press_snapshot = tuple(
            _ItemSnapshot(
                index=QtCore.QPersistentModelIndex(self._model.indexFromItem(item)),
                check_state=item.checkState(),
            )
            for item in self.selected_items()
        )
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e: QtGui.QMouseEvent) -> None:
        super().mouseReleaseEvent(e)

        # Restore the multi-selection only when a checkbox toggle collapsed it.
        # A plain row click should narrow the selection to one row.
        check_state_changed = False
        items_at_press: list[LabelListWidgetItem] = []
        for snap in self._press_snapshot:
            item = self._resolve_item(index=snap.index)
            if item is None:
                continue
            items_at_press.append(item)
            check_state_changed |= item.checkState() != snap.check_state
        if (
            check_state_changed
            and len(items_at_press) > 1
            and set(self.selected_items()) != set(items_at_press)
        ):
            self.selectionModel().clearSelection()
            for item in items_at_press:
                self.selectionModel().select(
                    self._model.indexFromItem(item),
                    QtCore.QItemSelectionModel.SelectionFlag.Select,
                )

        self._press_snapshot = ()

    def selection_at_press(self) -> tuple[LabelListWidgetItem, ...]:
        return tuple(
            item
            for snap in self._press_snapshot
            if (item := self._resolve_item(index=snap.index)) is not None
        )

    def _resolve_item(
        self, index: QtCore.QPersistentModelIndex
    ) -> LabelListWidgetItem | None:
        if not index.isValid():
            return None
        return cast(LabelListWidgetItem, self._model.itemFromIndex(index))

    def __len__(self) -> int:
        return self._model.rowCount()

    def __getitem__(self, i: int) -> LabelListWidgetItem:
        return cast(LabelListWidgetItem, self._model.item(i))

    def __iter__(self) -> Iterator[LabelListWidgetItem]:
        for i in range(len(self)):
            yield self[i]

    @property
    def item_dropped(self) -> QtCore.SignalInstance:
        return self._model.item_dropped

    @property
    def item_changed(self) -> QtCore.SignalInstance:
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
        delegate = cast(HTMLDelegate, self.itemDelegate())
        item.setSizeHint(delegate.default_size_hint())

    def remove_item(self, item: LabelListWidgetItem) -> None:
        index = self._model.indexFromItem(item)
        self._model.removeRows(index.row(), 1)

    def select_item(self, item: LabelListWidgetItem) -> None:
        index = self._model.indexFromItem(item)
        self.selectionModel().select(
            index, QtCore.QItemSelectionModel.SelectionFlag.Select
        )

    def find_item_by_shape(self, shape: Shape) -> LabelListWidgetItem:
        for row in range(self._model.rowCount()):
            item = self._model.item(row, 0)
            item = cast(LabelListWidgetItem, item)
            if item.shape() == shape:
                return item
        raise ValueError(f"cannot find shape: {shape}")

    def clear(self) -> None:
        self._model.clear()
