from __future__ import annotations

import copy
import dataclasses
import typing
from typing import Any
from typing import Final
from typing import Literal
from typing import TypeAlias

import numpy as np
import numpy.typing as npt
from loguru import logger

ShapeType: TypeAlias = Literal[
    "polygon",
    "rectangle",
    "oriented_rectangle",
    "point",
    "line",
    "circle",
    "linestrip",
    "points",
    "mask",
]

POLYLINE_SHAPE_TYPES: Final[tuple[ShapeType, ...]] = ("polygon", "linestrip")


@dataclasses.dataclass(eq=False)
class Shape:
    label: str | None = None
    group_id: int | None = None
    shape_type: ShapeType = "polygon"
    flags: dict[str, bool] | None = None
    description: str | None = None
    mask: npt.NDArray[np.bool_] | None = None
    points: npt.NDArray[np.float64] = dataclasses.field(
        default_factory=lambda: np.empty((0, 2), dtype=np.float64)
    )
    point_labels: npt.NDArray[np.int_] = dataclasses.field(
        default_factory=lambda: np.empty((0,), dtype=np.int_)
    )
    other_data: dict[str, Any] = dataclasses.field(default_factory=dict)
    closed: bool = False
    visible: bool = True

    def __post_init__(self) -> None:
        if self.shape_type not in typing.get_args(ShapeType):
            raise ValueError(f"Unexpected shape_type: {self.shape_type}")
        self.points = np.asarray(self.points, dtype=np.float64).reshape(-1, 2)
        self.point_labels = np.asarray(self.point_labels, dtype=np.int_).reshape(-1)
        if len(self.point_labels) == 0 and len(self.points) > 0:
            self.point_labels = np.ones(len(self.points), dtype=np.int_)

    def can_add_point(self) -> bool:
        return self.shape_type in POLYLINE_SHAPE_TYPES

    def insert_point(self, i: int, point: npt.ArrayLike, label: int = 1) -> None:
        point = np.asarray(point, dtype=np.float64).reshape(2)
        self.points = np.insert(self.points, i, point, axis=0)
        self.point_labels = np.insert(self.point_labels, i, label)

    def can_remove_point(self) -> bool:
        if not self.can_add_point():
            return False
        if self.shape_type == "polygon" and len(self.points) <= 3:
            return False
        if self.shape_type == "linestrip" and len(self.points) <= 2:
            return False
        return True

    def remove_point(self, i: int) -> None:
        if not self.can_remove_point():
            logger.warning(
                "Cannot remove point from: shape_type=%r, len(points)=%d",
                self.shape_type,
                len(self.points),
            )
            return
        self.points = np.delete(self.points, i, axis=0)
        self.point_labels = np.delete(self.point_labels, i)

    def move_vertex(self, i: int, pos: npt.ArrayLike) -> None:
        self.points[i] = np.asarray(pos, dtype=np.float64).reshape(2)

    def translate(self, offset: npt.ArrayLike) -> None:
        self.points = self.points + np.asarray(offset, dtype=np.float64).reshape(2)

    def copy(self) -> Shape:
        return copy.deepcopy(self)


def nearest_vertex_index(
    *,
    shape: Shape,
    point: npt.NDArray[np.float64],
    scale: float,
    epsilon: float,
) -> int | None:
    if shape.shape_type == "mask" or len(shape.points) == 0:
        return None
    distances = np.linalg.norm((shape.points - point) * scale, axis=1)
    nearest = int(np.argmin(distances))
    if distances[nearest] > epsilon:
        return None
    return nearest


def nearest_edge_index(
    *,
    shape: Shape,
    point: npt.NDArray[np.float64],
    scale: float,
    epsilon: float,
) -> int | None:
    if len(shape.points) == 0:
        return None
    scaled_point = point * scale
    scaled_points = shape.points * scale
    starts = np.roll(scaled_points, 1, axis=0)
    segments = scaled_points - starts
    length_squared = (segments * segments).sum(axis=1)
    t = np.clip(
        ((scaled_point - starts) * segments).sum(axis=1)
        / np.where(length_squared == 0, 1.0, length_squared),
        0.0,
        1.0,
    )
    projections = starts + t[:, None] * segments
    distances = np.linalg.norm(scaled_point - projections, axis=1)
    nearest = int(np.argmin(distances))
    if distances[nearest] > epsilon:
        return None
    return nearest


def nearest_rotation_point_index(
    *,
    shape: Shape,
    point: npt.NDArray[np.float64],
    scale: float,
    epsilon: float,
) -> int | None:
    if shape.shape_type != "oriented_rectangle" or len(shape.points) != 4:
        return None
    handles = (shape.points + np.roll(shape.points, 1, axis=0)) / 2
    distances = np.linalg.norm((handles - point) * scale, axis=1)
    nearest = int(np.argmin(distances))
    if distances[nearest] > epsilon:
        return None
    return nearest


def get_rotation_handle(*, shape: Shape, index: int) -> npt.NDArray[np.float64]:
    if shape.shape_type != "oriented_rectangle" or len(shape.points) != 4:
        raise ValueError(
            "Rotation handles are only defined for 4-point oriented rectangles, "
            f"got shape_type={shape.shape_type!r}, len(points)={len(shape.points)}"
        )
    return (shape.points[index] + shape.points[index - 1]) / 2


def oriented_rectangle_center(*, shape: Shape) -> npt.NDArray[np.float64]:
    if shape.shape_type != "oriented_rectangle":
        raise ValueError(
            f"Center is only defined for oriented rectangles, got {shape.shape_type!r}"
        )
    if len(shape.points) != 4:
        raise ValueError(
            f"Oriented rectangle center requires 4 points, got {len(shape.points)}"
        )
    return (shape.points[0] + shape.points[2]) / 2


_ARROW_HEAD_BACK_OFFSET: Final[float] = 0.22
_ARROW_HALF_LENGTH: Final[float] = 5.0
_ORIENTED_RECTANGLE_ARROW_TEMPLATE: Final[npt.NDArray[np.float64]] = (
    np.array(
        [
            [_ARROW_HEAD_BACK_OFFSET, -0.5],
            [1.0, 0.0],
            [_ARROW_HEAD_BACK_OFFSET, 0.5],
            [-1.0, 0.0],
        ]
    )
    * _ARROW_HALF_LENGTH
)


def oriented_rectangle_arrow_points(*, shape: Shape) -> npt.NDArray[np.float64]:
    center = oriented_rectangle_center(shape=shape)
    direction = shape.points[1] - shape.points[0]
    angle = float(np.arctan2(direction[1], direction[0]))
    return (
        _rotate_points_around_origin(
            points=_ORIENTED_RECTANGLE_ARROW_TEMPLATE, angle=angle
        )
        + center
    )


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
    if len(points) != 4 or len(shape.points) != 4:
        raise ValueError(
            "Shape rotation requires 4 points, got "
            f"len(source_points)={len(points)}, len(shape.points)={len(shape.points)}"
        )
    rotated = _rotate_points_around_origin(points=points - center, angle=angle) + center
    shape.points = rotated


def _rotate_points_around_origin(
    *,
    points: npt.NDArray[np.floating],
    angle: float,
) -> npt.NDArray[np.floating]:
    cos_a = np.cos(angle)
    sin_a = np.sin(angle)
    rotation = np.array([[cos_a, -sin_a], [sin_a, cos_a]])
    return points @ rotation.T
