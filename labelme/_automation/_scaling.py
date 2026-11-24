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
    scaled_first, scaled_end = pixels_centered_in(
        low=first, high=last + 1, factor=factor
    )
    return scaled_first, scaled_end - 1


def pixels_centered_in(*, low: float, high: float, factor: Fraction) -> tuple[int, int]:
    return math.ceil(low * factor - _HALF), math.ceil(high * factor - _HALF)


def _first_pixels_centered_from(
    *, first: int, count: int, factor: Fraction
) -> tuple[int, NDArray[np.int64]]:
    # ceil(edge * factor - 1/2) for count edges from first, as the first of them
    # and each one's steps from it, so int64 never holds a far-off pixel.
    whole, rest = divmod(
        factor.denominator - 2 * first * factor.numerator, 2 * factor.denominator
    )
    steps = 2 * factor.numerator * np.arange(count, dtype=np.int64)
    return -whole, -((rest - steps) // (2 * factor.denominator))


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
    if factor == 1:
        return mask
    last = first + mask.shape[axis] - 1
    if factor <= 1:
        sent_first, sent_last = _scale_pixel_span(first=first, last=last, factor=factor)
        start, steps = _first_pixels_centered_from(
            first=sent_first, count=sent_last - sent_first + 1, factor=1 / factor
        )
        return np.logical_or.reduceat(
            mask, np.maximum(steps + (start - first), 0), axis=axis
        )
    _, steps = _first_pixels_centered_from(
        first=first, count=last - first + 2, factor=factor
    )
    return np.repeat(mask, np.diff(steps), axis=axis)


def scale_mask(
    *, mask: NDArray[np.bool_], origin: tuple[int, int], factor: Scale
) -> tuple[NDArray[np.bool_], tuple[int, int, int, int]]:
    xmin, ymin = origin
    height, width = mask.shape
    box = scale_pixel_box(
        box=(xmin, ymin, xmin + width - 1, ymin + height - 1), factor=factor
    )
    for first, axis_factor, axis in sorted(
        [(ymin, factor[1], 0), (xmin, factor[0], 1)], key=lambda step: step[1]
    ):
        mask = _scale_mask_axis(mask=mask, first=first, factor=axis_factor, axis=axis)
    return mask, box


def scale_shape(*, shape: Shape, factor: Scale) -> Shape:
    if factor == UNSCALED:
        return shape
    scaled = copy.copy(shape)
    if shape.shape_type == "mask" and shape.mask is not None:
        scaled.mask, (x0, y0, x1, y1) = scale_mask(
            mask=shape.mask, origin=mask_shape_box(shape=shape)[:2], factor=factor
        )
        scaled.points = np.array([[x0, y0], [x1, y1]], dtype=np.float64)
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
