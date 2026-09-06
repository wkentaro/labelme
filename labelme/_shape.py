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

# Shape types whose points form an open-or-closed polyline that a user can
# extend or shrink one vertex at a time.
POLYLINE_SHAPE_TYPES: Final[tuple[ShapeType, ...]] = ("polygon", "linestrip")

# Point counts each shape type's finished geometry is defined by. A shape
# still being drawn holds fewer points than these until it is finalized.
CIRCLE_POINT_COUNT: Final = 2
LINE_POINT_COUNT: Final = 2
RECTANGLE_POINT_COUNT: Final = 2
ORIENTED_RECTANGLE_POINT_COUNT: Final = 4
MIN_LINESTRIP_POINT_COUNT: Final = 2
MIN_POLYGON_POINT_COUNT: Final = 3


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
        self.points = np.array(self.points, dtype=np.float64).reshape(-1, 2)
        self.point_labels = np.array(self.point_labels, dtype=np.int_).reshape(-1)
        if len(self.point_labels) == 0 and len(self.points) > 0:
            self.point_labels = np.ones(len(self.points), dtype=np.int_)

    # -- topology: growing/shrinking the point list ------------------------

    def can_add_point(self) -> bool:
        return self.shape_type in POLYLINE_SHAPE_TYPES

    def can_remove_point(self) -> bool:
        if not self.can_add_point():
            return False
        floor = {
            "polygon": MIN_POLYGON_POINT_COUNT,
            "linestrip": MIN_LINESTRIP_POINT_COUNT,
        }[self.shape_type]
        return len(self.points) > floor

    def insert_point(self, *, i: int, point: npt.ArrayLike, label: int = 1) -> None:
        if not self.can_add_point():
            logger.warning(
                "Cannot add point to: shape_type={!r}, len(points)={:d}",
                self.shape_type,
                len(self.points),
            )
            return
        self.points = np.insert(
            self.points, i, np.asarray(point, dtype=np.float64).reshape(2), axis=0
        )
        self.point_labels = np.insert(self.point_labels, i, label)

    def remove_point(self, *, i: int) -> None:
        if not self.can_remove_point():
            logger.warning(
                "Cannot remove point from: shape_type={!r}, len(points)={:d}",
                self.shape_type,
                len(self.points),
            )
            return
        self.points = np.delete(self.points, i, axis=0)
        self.point_labels = np.delete(self.point_labels, i)

    # -- moving geometry -----------------------------------------------------

    def move_vertex(self, *, i: int, pos: npt.ArrayLike) -> None:
        self.points[i] = np.asarray(pos, dtype=np.float64).reshape(2)

    def translate(self, *, offset: npt.ArrayLike) -> None:
        self.points = self.points + np.asarray(offset, dtype=np.float64).reshape(2)

    def copy(self) -> Shape:
        return copy.deepcopy(self)


# ---------------------------------------------------------------------------
# Hit-testing geometry
#
# Each function below answers "which index (if any) of this shape lies
# within `image_epsilon` of `point`?" for a different part of a shape: its
# vertices, its edges, or (for oriented rectangles) its rotation handles.
# They report the closest match, breaking ties toward the lower index.
# ---------------------------------------------------------------------------


def _closest_index_within(
    *, distances: npt.NDArray[np.float64], epsilon: float
) -> int | None:
    closest = int(np.argmin(distances))
    return closest if distances[closest] <= epsilon else None


def nearest_vertex_index(
    *,
    shape: Shape,
    point: npt.NDArray[np.float64],
    image_epsilon: float,
) -> int | None:
    # A mask's bbox corners are derived from its bitmap, and a point shape's
    # single point *is* the shape, not a draggable vertex; neither exposes one.
    if shape.shape_type in ("mask", "point") or len(shape.points) == 0:
        return None
    distances = np.linalg.norm(shape.points - point, axis=1)
    return _closest_index_within(distances=distances, epsilon=image_epsilon)


def nearest_edge_index(
    *,
    shape: Shape,
    point: npt.NDArray[np.float64],
    image_epsilon: float,
) -> int | None:
    if len(shape.points) == 0:
        return None
    # Edge i runs from points[i - 1] to points[i] (so edge 0 is the segment
    # that closes a polygon from its last point back to its first).
    edge_starts = np.roll(shape.points, shift=1, axis=0)
    edge_vectors = shape.points - edge_starts
    squared_lengths = np.einsum("ij,ij->i", edge_vectors, edge_vectors)
    # A repeated point yields a zero-length edge; substitute 1 as the divisor
    # so its (irrelevant) projection stays finite instead of NaN.
    safe_lengths = np.where(squared_lengths == 0, 1.0, squared_lengths)
    projection_t = np.clip(
        np.einsum("ij,ij->i", point - edge_starts, edge_vectors) / safe_lengths,
        0.0,
        1.0,
    )
    closest_points = edge_starts + projection_t[:, None] * edge_vectors
    distances = np.linalg.norm(point - closest_points, axis=1)
    if shape.shape_type == "linestrip":
        # Edge 0 above is the wrap-around segment np.roll manufactures from the
        # last point back to the first. A linestrip is open, so that segment
        # is never drawn and must never be picked as a hit.
        distances[0] = np.inf
    return _closest_index_within(distances=distances, epsilon=image_epsilon)


def nearest_rotation_point_index(
    *,
    shape: Shape,
    point: npt.NDArray[np.float64],
    image_epsilon: float,
) -> int | None:
    if not _is_full_oriented_rectangle(shape):
        return None
    distances = np.linalg.norm(_rotation_handles(shape.points) - point, axis=1)
    return _closest_index_within(distances=distances, epsilon=image_epsilon)


# ---------------------------------------------------------------------------
# Oriented-rectangle geometry: rotation handles, center, and the orientation
# arrow drawn through it.
# ---------------------------------------------------------------------------


def _is_full_oriented_rectangle(shape: Shape, /) -> bool:
    return (
        shape.shape_type == "oriented_rectangle"
        and len(shape.points) == ORIENTED_RECTANGLE_POINT_COUNT
    )


def _rotation_handles(points: npt.NDArray[np.float64], /) -> npt.NDArray[np.float64]:
    # Handle i sits at the midpoint of the edge from points[i - 1] to points[i].
    return (points + np.roll(points, shift=1, axis=0)) / 2


def get_rotation_handle(*, shape: Shape, index: int) -> npt.NDArray[np.float64]:
    if not _is_full_oriented_rectangle(shape):
        raise ValueError(
            "Rotation handles are only defined for 4-point oriented rectangles, "
            f"got shape_type={shape.shape_type!r}, len(points)={len(shape.points)}"
        )
    return _rotation_handles(shape.points)[index]


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


def _rotation_matrix(angle: float, /) -> npt.NDArray[np.float64]:
    cos_a, sin_a = np.cos(angle), np.sin(angle)
    return np.array([[cos_a, -sin_a], [sin_a, cos_a]])


def _rotated(
    points: npt.NDArray[np.floating], /, *, angle: float
) -> npt.NDArray[np.floating]:
    return points @ _rotation_matrix(angle).T


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
    shape.points = _rotated(points - center, angle=angle) + center


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
    return _rotated(_ARROW_TEMPLATE, angle=angle) + center
