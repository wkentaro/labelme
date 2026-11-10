from __future__ import annotations

from PySide6 import QtGui
from PySide6 import QtWidgets


def _format_position(*, x: int, y: int) -> str:
    return f"x {x:>4}   y {y:>4}"


class StatusStats(QtWidgets.QLabel):
    def __init__(self) -> None:
        super().__init__("")

        font = QtGui.QFont()
        font.setFamily("monospace")
        font.setStyleHint(QtGui.QFont.StyleHint.Monospace)
        self.setFont(font)
        # Reserved for 4-digit coordinates, so the readout keeps its place.
        self.setMinimumWidth(
            self.fontMetrics().horizontalAdvance(_format_position(x=9999, y=9999))
        )

    def set_position(self, *, x: float, y: float) -> None:
        self.setText(_format_position(x=round(x), y=round(y)))
