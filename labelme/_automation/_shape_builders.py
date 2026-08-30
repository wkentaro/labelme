from __future__ import annotations

import typing
from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import ArrayLike
from numpy.typing import NDArray

from .._shape import MIN_POLYGON_POINT_COUNT
from .._shape import Shape
from ._geometry import Circle
from ._geometry import _round_bbox_to_int
from ._geometry import compute_circle_from_mask
from ._geometry import compute_oriented_rectangle_from_mask
from ._geometry import compute_polygons_from_mask
from ._types import AiOutputFormat

_DEFAULT_POLYGON_DETAIL: Final[int] = 80


@dataclass
class Detection:
    bbox: tuple[float, float, float, float] | None = None
    mask: NDArray[np.bool_] | None = None
    label: str | None = None
    description: str | None = None
    score: float = 0.0


def _build_shape(
    *,
    shape_type: AiOutputFormat,
    points: ArrayLike,
    mask: NDArray[np.bool_] | None,
    label: str | None,
    description: str | None,
) -> Shape:
    return Shape(
        label=label,
        shape_type=shape_type,
        mask=mask,
        description=description,
        points=np.asarray(points, dtype=np.float64),
        closed=True,
    )


def _build_shapes_from_detection(
    *,
    detection: Detection,
    shape_type: AiOutputFormat,
    image_size: tuple[int, int] | None,
    polygon_detail: int,
) -> list[Shape]:
    if shape_type == "rectangle":
        if detection.bbox is None:
            return []
        xmin, ymin, xmax, ymax = detection.bbox
        return [
            _build_shape(
                shape_type="rectangle",
                points=[[xmin, ymin], [xmax, ymax]],
                mask=None,
                label=detection.label,
                description=detection.description,
            )
        ]
    if shape_type == "polygon":
        if detection.mask is None:
            return []
        polygons = compute_polygons_from_mask(
            mask=detection.mask,
            detail=polygon_detail,
        )
        if detection.bbox is not None:
            offset = np.array([detection.bbox[0], detection.bbox[1]], dtype=np.float32)
            polygons = [polygon + offset for polygon in polygons]
        return [
            _build_shape(
                shape_type="polygon",
                points=polygon,
                mask=None,
                label=detection.label,
                description=detection.description,
            )
            for polygon in polygons
            if len(polygon) >= MIN_POLYGON_POINT_COUNT
        ]
    if shape_type == "mask":
        if detection.bbox is None or detection.mask is None:
            return []
        if not detection.mask.any():
            return []
        xmin, ymin, xmax, ymax = _round_bbox_to_int(bbox=detection.bbox)
        return [
            _build_shape(
                shape_type="mask",
                points=[[xmin, ymin], [xmax, ymax]],
                mask=detection.mask,
                label=detection.label,
                description=detection.description,
            )
        ]
    if shape_type == "circle":
        circle = _circle_for_detection(detection=detection)
        if circle is None:
            return []
        return [
            _build_shape(
                shape_type="circle",
                points=[
                    [circle.cx, circle.cy],
                    [circle.cx + circle.radius, circle.cy],
                ],
                mask=None,
                label=detection.label,
                description=detection.description,
            )
        ]
    if shape_type == "oriented_rectangle":
        corners = _oriented_rectangle_for_detection(detection=detection)
        if corners is not None and image_size is not None:
            corners = _fit_oriented_rectangle_to_image(
                corners=corners,
                image_size=image_size,
            )
        if corners is None:
            return []
        return [
            _build_shape(
                shape_type="oriented_rectangle",
                points=corners,
                mask=None,
                label=detection.label,
                description=detection.description,
            )
        ]
    raise ValueError(f"Unsupported shape_type: {shape_type!r}")


