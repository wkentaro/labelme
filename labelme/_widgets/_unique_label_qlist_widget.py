from __future__ import annotations

import contextlib
from collections.abc import Callable
from collections.abc import Container
from collections.abc import Iterable
from collections.abc import Iterator
from typing import Final
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets
from PySide6.QtCore import Qt

from ._label_list_widget import LABEL_COLOR_ROLE
from ._label_list_widget import ColorSwatchDelegate


class _EscapableQListWidget(QtWidgets.QListWidget):
    @override
    def keyPressEvent(self, keyEvent: QtGui.QKeyEvent, /) -> None:
        super().keyPressEvent(keyEvent)
        if keyEvent.key() == Qt.Key.Key_Escape:
            self.clearSelection()


# The next free role after the swatch color.
_UNUSED_ROLE: Final = LABEL_COLOR_ROLE + 1


class _LabelDelegate(ColorSwatchDelegate):
    @override
    def initStyleOption(
        self,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
        /,
    ) -> None:
        super().initStyleOption(option, index)
        # Read the palette at paint time, so the dimming follows the theme.
        if index.data(_UNUSED_ROLE):
            option.palette.setColor(
                QtGui.QPalette.ColorRole.Text,
                option.palette.color(QtGui.QPalette.ColorRole.PlaceholderText),
            )


def _section_header(
    *, title: str, buttons: list[QtWidgets.QToolButton]
) -> QtWidgets.QWidget:
    header = QtWidgets.QWidget()
    title_label = QtWidgets.QLabel(title)
    title_label.setForegroundRole(QtGui.QPalette.ColorRole.PlaceholderText)
    # Weight and size, not just color, so a header never reads as a label row.
    font = title_label.font()
    font.setWeight(QtGui.QFont.Weight.DemiBold)
    font.setPointSizeF(font.pointSizeF() - 1)
    title_label.setFont(font)
    layout = QtWidgets.QHBoxLayout(header)
    layout.setContentsMargins(4, 4, 0, 0)
    layout.addWidget(title_label)
    layout.addStretch(1)
    for button in buttons:
        layout.addWidget(button)
    return header


def _header_button(*, text: str, on_click: Callable[[], None]) -> QtWidgets.QToolButton:
    button = QtWidgets.QToolButton()
    button.setText(text)
    button.setAutoRaise(True)
    button.clicked.connect(on_click)
    return button


