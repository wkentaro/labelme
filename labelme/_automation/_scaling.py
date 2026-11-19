from __future__ import annotations

import copy
import math

import numpy as np
from numpy.typing import NDArray

from .._shape import Shape
from ._geometry import compute_polygon_from_circle


def _scale_pixel_span(*, first: int, last: int, factor: float) -> tuple[int, int]:
    start, end = round(first * factor), round((last + 1) * factor) - 1
    if start > end:
        start = end = math.floor((first + last + 1) / 2 * factor)
    return start, end


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


def _grid_sources(
    *, first: int, start: int, end: int, length: int, factor: float
) -> NDArray[np.intp]:
    sources = np.floor((np.arange(start, end + 1) + 0.5) / factor).astype(np.intp)
    return np.clip(sources - first, 0, length - 1)


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
        rows = _grid_sources(
            first=ymin, start=y0, end=y1, length=height, factor=factor[1]
        )
        columns = _grid_sources(
            first=xmin, start=x0, end=x1, length=width, factor=factor[0]
        )
        scaled.mask = shape.mask[np.ix_(rows, columns)]
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