def _oriented_rectangle_for_detection(
    *,
    detection: Detection,
) -> NDArray[np.float32] | None:
    if detection.mask is not None:
        corners = compute_oriented_rectangle_from_mask(mask=detection.mask)
        if corners is not None:
            offset_x, offset_y = (
                detection.bbox[:2] if detection.bbox is not None else (0.0, 0.0)
            )
            return corners + np.array([offset_x, offset_y], dtype=np.float32)
    if detection.bbox is not None:
        xmin, ymin, xmax, ymax = detection.bbox
        return np.array(
            [[xmin, ymin], [xmax, ymin], [xmax, ymax], [xmin, ymax]],
            dtype=np.float32,
        )
    return None


def _fit_oriented_rectangle_to_image(
    *,
    corners: NDArray[np.float32],
    image_size: tuple[int, int],
) -> NDArray[np.float32] | None:
    size = np.asarray(image_size, dtype=np.float32)
    if (corners >= 0).all() and (corners <= size).all():
        return corners
    # Clipping individual vertices would produce a quadrilateral that the
    # oriented-rectangle editor cannot preserve.
    lower = np.clip(corners.min(axis=0), 0, size)
    upper = np.clip(corners.max(axis=0), 0, size)
    if (upper <= lower).any():
        return None
    return np.array(
        [lower, [upper[0], lower[1]], upper, [lower[0], upper[1]]],
        dtype=np.float32,
    )


def _circle_for_detection(*, detection: Detection) -> Circle | None:
    if detection.mask is not None:
        circle = compute_circle_from_mask(mask=detection.mask)
        if circle is not None:
            offset_x, offset_y = (
                detection.bbox[:2] if detection.bbox is not None else (0.0, 0.0)
            )
            return Circle(
                cx=circle.cx + offset_x,
                cy=circle.cy + offset_y,
                radius=circle.radius,
            )
    if detection.bbox is not None:
        # Inscribed in bbox when no usable mask is available.
        xmin, ymin, xmax, ymax = detection.bbox
        radius = min(xmax - xmin, ymax - ymin) / 2
        if radius > 0:
            return Circle(cx=(xmin + xmax) / 2, cy=(ymin + ymax) / 2, radius=radius)
    return None


# Output formats that drop a bbox-only detection. Deriving this from the same
# conversion path keeps the runtime warning condition from drifting.
MASK_REQUIRED_SHAPE_TYPES: Final[frozenset[AiOutputFormat]] = frozenset(
    shape_type
    for shape_type in typing.get_args(AiOutputFormat)
    if not _build_shapes_from_detection(
        detection=Detection(bbox=(0, 0, 1, 1), mask=None),
        shape_type=shape_type,
        image_size=None,
        polygon_detail=_DEFAULT_POLYGON_DETAIL,
    )
)


def shapes_from_detections(
    *,
    detections: list[Detection],
    shape_type: AiOutputFormat,
    image_size: tuple[int, int] | None = None,
    polygon_detail: int = _DEFAULT_POLYGON_DETAIL,
) -> list[Shape]:
    shapes: list[Shape] = []
    next_group_id = 1
    for detection in detections:
        detection_shapes = _build_shapes_from_detection(
            detection=detection,
            shape_type=shape_type,
            image_size=image_size,
            polygon_detail=polygon_detail,
        )
        if len(detection_shapes) > 1:
            for shape in detection_shapes:
                shape.group_id = next_group_id
            next_group_id += 1
        shapes.extend(detection_shapes)
    return shapes


def assign_available_group_ids(
    *, shapes: list[Shape], existing_shapes: list[Shape]
) -> None:
    next_group_id = (
        max(
            (shape.group_id for shape in existing_shapes if shape.group_id is not None),
            default=0,
        )
        + 1
    )
    replacements: dict[int, int] = {}
    for shape in shapes:
        if shape.group_id is None:
            continue
        if shape.group_id not in replacements:
            replacements[shape.group_id] = next_group_id
            next_group_id += 1
        shape.group_id = replacements[shape.group_id]
