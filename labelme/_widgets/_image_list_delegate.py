from __future__ import annotations

import itertools
import os
from collections.abc import Sequence
from typing import Final

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets
from PySide6.QtCore import Qt

_HEADING_PADDING: Final = 4


class ImageListDelegate(QtWidgets.QStyledItemDelegate):
    """Shows each folder once, as a heading over the first row of its run.

    The heading is part of that row, so rows still map one to one to Images
    and the list's row numbers, keys and counts are unchanged. Each row then
    shows only the file name; its text and tooltip keep the full path.
    """

    def __init__(self, *, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._show_folders = False

    def set_labels(self, labels: Sequence[str], /) -> None:
        # Headings pay off at two or more Images per folder run. One Image per
        # folder, such as sample_01/image.jpg, would add a heading to every
        # row, so those lists keep the full path in each row.
        folders = [os.path.dirname(label) for label in labels]
        runs = len(list(itertools.groupby(folders)))
        self._show_folders = any(folders) and runs * 2 <= len(folders)

    def heading(
        self, index: QtCore.QModelIndex | QtCore.QPersistentModelIndex, /
    ) -> str | None:
        if not self._show_folders:
            return None
        folder = os.path.dirname(index.data(Qt.ItemDataRole.DisplayRole))
        row = index.row()
        if row > 0:
            previous = index.sibling(row - 1, 0).data(Qt.ItemDataRole.DisplayRole)
            if os.path.dirname(previous) == folder:
                return None
        # Images at the top of the opened folder follow a heading too, so they
        # don't read as part of the folder above them.
        return (folder or os.curdir) + os.sep

    def initStyleOption(
        self,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
        /,
    ) -> None:
        super().initStyleOption(option, index)
        if self._show_folders:
            option.text = os.path.basename(option.text)

    def sizeHint(
        self,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
        /,
    ) -> QtCore.QSize:
        size = super().sizeHint(option, index)
        heading = self.heading(index)
        if heading is None:
            return size
        metrics = QtGui.QFontMetrics(_heading_font(option))
        # The width lets the list scroll sideways to a long heading, as it
        # does to a long row.
        size.setWidth(
            max(size.width(), metrics.horizontalAdvance(heading) + 2 * _HEADING_PADDING)
        )
        size.setHeight(size.height() + metrics.height() + 2 * _HEADING_PADDING)
        return size

    def paint(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
        /,
    ) -> None:
        heading = self.heading(index)
        if heading is None:
            super().paint(painter, option, index)
            return
        font = _heading_font(option)
        rect: QtCore.QRect = option.rect
        strip = QtCore.QRect(rect)
        strip.setHeight(QtGui.QFontMetrics(font).height() + 2 * _HEADING_PADDING)
        painter.save()
        painter.fillRect(strip, option.palette.alternateBase())
        painter.setFont(font)
        painter.setPen(option.palette.color(QtGui.QPalette.ColorRole.PlaceholderText))
        painter.drawText(
            strip.adjusted(_HEADING_PADDING, 0, -_HEADING_PADDING, 0),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            heading,
        )
        painter.restore()
        row = QtWidgets.QStyleOptionViewItem(option)
        row.rect = rect.adjusted(0, strip.height(), 0, 0)
        super().paint(painter, row, index)


def _heading_font(option: QtWidgets.QStyleOptionViewItem, /) -> QtGui.QFont:
    font = QtGui.QFont(option.font)
    font.setPointSizeF(font.pointSizeF() * 0.85)
    return font
