from __future__ import annotations

import numpy as np
import pytest
from numpy.typing import NDArray
from PyQt5 import QtCore

from labelme.shape import Shape


def _make_mask_shape(
    mask: NDArray[np.bool_], origin_x: float, origin_y: float
) -> Shape:
    shape = Shape(shape_type="mask")
    h, w = mask.shape
    shape.addPoint(QtCore.QPointF(origin_x, origin_y))
    shape.addPoint(QtCore.QPointF(origin_x + w, origin_y + h))
    shape.mask = mask
    return shape


@pytest.mark.parametrize(
    "point, expected",
    [
        ((4, 3), True),  # inside True region
        ((4, 4), True),  # last valid row/column
        ((5, 2), False),  # one pixel past right boundary
        ((2, 5), False),  # one pixel past bottom boundary
        ((5, 5), False),  # past both boundaries
    ],
)
def test_mask_contains_point(point: tuple[int, int], expected: bool) -> None:
    mask = np.ones((5, 5), dtype=bool)
    shape = _make_mask_shape(mask, origin_x=0, origin_y=0)
    assert shape.containsPoint(QtCore.QPointF(*point)) is expected
