from __future__ import annotations

from collections.abc import Iterable

from PyQt5 import QtCore

from labelme.shape import Shape


class ShapeClipboard(QtCore.QObject):
    availability_changed = QtCore.pyqtSignal(bool)

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._buffer: tuple[Shape, ...] = ()

    def store(self, shapes: Iterable[Shape]) -> None:
        snapshot = tuple(shape.copy() for shape in shapes)
        had_content = bool(self._buffer)
        self._buffer = snapshot
        if had_content != bool(snapshot):
            self.availability_changed.emit(bool(snapshot))

    def paste(self) -> list[Shape]:
        return [shape.copy() for shape in self._buffer]
