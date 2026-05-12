from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

import numpy as np
import PIL.Image
import PIL.ImageDraw
from numpy.typing import NDArray
from PyQt5 import QtCore

from labelme._shape import Shape

from ._shape_builders import Detection


# eq=False because numpy arrays raise on element-wise equality; dataclass
# auto-equality would propagate that into __eq__/__hash__.
@dataclass(frozen=True, eq=False)
class _LocalMask:
    mask: NDArray[np.bool_]
    origin_xy: tuple[int, int]


def shape_to_xyxy_bbox(*, shape: Shape) -> NDArray[np.float32] | None:
    if shape.shape_type == "circle":
        if len(shape.points) != 2:
            return None
        center, edge = shape.points
        radius = _radius_from_circle_points(center=center, edge=edge)
        return np.array(
            [
                center.x() - radius,
                center.y() - radius,
                center.x() + radius,
                center.y() + radius,
            ],
            dtype=np.float32,
        )
    minimum_points_by_shape_type = {
        "rectangle": 2,
        "mask": 2,
        "polygon": 3,
        "oriented_rectangle": 4,
    }
    if shape.shape_type in minimum_points_by_shape_type:
        if len(shape.points) < minimum_points_by_shape_type[shape.shape_type]:
            return None
        points = np.array([[p.x(), p.y()] for p in shape.points])
        xmin, ymin = points.min(axis=0)
        xmax, ymax = points.max(axis=0)
        return np.array([xmin, ymin, xmax, ymax], dtype=np.float32)
    return None


def suppress_detections_overlapping_existing_shapes(
    *,
    detections: list[Detection],
    existing_shapes: list[Shape],
) -> list[Detection]:
    if not detections:
        return []

    existing_masks = _local_masks_from_shapes(shapes=existing_shapes)
    if not existing_masks:
        return list(detections)

    kept: list[Detection] = []
    for detection in detections:
        if not _detection_overlaps_any(
            detection=detection, existing_masks=existing_masks
        ):
            kept.append(detection)
    return kept


def _detection_overlaps_any(
    *,
    detection: Detection,
    existing_masks: list[_LocalMask],
) -> bool:
    DUPLICATE_IOU_THRESHOLD: Final[float] = 0.5
    if detection.bbox is None:
        return False
    new_bbox = np.array(detection.bbox, dtype=np.float32)
    xmin, ymin, _, _ = _round_bbox_to_int(bbox=new_bbox)
    new_origin = (xmin, ymin)
    new_mask = detection.mask
    if new_mask is None:
        new_mask = _filled_mask_for_bbox(bbox=new_bbox)
    return any(
        _mask_iou(
            mask_a=new_mask,
            origin_a=new_origin,
            mask_b=other.mask,
            origin_b=other.origin_xy,
        )
        >= DUPLICATE_IOU_THRESHOLD
        for other in existing_masks
    )


def _local_masks_from_shapes(*, shapes: list[Shape]) -> list[_LocalMask]:
    local_masks: list[_LocalMask] = []
    for shape in shapes:
        bbox = shape_to_xyxy_bbox(shape=shape)
        if bbox is None:
            continue
        xmin, ymin, _, _ = _round_bbox_to_int(bbox=bbox)
        local_masks.append(
            _LocalMask(
                mask=_shape_to_local_mask(shape=shape, bbox=bbox),
                origin_xy=(xmin, ymin),
            )
        )
    return local_masks


def _shape_to_local_mask(
    *, shape: Shape, bbox: NDArray[np.float32]
) -> NDArray[np.bool_]:
    xmin, ymin, xmax, ymax = _round_bbox_to_int(bbox=bbox)
    width = xmax - xmin + 1
    height = ymax - ymin + 1
    if shape.shape_type == "mask":
        return _mask_shape_local_mask(shape=shape, width=width, height=height)
    if shape.shape_type == "rectangle":
        return np.ones((height, width), dtype=np.bool_)
    if shape.shape_type == "circle":
        return _circle_shape_local_mask(
            shape=shape, xmin=xmin, ymin=ymin, width=width, height=height
        )
    if shape.shape_type in ("polygon", "oriented_rectangle"):
        return _polygon_shape_local_mask(
            shape=shape, xmin=xmin, ymin=ymin, width=width, height=height
        )
    raise ValueError(f"Unsupported shape_type: {shape.shape_type!r}")


