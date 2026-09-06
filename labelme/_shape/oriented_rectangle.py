from __future__ import annotations

from typing import Final

import numpy as np
import numpy.typing as npt

from .model import ORIENTED_RECTANGLE_POINT_COUNT
from .model import Shape


def _is_full_oriented_rectangle(shape: Shape, /) -> bool:
    return (
        shape.shape_type == "oriented_rectangle"
        and len(shape.points) == ORIENTED_RECTANGLE_POINT_COUNT
    )


def _get_rotation_handles(
    points: npt.NDArray[np.float64], /
) -> npt.NDArray[np.float64]:
    # Handle i sits at the midpoint of the edge from points[i - 1] to points[i].
    return (points + np.roll(points, shift=1, axis=0)) / 2


def get_rotation_handle(*, shape: Shape, index: int) -> npt.NDArray[np.float64]:
    if not _is_full_oriented_rectangle(shape):
        raise ValueError(
            "Rotation handles are only defined for 4-point oriented rectangles, "
            f"got shape_type={shape.shape_type!r}, len(points)={len(shape.points)}"
        )
    return _get_rotation_handles(shape.points)[index]


def oriented_rectangle_center(*, shape: Shape) -> npt.NDArray[np.float64]:
    if shape.shape_type != "oriented_rectangle":
        raise ValueError(
            f"Center is only defined for oriented rectangles, got {shape.shape_type!r}"
        )
    if len(shape.points) != ORIENTED_RECTANGLE_POINT_COUNT:
        raise ValueError(
            f"Oriented rectangle center requires 4 points, got {len(shape.points)}"
        )
    # Opposite corners of a parallelogram share a midpoint.
    return (shape.points[0] + shape.points[2]) / 2


def _make_rotation_matrix(angle: float, /) -> npt.NDArray[np.float64]:
    cos_a, sin_a = np.cos(angle), np.sin(angle)
    return np.array([[cos_a, -sin_a], [sin_a, cos_a]])


def _rotate_points(
    points: npt.NDArray[np.floating], /, *, angle: float
) -> npt.NDArray[np.floating]:
    return points @ _make_rotation_matrix(angle).T


def rotate(
    *,
    shape: Shape,
    center: npt.NDArray[np.float64],
    angle: float,
    source_points: npt.NDArray[np.float64] | None = None,
) -> None:
    if shape.shape_type != "oriented_rectangle":
        raise ValueError(
            "Shape rotation is only supported for oriented rectangles, "
            f"got {shape.shape_type!r}"
        )
    points = shape.points if source_points is None else source_points
    if (
        len(points) != ORIENTED_RECTANGLE_POINT_COUNT
        or len(shape.points) != ORIENTED_RECTANGLE_POINT_COUNT
    ):
        raise ValueError(
            "Shape rotation requires 4 points, got "
            f"len(source_points)={len(points)}, len(shape.points)={len(shape.points)}"
        )
    shape.points = _rotate_points(points - center, angle=angle) + center


# The arrow is drawn nose-first along +x, then rotated to the rectangle's
# first-edge direction and recentered; only its aspect (half-length, and how
# far the barbs sit behind the tip) is a tunable constant.
_ARROW_HALF_LENGTH: Final[float] = 5.0
_ARROW_BARB_SETBACK: Final[float] = 0.22
_ARROW_TEMPLATE: Final[npt.NDArray[np.float64]] = _ARROW_HALF_LENGTH * np.array(
    [
        [_ARROW_BARB_SETBACK, -0.5],
        [1.0, 0.0],
        [_ARROW_BARB_SETBACK, 0.5],
        [-1.0, 0.0],
    ]
)


def oriented_rectangle_arrow_points(*, shape: Shape) -> npt.NDArray[np.float64]:
    edge = shape.points[1] - shape.points[0]
    angle = float(np.arctan2(edge[1], edge[0]))
    center = oriented_rectangle_center(shape=shape)
    return _rotate_points(_ARROW_TEMPLATE, angle=angle) + center
