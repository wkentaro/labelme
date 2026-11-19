from __future__ import annotations

import dataclasses
import math
import typing
from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import ArrayLike
from numpy.typing import NDArray

from .._shape import MIN_POLYGON_POINT_COUNT
from .._shape import Shape
from ._geometry import Circle
from ._geometry import compute_circle_from_mask
from ._geometry import compute_oriented_rectangle_from_mask
from ._geometry import compute_polygons_from_mask
from ._geometry import round_bbox_to_int
from ._scaling import AtImageSize
from ._types import AiOutputFormat

_DEFAULT_POLYGON_DETAIL: Final[int] = 60


@dataclass
class Detection:
    bbox: tuple[float, float, float, float] | None = None
    mask: NDArray[np.bool_] | None = None
    label: str | None = None
    description: str | None = None
    score: float = 0.0
    at_image_size: AtImageSize | None = None


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
        outline_mask, step = _outline_mask(mask=detection.mask)
        origin = np.array(_mask_origin(detection=detection), dtype=np.float32)
        polygons = [
            np.minimum(polygon * step, detection.mask.shape[::-1]) + origin
            for polygon in compute_polygons_from_mask(
                mask=outline_mask,
                detail=polygon_detail,
                pixel_size=step,
            )
        ]
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
        xmin, ymin, xmax, ymax = round_bbox_to_int(bbox=detection.bbox)
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
        corners, step = _oriented_rectangle_for_detection(detection=detection)
        if corners is not None and image_size is not None:
            corners = _fit_oriented_rectangle_to_image(
                corners=corners,
                image_size=image_size,
                max_shift=step - 1,
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


def _mask_origin(*, detection: Detection) -> tuple[int, int]:
    if detection.bbox is None:
        return 0, 0
    xmin, ymin, _, _ = round_bbox_to_int(bbox=detection.bbox)
    return xmin, ymin


def _oriented_rectangle_for_detection(
    *,
    detection: Detection,
) -> tuple[NDArray[np.float32] | None, int]:
    if detection.mask is not None:
        outline_mask, step = _outline_mask(mask=detection.mask)
        corners = compute_oriented_rectangle_from_mask(mask=outline_mask)
        if corners is None and step > 1:
            corners = compute_oriented_rectangle_from_mask(mask=detection.mask)
            step = 1
        if corners is not None:
            origin = np.array(_mask_origin(detection=detection), dtype=np.float32)
            return corners * step + origin, step
    if detection.bbox is not None:
        xmin, ymin, xmax, ymax = detection.bbox
        return np.array(
            [[xmin, ymin], [xmax, ymin], [xmax, ymax], [xmin, ymax]],
            dtype=np.float32,
        ), 1
    return None, 1


def _fit_oriented_rectangle_to_image(
    *,
    corners: NDArray[np.float32],
    image_size: tuple[int, int],
    max_shift: float,
) -> NDArray[np.float32] | None:
    size = np.asarray(image_size, dtype=np.float32)
    shift = np.maximum(-corners.min(axis=0), 0) - np.maximum(
        corners.max(axis=0) - size, 0
    )
    if (np.abs(shift) <= max_shift).all():
        corners = corners + shift
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
        outline_mask, step = _outline_mask(mask=detection.mask)
        circle = compute_circle_from_mask(mask=outline_mask)
        if circle is not None:
            offset_x, offset_y = _mask_origin(detection=detection)
            return Circle(
                cx=circle.cx * step + offset_x,
                cy=circle.cy * step + offset_y,
                radius=circle.radius * step,
            )
    if detection.bbox is not None:
        # Inscribed in bbox when no usable mask is available.
        xmin, ymin, xmax, ymax = detection.bbox
        radius = min(xmax - xmin, ymax - ymin) / 2
        if radius > 0:
            return Circle(cx=(xmin + xmax) / 2, cy=(ymin + ymax) / 2, radius=radius)
    return None


def _outline_mask(*, mask: NDArray[np.bool_]) -> tuple[NDArray[np.bool_], int]:
    MAX_PIXELS: Final = 1 << 20
    step = math.ceil(math.sqrt(mask.size / MAX_PIXELS))
    if step == 1:
        return np.ascontiguousarray(mask), step
    rows = np.logical_or.reduceat(mask, np.arange(0, mask.shape[0], step), axis=0)
    return np.logical_or.reduceat(rows, np.arange(0, mask.shape[1], step), axis=1), step


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
    built: dict[int, list[Shape]] | None = None,
) -> list[Shape]:
    shapes: list[Shape] = []
    next_group_id = 1
    memo = {} if built is None else built
    for detection in detections:
        source = detection.at_image_size
        key = None if source is None else id(source.annotation)
        if key in memo:
            detection_shapes = memo[key]
        else:
            if source is not None:
                detection = dataclasses.replace(
                    detection,
                    bbox=source.bbox,
                    mask=None if shape_type == "rectangle" else source.mask(),
                )
            detection_shapes = _build_shapes_from_detection(
                detection=detection,
                shape_type=shape_type,
                image_size=image_size,
                polygon_detail=polygon_detail,
            )
            if key is not None:
                memo[key] = detection_shapes
        if len(detection_shapes) > 1:
            for shape in detection_shapes:
                shape.group_id = next_group_id
            next_group_id += 1
        shapes.extend(detection_shapes)
        del detection
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
