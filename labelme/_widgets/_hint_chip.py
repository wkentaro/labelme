from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import replace
from typing import Final

from PySide6 import QtGui
from PySide6.QtCore import QPointF
from PySide6.QtCore import QRectF
from PySide6.QtCore import Qt
from PySide6.QtCore import QTextBoundaryFinder

# The Return key's symbol, on the chip and on the AI-Find All Run button.
RETURN_GLYPH: Final = "\u21b5"

# Over the image, like the AI progress ring: fixed colors that read on light
# and dark pixels alike, whatever the theme.
_BACKGROUND: Final = QtGui.QColor(24, 24, 26, 214)
_HAIRLINE: Final = QtGui.QColor(255, 255, 255, 40)
_KEYCAP: Final = QtGui.QColor(255, 255, 255, 120)
_TEXT: Final = QtGui.QColor(255, 255, 255, 235)
_SECONDARY_TEXT: Final = QtGui.QColor(255, 255, 255, 170)

_PADDING: Final = 9.0
_ITEM_GAP: Final = 12.0
_MARK_WIDTH: Final = 14.0
_GAP: Final = 5.0


@dataclass(frozen=True)
class HintItem:
    text: str
    key: str | None = None
    # Paints the mark this gesture leaves on the canvas, centered on a point.
    mark: Callable[[QtGui.QPainter, QPointF], None] | None = None


def _fonts(base: QtGui.QFont, /) -> tuple[QtGui.QFont, QtGui.QFont]:
    first = QtGui.QFont(base)
    first.setPixelSize(12)
    first.setWeight(QtGui.QFont.Weight.Medium)
    rest = QtGui.QFont(base)
    rest.setPixelSize(11)
    return first, rest


def _keycap_height(metrics: QtGui.QFontMetricsF, /) -> float:
    return metrics.height() + 4


def _keycap_width(metrics: QtGui.QFontMetricsF, key: str, /) -> float:
    return max(_keycap_height(metrics), metrics.horizontalAdvance(key) + 10)


def _row_width(row: list[HintItem], font: QtGui.QFont, /) -> float:
    metrics = QtGui.QFontMetricsF(font)
    width = _ITEM_GAP * (len(row) - 1)
    for item in row:
        if item.mark is not None:
            width += _MARK_WIDTH + _GAP
        if item.key is not None:
            width += _keycap_width(metrics, item.key) + _GAP
        width += metrics.horizontalAdvance(item.text)
    return width


def _wrap(
    row: list[HintItem], font: QtGui.QFont, width: float, /
) -> list[list[HintItem]]:
    lines: list[list[HintItem]] = [[]]
    for item in row:
        for piece in _split(item, font, width):
            if lines[-1] and _row_width([*lines[-1], piece], font) > width:
                lines.append([])
            lines[-1].append(piece)
    return lines


def _split(item: HintItem, font: QtGui.QFont, width: float, /) -> list[HintItem]:
    # An item wider than a line breaks where the script allows a line break.
    # The mark and key stay on the first piece.
    if _row_width([item], font) <= width:
        return [item]
    finder = QTextBoundaryFinder(QTextBoundaryFinder.BoundaryType.Line, item.text)
    pieces = [replace(item, text="")]
    start = 0
    while (end := finder.toNextBoundary()) != -1:
        token = item.text[start:end]
        start = end
        last = pieces[-1]
        grown = replace(last, text=last.text + token)
        if last.text and _row_width([grown], font) > width:
            pieces[-1] = replace(last, text=last.text.rstrip())
            pieces.append(HintItem(token))
        else:
            pieces[-1] = grown
    return pieces


def _line_height(row_index: int, /) -> float:
    FIRST_ROW_HEIGHT: Final = 30.0
    ROW_HEIGHT: Final = 22.0
    return FIRST_ROW_HEIGHT if row_index == 0 else ROW_HEIGHT


def _height(lines: list[list[list[HintItem]]], /) -> float:
    return sum(_line_height(i) * len(row_lines) for i, row_lines in enumerate(lines))


