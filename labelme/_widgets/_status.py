from __future__ import annotations

from PySide6 import QtGui
from PySide6 import QtWidgets


def _format_position(*, x: int, y: int, intensity_text: str | None = None) -> str:
    base = f"x {x:>4}   y {y:>4}"
    if intensity_text:
        return f"{base}   {intensity_text}"
    return base


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

    def set_position(
        self, *, x: float, y: float, intensity_text: str | None = None
    ) -> None:
        self.setText(
            _format_position(x=round(x), y=round(y), intensity_text=intensity_text)
        )
