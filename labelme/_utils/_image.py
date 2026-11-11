# MIT License
# Copyright (c) Kentaro Wada

from __future__ import annotations

import math
from typing import NamedTuple

import numpy as np
from numpy.typing import NDArray
from PySide6 import QtCore
from PySide6 import QtGui


def img_qt_to_arr(*, img_qt: QtGui.QImage) -> NDArray[np.uint8]:
    w, h, d = img_qt.size().width(), img_qt.size().height(), img_qt.depth()
    channels = d // 8
    # bits() spans bytesPerLine() * height; Qt aligns each scanline to a 4-byte
    # boundary, so a row may be wider than w * channels. Drop the padding.
    rows = np.frombuffer(bytes(img_qt.bits()), dtype=np.uint8).reshape(
        (h, img_qt.bytesPerLine())
    )
    return rows[:, : w * channels].reshape((h, w, channels))


def img_qt_to_rgb_arr(*, img_qt: QtGui.QImage) -> NDArray[np.uint8]:
    # The raw-memory conversion above yields BGRA on little-endian for the
    # 32-bit formats Qt loads images as; force RGB888 first (byte-order
    # defined on every platform) so callers that feed vision models get
    # true RGB.
    return img_qt_to_arr(
        img_qt=img_qt.convertToFormat(QtGui.QImage.Format.Format_RGB888)
    )


class ImageDecodeRequirement(NamedTuple):
    width: int
    height: int
    required_mb: int


def get_image_decode_requirement(*, image_data: bytes) -> ImageDecodeRequirement | None:
    buffer = QtCore.QBuffer()
    buffer.setData(image_data)
    buffer.open(QtCore.QIODevice.OpenModeFlag.ReadOnly)
    return get_reader_decode_requirement(reader=QtGui.QImageReader(buffer))


def get_reader_decode_requirement(
    *, reader: QtGui.QImageReader
) -> ImageDecodeRequirement | None:
    size = reader.size()
    if not size.isValid():
        return None
    bits_per_pixel = QtGui.QImage.toPixelFormat(
        reader.imageFormat()  # ty: ignore[no-matching-overload]
    ).bitsPerPixel()
    if bits_per_pixel <= 0:
        return None

    # Match Qt's 32-bit minimum for GUI-backed image allocations.
    required_mb = (
        size.width() * size.height() * max(bits_per_pixel, 32) / 8 / 1024 / 1024
    )
    return ImageDecodeRequirement(
        width=size.width(),
        height=size.height(),
        required_mb=math.ceil(required_mb),
    )