class UniqueLabelQListWidget(_EscapableQListWidget):
    """Lists the labels from Settings first, then the ones found in annotations.

    Each section sits under a header row. Header rows are disabled, so they
    take no selection and the arrow keys skip them, and they carry no text, so
    the AI prompt's completer, which reads this model, never suggests them.
    """

    label_remove_requested = QtCore.Signal(str)

    _found_header: QtWidgets.QListWidgetItem
    _clear_unused_button: QtWidgets.QToolButton

    def __init__(
        self,
        *,
        on_edit_settings_labels: Callable[[], None],
        on_clear_unused: Callable[[], None],
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self.setItemDelegate(_LabelDelegate(parent=self))
        self._add_header(
            title=self.tr("Label set"),
            buttons=[
                _header_button(text=self.tr("Edit…"), on_click=on_edit_settings_labels)
            ],
        )
        self._clear_unused_button = _header_button(
            text=self.tr("Clear Unused"), on_click=on_clear_unused
        )
        self._clear_unused_button.setEnabled(False)
        self._found_header = self._add_header(
            title=self.tr("Found in files"), buttons=[self._clear_unused_button]
        )

    def _add_header(
        self, *, title: str, buttons: list[QtWidgets.QToolButton]
    ) -> QtWidgets.QListWidgetItem:
        widget = _section_header(title=title, buttons=buttons)
        item = QtWidgets.QListWidgetItem()
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        item.setData(Qt.ItemDataRole.AccessibleTextRole, title)
        item.setSizeHint(widget.sizeHint())
        self.addItem(item)
        self.setItemWidget(item, widget)
        return item

    @override
    def mousePressEvent(self, mouseEvent: QtGui.QMouseEvent, /) -> None:
        super().mousePressEvent(mouseEvent)
        if not self.indexAt(mouseEvent.position().toPoint()).isValid():
            self.clearSelection()

    @override
    def event(self, event: QtCore.QEvent, /) -> bool:
        if (
            event.type() == QtCore.QEvent.Type.ShortcutOverride
            and isinstance(event, QtGui.QKeyEvent)
            and _is_removal_key(event=event)
        ):
            # The window's Delete Shapes action must not handle list keystrokes.
            event.accept()
            return True
        return super().event(event)

    @override
    def keyPressEvent(self, keyEvent: QtGui.QKeyEvent, /) -> None:
        if not _is_removal_key(event=keyEvent):
            super().keyPressEvent(keyEvent)
            return
        found_labels = self.found_labels()
        for item in self.selectedItems():
            label = item.data(Qt.ItemDataRole.UserRole)
            if label in found_labels:
                self.label_remove_requested.emit(label)

    def _label_items(self) -> list[QtWidgets.QListWidgetItem]:
        return [
            item
            for row in range(self.count())
            if (item := self.item(row)).data(Qt.ItemDataRole.UserRole) is not None
        ]

    def labels(self) -> list[str]:
        return [item.data(Qt.ItemDataRole.UserRole) for item in self._label_items()]

    def found_labels(self) -> list[str]:
        return [
            self.item(row).data(Qt.ItemDataRole.UserRole)
            for row in range(self.row(self._found_header) + 1, self.count())
        ]

    def set_unused_labels(self, *, labels: Container[str]) -> None:
        # Dimmed rows preview what Clear Unused removes, so only labels found
        # in files dim, including one that just left the label set.
        found_labels = self.found_labels()
        any_unused = False
        for item in self._label_items():
            label = item.data(Qt.ItemDataRole.UserRole)
            unused = label in found_labels and label in labels
            any_unused |= unused
            item.setData(_UNUSED_ROLE, unused)
        self._clear_unused_button.setEnabled(any_unused)

    def label_index(self, *, label: str) -> int:
        # Canvas painting calls this per label per frame, so count rows rather
        # than list the labels. Past the end for an absent label, which is
        # where it would be added.
        HEADER_COUNT: Final = 2
        item = self.find_label_item(label=label)
        if item is None:
            return self.count() - HEADER_COUNT
        row = self.row(item)
        return row - 1 - (row > self.row(self._found_header))

    def find_label_item(self, *, label: str) -> QtWidgets.QListWidgetItem | None:
        for item in self.findItems(
            label, Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchCaseSensitive
        ):
            if item.data(Qt.ItemDataRole.UserRole) is not None:
                return item
        return None

    def add_label_item(
        self, *, label: str, color: tuple[int, int, int], from_settings: bool = False
    ) -> None:
        if self.find_label_item(label=label):
            raise ValueError(f"Item for label '{label}' already exists")
        item = _new_label_item(label=label, color=color)
        if from_settings:
            self.insertItem(self.row(self._found_header), item)
        else:
            self.addItem(item)

    def set_settings_labels(
        self,
        *,
        labels: list[str],
        found_in_annotations: Container[str],
        color: Callable[[str], tuple[int, int, int]],
    ) -> None:
        with self._keeping_selection():
            # A label leaving Settings moves to the end of the annotations
            # section when it was found in annotations, and is removed
            # otherwise.
            for row in reversed(range(1, self.row(self._found_header))):
                label = self.item(row).data(Qt.ItemDataRole.UserRole)
                if label in labels:
                    continue
                item = self.takeItem(row)
                if label in found_in_annotations:
                    self.addItem(item)
            for row, label in enumerate(labels, start=1):
                item = self.find_label_item(label=label)
                if item is None:
                    self.insertItem(
                        row, _new_label_item(label=label, color=color(label))
                    )
                elif self.row(item) != row:
                    self.insertItem(row, self.takeItem(self.row(item)))

    def remove_label_items(self, *, labels: Iterable[str]) -> None:
        with self._keeping_selection():
            for label in labels:
                item = self.find_label_item(label=label)
                if item is None:
                    raise ValueError(f"No item for label '{label}'")
                self.takeItem(self.row(item))

    @contextlib.contextmanager
    def _keeping_selection(self) -> Iterator[None]:
        # Moving or removing a row moves Qt's selection to a neighbor, which
        # would become the label new shapes get, so restore it afterwards.
        selected = self.selectedItems()
        current = self.currentItem()
        yield
        self.clearSelection()
        if current is not None and self.row(current) >= 0:
            self.setCurrentItem(
                current, QtCore.QItemSelectionModel.SelectionFlag.NoUpdate
            )
        for item in selected:
            if self.row(item) >= 0:
                item.setSelected(True)


def _new_label_item(
    *, label: str, color: tuple[int, int, int]
) -> QtWidgets.QListWidgetItem:
    item = QtWidgets.QListWidgetItem(label)
    item.setData(Qt.ItemDataRole.UserRole, label)
    item.setData(LABEL_COLOR_ROLE, QtGui.QColor(*color))
    return item


def _is_removal_key(*, event: QtGui.QKeyEvent) -> bool:
    return event.modifiers() == Qt.KeyboardModifier.NoModifier and event.key() in (
        Qt.Key.Key_Delete,
        Qt.Key.Key_Backspace,
    )
