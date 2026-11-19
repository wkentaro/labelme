from __future__ import annotations

import copy
import math
from typing import Final

import numpy as np
from numpy.typing import NDArray

from .._shape import Shape
from ._geometry import compute_polygon_from_circle

_GRID_EDGE: Final[float] = 1e-9


def _scale_pixel_span(*, first: int, last: int, factor: float) -> tuple[int, int]:
    if factor <= 1:
        return (
            math.floor((first + 0.5) * factor + _GRID_EDGE),
            math.floor((last + 0.5) * factor + _GRID_EDGE),
        )
    return (
        math.ceil(first * factor - 0.5 - _GRID_EDGE),
        math.ceil((last + 1) * factor - 0.5 - _GRID_EDGE) - 1,
    )


def scale_pixel_box(
    *, box: tuple[int, int, int, int], factor: tuple[float, float]
) -> tuple[int, int, int, int]:
    xmin, ymin, xmax, ymax = box
    x0, x1 = _scale_pixel_span(first=xmin, last=xmax, factor=factor[0])
    y0, y1 = _scale_pixel_span(first=ymin, last=ymax, factor=factor[1])
    return x0, y0, x1, y1


def scale_bbox(
    *, bbox: tuple[float, float, float, float], factor: tuple[float, float]
) -> tuple[float, float, float, float]:
    if factor == (1.0, 1.0):
        return bbox
    xmin, ymin, xmax, ymax = bbox
    scale_x, scale_y = factor
    return (
        xmin * scale_x,
        ymin * scale_y,
        max(xmin * scale_x, (xmax + 1) * scale_x - 1),
        max(ymin * scale_y, (ymax + 1) * scale_y - 1),
    )


def _scale_mask_axis(
    mask: NDArray[np.bool_],
    *,
    first: int,
    start: int,
    end: int,
    factor: float,
    axis: int,
) -> NDArray[np.bool_]:
    length = mask.shape[axis]
    if factor <= 1:
        sent = np.floor((np.arange(first, first + length) + 0.5) * factor + _GRID_EDGE)
        return np.logical_or.reduceat(
            mask, np.flatnonzero(np.diff(sent, prepend=sent[0] - 1)), axis=axis
        )
    sources = np.floor((np.arange(start, end + 1) + 0.5) / factor + _GRID_EDGE)
    return np.take(
        mask, np.clip(sources.astype(np.intp) - first, 0, length - 1), axis=axis
    )


def scale_shape(*, shape: Shape, factor: tuple[float, float]) -> Shape:
    if factor == (1.0, 1.0):
        return shape
    scaled = copy.copy(shape)
    if shape.shape_type == "mask" and shape.mask is not None:
        xmin, ymin = np.round(shape.points.min(axis=0)).astype(int)
        height, width = shape.mask.shape
        x0, y0, x1, y1 = scale_pixel_box(
            box=(xmin, ymin, xmin + width - 1, ymin + height - 1), factor=factor
        )
        scaled.points = np.array([[x0, y0], [x1, y1]], dtype=np.float64)
        rows = _scale_mask_axis(
            shape.mask, first=ymin, start=y0, end=y1, factor=factor[1], axis=0
        )
        scaled.mask = _scale_mask_axis(
            rows, first=xmin, start=x0, end=x1, factor=factor[0], axis=1
        )
        return scaled
    if shape.shape_type == "rectangle" and len(shape.points) == 2:  # noqa: PLR2004
        xmin, ymin, xmax, ymax = scale_bbox(
            bbox=(*shape.points.min(axis=0), *shape.points.max(axis=0)), factor=factor
        )
        scaled.points = np.array([[xmin, ymin], [xmax, ymax]], dtype=np.float64)
        return scaled
    if shape.shape_type == "circle" and len(shape.points) == 2:  # noqa: PLR2004
        center, edge = shape.points
        scaled.shape_type = "polygon"
        scaled.points = compute_polygon_from_circle(
            center=center, radius=float(np.linalg.norm(edge - center)), detail=100
        ) * np.asarray(factor)
        return scaled
    scaled.points = shape.points * np.asarray(factor)
    return scaled
