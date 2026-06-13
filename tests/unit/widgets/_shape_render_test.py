from __future__ import annotations

import numpy as np
from PyQt5 import QtCore
from PyQt5 import QtGui
from pytestqt.qtbot import QtBot

from labelme._shape import Shape
from labelme.widgets._shape_render import Palette
from labelme.widgets._shape_render import ShapeRenderContext
from labelme.widgets._shape_render import render_shape


def _make_context(*, show_labels: bool) -> ShapeRenderContext:
    return ShapeRenderContext(
        scale=1.0,
        palette=Palette.from_rgb(rgb=(0, 255, 0)),
        point_size=8,
        point_type="round",
        selected=False,
        fill=False,
        highlight=None,
        rotation_highlight=None,
        show_labels=show_labels,
    )


def _make_rectangle(*, label: str | None) -> Shape:
    return Shape(
        label=label,
        shape_type="rectangle",
        points=np.array([(40.0, 60.0), (120.0, 100.0)], dtype=np.float64),
    )


def _count_opaque_pixels(*, shape: Shape, context: ShapeRenderContext) -> int:
    image = QtGui.QImage(200, 200, QtGui.QImage.Format_ARGB32)
    image.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(image)
    render_shape(painter=painter, shape=shape, context=context)
    painter.end()
    buffer = bytes(image.constBits().asarray(image.byteCount()))
    alpha = np.frombuffer(buffer, dtype=np.uint8).reshape(-1, 4)[:, 3]
    return int(np.count_nonzero(alpha))


def test_render_shape_draws_label_when_show_labels_enabled(qtbot: QtBot) -> None:
    shape = _make_rectangle(label="car")

    without_label = _count_opaque_pixels(
        shape=shape, context=_make_context(show_labels=False)
    )
    with_label = _count_opaque_pixels(
        shape=shape, context=_make_context(show_labels=True)
    )

    assert with_label > without_label


def test_render_shape_omits_label_for_empty_label(qtbot: QtBot) -> None:
    context = _make_context(show_labels=True)

    labeled = _count_opaque_pixels(shape=_make_rectangle(label="car"), context=context)
    unlabeled = _count_opaque_pixels(shape=_make_rectangle(label=None), context=context)

    assert unlabeled < labeled
