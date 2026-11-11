from __future__ import annotations

import numpy as np
from PySide6 import QtGui

from labelme._utils import _image as image_module


def test_img_qt_to_arr_returns_bgra_pixels() -> None:
    img_qt = QtGui.QImage(4, 3, QtGui.QImage.Format.Format_RGB32)
    img_qt.fill(QtGui.QColor(0, 0, 0))
    img_qt.setPixelColor(0, 0, QtGui.QColor(10, 20, 30))
    img_qt.setPixelColor(3, 2, QtGui.QColor(40, 50, 60))

    arr = image_module.img_qt_to_arr(img_qt=img_qt)

    assert arr.dtype == np.uint8
    assert arr.shape == (3, 4, 4)
    # Format_RGB32 is stored as BGRA on little-endian, with a filled alpha byte.
    np.testing.assert_array_equal(arr[0, 0], [30, 20, 10, 255])
    np.testing.assert_array_equal(arr[2, 3], [60, 50, 40, 255])


def test_img_qt_to_rgb_arr_returns_rgb_pixels() -> None:
    img_qt = QtGui.QImage(4, 3, QtGui.QImage.Format.Format_RGB32)
    img_qt.fill(QtGui.QColor(0, 0, 0))
    img_qt.setPixelColor(0, 0, QtGui.QColor(10, 20, 30))
    img_qt.setPixelColor(3, 2, QtGui.QColor(40, 50, 60))

    arr = image_module.img_qt_to_rgb_arr(img_qt=img_qt)

    assert arr.dtype == np.uint8
    assert arr.shape == (3, 4, 3)
    np.testing.assert_array_equal(arr[0, 0], [10, 20, 30])
    np.testing.assert_array_equal(arr[2, 3], [40, 50, 60])


def test_img_qt_to_arr_strips_scanline_padding() -> None:
    # width 3 * 3 channels = 9 bytes/row, but Qt pads each scanline to a 4-byte
    # boundary, so bytesPerLine() is 12; the padding must not leak into the array.
    img_qt = QtGui.QImage(3, 2, QtGui.QImage.Format.Format_RGB888)
    assert img_qt.bytesPerLine() > 3 * 3
    columns = [
        QtGui.QColor(255, 0, 0),
        QtGui.QColor(0, 255, 0),
        QtGui.QColor(0, 0, 255),
    ]
    for y in range(2):
        for x, color in enumerate(columns):
            img_qt.setPixelColor(x, y, color)

    arr = image_module.img_qt_to_arr(img_qt=img_qt)

    assert arr.shape == (2, 3, 3)
    expected = np.array([[[255, 0, 0], [0, 255, 0], [0, 0, 255]]] * 2, dtype=np.uint8)
    np.testing.assert_array_equal(arr, expected)


def test_img_qt_to_arr_copies_source_buffer() -> None:
    # The array must own its data, not alias the QImage's buffer, so it stays
    # valid after the source is overwritten or freed.
    img_qt = QtGui.QImage(2, 2, QtGui.QImage.Format.Format_RGB32)
    img_qt.fill(QtGui.QColor(10, 20, 30))

    arr = image_module.img_qt_to_arr(img_qt=img_qt)
    img_qt.fill(QtGui.QColor(200, 210, 220))

    np.testing.assert_array_equal(arr[0, 0], [30, 20, 10, 255])