def _mask_shape_local_mask(
    *, shape: Shape, width: int, height: int
) -> NDArray[np.bool_]:
    if shape.mask is None:
        return np.ones((height, width), dtype=np.bool_)
    return shape.mask.astype(np.bool_, copy=False)


def _circle_shape_local_mask(
    *, shape: Shape, xmin: int, ymin: int, width: int, height: int
) -> NDArray[np.bool_]:
    center, edge = shape.points
    cx_local = center.x() - xmin
    cy_local = center.y() - ymin
    radius = _radius_from_circle_points(center=center, edge=edge)
    image = PIL.Image.new("L", (width, height), 0)
    draw = PIL.ImageDraw.Draw(image)
    draw.ellipse(
        (
            cx_local - radius,
            cy_local - radius,
            cx_local + radius,
            cy_local + radius,
        ),
        fill=1,
    )
    return np.asarray(image, dtype=np.bool_)


def _polygon_shape_local_mask(
    *, shape: Shape, xmin: int, ymin: int, width: int, height: int
) -> NDArray[np.bool_]:
    image = PIL.Image.new("L", (width, height), 0)
    draw = PIL.ImageDraw.Draw(image)
    points_local = [(p.x() - xmin, p.y() - ymin) for p in shape.points]
    draw.polygon(points_local, fill=1)
    return np.asarray(image, dtype=np.bool_)


def _radius_from_circle_points(
    *, center: QtCore.QPointF, edge: QtCore.QPointF
) -> float:
    return math.sqrt((edge.x() - center.x()) ** 2 + (edge.y() - center.y()) ** 2)


def _round_bbox_to_int(*, bbox: NDArray[np.float32]) -> tuple[int, int, int, int]:
    return (
        int(round(bbox[0])),
        int(round(bbox[1])),
        int(round(bbox[2])),
        int(round(bbox[3])),
    )


def _filled_mask_for_bbox(*, bbox: NDArray[np.float32]) -> NDArray[np.bool_]:
    xmin, ymin, xmax, ymax = _round_bbox_to_int(bbox=bbox)
    return np.ones((ymax - ymin + 1, xmax - xmin + 1), dtype=np.bool_)


def _mask_iou(
    *,
    mask_a: NDArray[np.bool_],
    origin_a: tuple[int, int],
    mask_b: NDArray[np.bool_],
    origin_b: tuple[int, int],
) -> float:
    a_xmin, a_ymin = origin_a
    b_xmin, b_ymin = origin_b
    a_h, a_w = mask_a.shape
    b_h, b_w = mask_b.shape

    union_xmin = min(a_xmin, b_xmin)
    union_ymin = min(a_ymin, b_ymin)
    union_xmax = max(a_xmin + a_w, b_xmin + b_w)
    union_ymax = max(a_ymin + a_h, b_ymin + b_h)
    canvas_h = union_ymax - union_ymin
    canvas_w = union_xmax - union_xmin

    canvas_a = np.zeros((canvas_h, canvas_w), dtype=np.bool_)
    canvas_b = np.zeros((canvas_h, canvas_w), dtype=np.bool_)
    _place_mask(
        canvas=canvas_a, mask=mask_a, top=a_ymin - union_ymin, left=a_xmin - union_xmin
    )
    _place_mask(
        canvas=canvas_b, mask=mask_b, top=b_ymin - union_ymin, left=b_xmin - union_xmin
    )

    intersection = int(np.count_nonzero(canvas_a & canvas_b))
    if intersection == 0:
        return 0.0
    union = int(np.count_nonzero(canvas_a | canvas_b))
    return intersection / union


def _place_mask(
    *,
    canvas: NDArray[np.bool_],
    mask: NDArray[np.bool_],
    top: int,
    left: int,
) -> None:
    h, w = mask.shape
    canvas[top : top + h, left : left + w] |= mask