def place_hint_chip(
    *,
    rows: list[list[HintItem]],
    font: QtGui.QFont,
    anchor: QRectF,
    bounds: QRectF,
) -> tuple[QRectF, list[list[list[HintItem]]]]:
    # Centered under the anchor, above it without room, else inside bounds,
    # with a margin from both. A row wraps where it allows a line break when
    # the chip would be wider than bounds, as in a narrow window or a long
    # translation.
    MARGIN: Final = 8.0
    fonts = _fonts(font)
    room = bounds.width() - 2 * (MARGIN + _PADDING)
    wrapped = [_wrap(row, fonts[min(i, 1)], room) for i, row in enumerate(rows)]
    # A view too short for every line keeps the first row and drops the
    # secondary ones from the end.
    while len(wrapped) > 1 and _height(wrapped) > bounds.height() - 2 * MARGIN:
        wrapped.pop()
    width = 2 * _PADDING + max(
        _row_width(line, fonts[min(i, 1)])
        for i, lines in enumerate(wrapped)
        for line in lines
    )
    height = _height(wrapped)
    x = anchor.center().x() - width / 2
    x = max(bounds.left() + MARGIN, min(x, bounds.right() - MARGIN - width))
    y = anchor.bottom() + MARGIN
    if y + height > bounds.bottom() - MARGIN:
        y = anchor.top() - MARGIN - height
    if y < bounds.top() + MARGIN:
        y = bounds.bottom() - MARGIN - height
    # A suggestion scrolled out of view still gets its hint.
    y = max(bounds.top() + MARGIN, min(y, bounds.bottom() - MARGIN - height))
    return QRectF(x, y, width, height), wrapped


def paint_hint_chip(
    painter: QtGui.QPainter,
    /,
    *,
    lines: list[list[list[HintItem]]],
    font: QtGui.QFont,
    rect: QRectF,
) -> None:
    RADIUS: Final = 8.0
    painter.save()
    painter.setPen(QtGui.QPen(_HAIRLINE, 1.0))
    painter.setBrush(_BACKGROUND)
    painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), RADIUS, RADIUS)
    fonts = _fonts(font)
    top = rect.top()
    for i, row_lines in enumerate(lines):
        if i > 0:
            # Rows after the first are secondary; a hairline sets them off.
            painter.setPen(QtGui.QPen(_HAIRLINE, 1.0))
            painter.drawLine(
                QPointF(rect.left() + 1, top), QPointF(rect.right() - 1, top)
            )
        for line in row_lines:
            _paint_row(
                painter,
                row=line,
                font=fonts[min(i, 1)],
                color=_TEXT if i == 0 else _SECONDARY_TEXT,
                origin=QPointF(rect.left() + _PADDING, top + _line_height(i) / 2),
            )
            top += _line_height(i)
    painter.restore()


def _paint_row(
    painter: QtGui.QPainter,
    /,
    *,
    row: list[HintItem],
    font: QtGui.QFont,
    color: QtGui.QColor,
    origin: QPointF,
) -> None:
    painter.setFont(font)
    metrics = QtGui.QFontMetricsF(font)
    x, y = origin.x(), origin.y()
    for item in row:
        if item.mark is not None:
            item.mark(painter, QPointF(x + _MARK_WIDTH / 2, y))
            x += _MARK_WIDTH + _GAP
        if item.key is not None:
            width = _keycap_width(metrics, item.key)
            height = _keycap_height(metrics)
            keycap = QRectF(x, y - height / 2, width, height)
            painter.setPen(QtGui.QPen(_KEYCAP, 1.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(keycap.adjusted(0.5, 0.5, -0.5, -0.5), 4, 4)
            painter.setPen(color)
            painter.drawText(keycap, Qt.AlignmentFlag.AlignCenter, item.key)
            x += width + _GAP
        width = metrics.horizontalAdvance(item.text)
        painter.setPen(color)
        painter.drawText(
            QRectF(x, y - metrics.height() / 2, width + 1, metrics.height()),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            item.text,
        )
        x += width + _ITEM_GAP
