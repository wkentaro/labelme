from __future__ import annotations

from collections.abc import Iterator
from typing import Final
from typing import NamedTuple
from typing import cast

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QStyle

from .._shape import Shape

LABEL_COLOR_ROLE: Final = Qt.ItemDataRole.UserRole.value + 1


def format_shape_label(shape: Shape) -> str:
    assert shape.label is not None
    text = shape.label
    if shape.group_id is not None:
        text += f" ({shape.group_id})"
    enabled_flags = [key for key, value in (shape.flags or {}).items() if value]
    if enabled_flags:
        text += f" [{', '.join(enabled_flags)}]"
    return text


_INVALID_MODEL_INDEX: Final = QtCore.QModelIndex()


class TrailingColorDotDelegate(QtWidgets.QStyledItemDelegate):
    _DOT: Final = " ●"

    def sizeHint(
        self,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
    ) -> QtCore.QSize:
        size = super().sizeHint(option, index)
        if isinstance(index.data(LABEL_COLOR_ROLE), QtGui.QColor):
            size.setWidth(
                size.width() + option.fontMetrics.horizontalAdvance(self._DOT)
            )
        return size

    def paint(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
    ) -> None:
        color = index.data(LABEL_COLOR_ROLE)
        if not isinstance(color, QtGui.QColor):
            super().paint(painter, option, index)
            return

        opt = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        widget_style = (
            opt.widget.style() if opt.widget else QtWidgets.QApplication.style()
        )
        text_rect = widget_style.subElementRect(
            QStyle.SubElement.SE_ItemViewItemText, opt
        )
        text_margin = (
            widget_style.pixelMetric(
                QStyle.PixelMetric.PM_FocusFrameHMargin, None, opt.widget
            )
            + 1
        )
        dot_width = opt.fontMetrics.horizontalAdvance(self._DOT)
        available_width = max(0, text_rect.width() - 2 * text_margin - dot_width)

        # The dot is painted here rather than appended to opt.text, so that Qt
        # never draws the glyph in the text color underneath it: the two draws
        # land a subpixel apart and the one below shows as a fringe.
        opt.text = opt.fontMetrics.elidedText(
            opt.text, opt.textElideMode, available_width
        )
        widget_style.drawControl(
            QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget
        )

        dot_rect = QtCore.QRect(text_rect)
        dot_rect.setLeft(
            text_rect.left() + text_margin + opt.fontMetrics.horizontalAdvance(opt.text)
        )
        dot_rect.setWidth(dot_width)

        painter.save()
        painter.setFont(opt.font)
        painter.setPen(color)
        painter.drawText(dot_rect, opt.displayAlignment, self._DOT)
        painter.restore()


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

    def clone(self) -> LabelListWidgetItem:
        item = LabelListWidgetItem(text=self.text(), shape=self.shape())
        item.setData(self.data(LABEL_COLOR_ROLE), LABEL_COLOR_ROLE)
        return item

    def set_shape(self, shape: Shape | None) -> None:
        self.setData(shape, Qt.ItemDataRole.UserRole)

    def set_label(self, text: str, color: tuple[int, int, int]) -> None:
        self.setText(text)
        self.setData(QtGui.QColor(*color), LABEL_COLOR_ROLE)

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
        | QtCore.QPersistentModelIndex = _INVALID_MODEL_INDEX,
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

        self.setItemDelegate(TrailingColorDotDelegate())
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
