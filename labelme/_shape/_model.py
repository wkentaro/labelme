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

    def move_vertex(self, *, i: int, pos: npt.ArrayLike) -> None:
        self.points[i] = np.asarray(pos, dtype=np.float64).reshape(2)

    def translate(self, *, offset: npt.ArrayLike) -> None:
        self.points = self.points + np.asarray(offset, dtype=np.float64).reshape(2)

    def copy(self) -> Shape:
        return copy.deepcopy(self)
