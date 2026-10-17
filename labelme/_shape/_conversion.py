from __future__ import annotations

import typing

import numpy as np

from ._model import MIN_POLYGON_POINT_COUNT
from ._model import RECTANGLE_POINT_COUNT
from ._model import Shape
from ._model import ShapeType

POLYGON_FAMILY_SHAPE_TYPES: typing.Final[tuple[ShapeType, ...]] = (
    "polygon",
    "rectangle",
    "linestrip",
)


def get_valid_conversion_targets(shape: Shape, /) -> set[ShapeType]:
    if shape.locked:
        return set()

    if shape.shape_type == "rectangle":
        if len(shape.points) == RECTANGLE_POINT_COUNT:
            return {"polygon"}
        return set()

    if shape.shape_type == "polygon":
        if len(shape.points) >= MIN_POLYGON_POINT_COUNT:
            return {"rectangle", "linestrip"}
        return set()

    if shape.shape_type == "linestrip":
        if len(shape.points) >= MIN_POLYGON_POINT_COUNT:
            return {"polygon"}
        return set()

    return set()


def get_intersection_conversion_targets(
    shapes: typing.Iterable[Shape], /
) -> set[ShapeType]:
    shape_list = list(shapes)
    if not shape_list:
        return set()

    first_targets = get_valid_conversion_targets(shape_list[0])
    if not first_targets:
        return set()

    intersection = set(first_targets)
    for s in shape_list[1:]:
        intersection &= get_valid_conversion_targets(s)
        if not intersection:
            break

    return intersection


def convert_shape_geometry(*, shape: Shape, target_type: ShapeType) -> Shape:
    valid_targets = get_valid_conversion_targets(shape)
    if target_type not in valid_targets:
        raise ValueError(
            f"Cannot convert shape of type {shape.shape_type!r} with "
            f"{len(shape.points)} points to {target_type!r}"
        )

    converted = shape.copy()

    if target_type == "polygon":
        if shape.shape_type == "rectangle":
            p0, p1 = shape.points[0], shape.points[1]
            x0, y0 = float(p0[0]), float(p0[1])
            x1, y1 = float(p1[0]), float(p1[1])
            converted.points = np.array(
                [[x0, y0], [x1, y0], [x1, y1], [x0, y1]], dtype=np.float64
            )
            converted.point_labels = np.ones(4, dtype=np.int_)
            converted.shape_type = "polygon"
            converted.closed = True
            return converted

        if shape.shape_type == "linestrip":
            converted.shape_type = "polygon"
            converted.closed = True
            return converted

    if target_type == "rectangle":
        if shape.shape_type == "polygon":
            min_x = float(np.min(shape.points[:, 0]))
            min_y = float(np.min(shape.points[:, 1]))
            max_x = float(np.max(shape.points[:, 0]))
            max_y = float(np.max(shape.points[:, 1]))
            converted.points = np.array(
                [[min_x, min_y], [max_x, max_y]], dtype=np.float64
            )
            converted.point_labels = np.ones(2, dtype=np.int_)
            converted.shape_type = "rectangle"
            converted.closed = True
            return converted

    if target_type == "linestrip":
        if shape.shape_type == "polygon":
            converted.shape_type = "linestrip"
            converted.closed = True
            return converted

    raise ValueError(
        f"Unexpected conversion from {shape.shape_type!r} to {target_type!r}"
    )
