from __future__ import annotations

import copy
import math
from fractions import Fraction
from typing import Final

import numpy as np
from numpy.typing import NDArray

from .._shape import Shape
from .._shape import mask_shape_box
from ._geometry import compute_polygon_from_circle

_HALF: Final = Fraction(1, 2)

Scale = tuple[Fraction, Fraction]
UNSCALED: Final[Scale] = (Fraction(1), Fraction(1))


def _scale_pixel_span(*, first: int, last: int, factor: Fraction) -> tuple[int, int]:
    if factor <= 1:
        return (
            math.floor((first + _HALF) * factor),
            math.floor((last + _HALF) * factor),
        )
    return (
        math.ceil(first * factor - _HALF),
        math.ceil((last + 1) * factor - _HALF) - 1,
    )


def scale_pixel_box(
    *, box: tuple[int, int, int, int], factor: Scale
) -> tuple[int, int, int, int]:
    xmin, ymin, xmax, ymax = box
    x0, x1 = _scale_pixel_span(first=xmin, last=xmax, factor=factor[0])
    y0, y1 = _scale_pixel_span(first=ymin, last=ymax, factor=factor[1])
    return x0, y0, x1, y1


def scale_bbox(
    *, bbox: tuple[float, float, float, float], factor: Scale
) -> tuple[float, float, float, float]:
    if factor == UNSCALED:
        return bbox
    xmin, ymin, xmax, ymax = bbox
    scale_x, scale_y = float(factor[0]), float(factor[1])
    return (
        xmin * scale_x,
        ymin * scale_y,
        max(xmin * scale_x, (xmax + 1) * scale_x - 1),
        max(ymin * scale_y, (ymax + 1) * scale_y - 1),
    )


def _scale_mask_axis(
    *, mask: NDArray[np.bool_], first: int, factor: Fraction, axis: int
) -> NDArray[np.bool_]:
    last = first + mask.shape[axis] - 1
    if factor <= 1:
        sent_first, sent_last = _scale_pixel_span(first=first, last=last, factor=factor)
        runs = [
            max(first, _scale_pixel_span(first=sent, last=sent, factor=1 / factor)[0])
            - first
            for sent in range(sent_first, sent_last + 1)
        ]
        return np.logical_or.reduceat(mask, runs, axis=axis)
    sent_starts = [
        _scale_pixel_span(first=source, last=source, factor=factor)[0]
        for source in range(first, last + 2)
    ]
    return np.repeat(mask, np.diff(sent_starts), axis=axis)


def scale_shape(*, shape: Shape, factor: Scale) -> Shape:
    if factor == UNSCALED:
        return shape
    scaled = copy.copy(shape)
    if shape.shape_type == "mask" and shape.mask is not None:
        box = mask_shape_box(shape=shape)
        xmin, ymin = box[:2]
        x0, y0, x1, y1 = scale_pixel_box(box=box, factor=factor)
        scaled.points = np.array([[x0, y0], [x1, y1]], dtype=np.float64)
        mask = shape.mask
        for first, axis_factor, axis in sorted(
            [(ymin, factor[1], 0), (xmin, factor[0], 1)], key=lambda step: step[1]
        ):
            mask = _scale_mask_axis(
                mask=mask, first=first, factor=axis_factor, axis=axis
            )
        scaled.mask = mask
        return scaled
    if shape.shape_type == "rectangle" and len(shape.points) == 2:  # noqa: PLR2004
        xmin, ymin, xmax, ymax = scale_bbox(
            bbox=(*shape.points.min(axis=0), *shape.points.max(axis=0)), factor=factor
        )
        scaled.points = np.array([[xmin, ymin], [xmax, ymax]], dtype=np.float64)
        return scaled
    stretch = np.asarray(factor, dtype=np.float64)
    if shape.shape_type == "circle" and len(shape.points) == 2:  # noqa: PLR2004
        center, edge = shape.points
        scaled.shape_type = "polygon"
        scaled.points = (
            compute_polygon_from_circle(
                center=center, radius=float(np.linalg.norm(edge - center)), detail=100
            )
            * stretch
        )
        return scaled
    scaled.points = shape.points * stretch
    return scaled
