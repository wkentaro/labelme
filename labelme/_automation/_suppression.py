from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import PIL.Image
import PIL.ImageDraw
from numpy.typing import NDArray

from .._shape import Shape
from ._geometry import shape_to_xyxy_bbox
from ._shape_builders import Detection


# eq=False: numpy arrays don't reduce to a scalar bool, so the auto-generated
# dataclass __eq__ (which calls bool() on the result) would raise ValueError.
@dataclass(frozen=True, eq=False)
class _LocalMask:
    mask: NDArray[np.bool_]
    origin_xy: tuple[int, int]
    area: int


@dataclass(frozen=True)
class _ExistingShapeMatchResult:
    new_detections: list[Detection]
    matching_shapes: list[Shape]


@dataclass(frozen=True)
class _MaskOverlap:
    iou: float
    containment: float


def suppress_detections_greedy(
    *,
    detections: list[Detection],
    iou_threshold: float,
) -> list[Detection]:
    """Callers must pass detections in priority order (highest first); the first
    detection in each redundant cluster is kept and later ones are dropped.

    Redundancy combines IoU with intersection-over-smaller (containment), so
    nested masks (e.g. tree-cluster containing a single tree) deduplicate even
    when their IoU is low.
    """
    if not detections:
        return []

    # Mixing bbox-only and mask detections would silently let bbox-only peers
    # (treated as fully-opaque rectangles) suppress overlapping mask detections
    # via containment. Require homogeneous input until a caller needs otherwise.
    mask_presence = {d.mask is not None for d in detections if d.bbox is not None}
    if len(mask_presence) > 1:
        raise ValueError(
            "detections must be homogeneous: either all have masks or none do"
        )

    kept: list[Detection] = []
    kept_masks_by_label: dict[str | None, list[_LocalMask]] = {}
    for detection in detections:
        if detection.bbox is None:
            kept.append(detection)
            continue
        new_local = _local_mask_from_detection(detection=detection)
        peers = kept_masks_by_label.setdefault(detection.label, [])
        if any(
            _is_redundant_overlap(
                overlap=_compute_mask_overlap(a=new_local, b=peer),
                iou_threshold=iou_threshold,
            )
            for peer in peers
        ):
            continue
        kept.append(detection)
        peers.append(new_local)
    return kept


def match_detections_to_existing_shapes(
    *,
    detections: list[Detection],
    existing_shapes: list[Shape],
) -> _ExistingShapeMatchResult:
    OVERLAP_IOU_THRESHOLD: Final[float] = 0.5
    if not detections:
        return _ExistingShapeMatchResult(new_detections=[], matching_shapes=[])
    existing_shape_masks = [
        (shape, local_mask)
        for shape in existing_shapes
        if (local_mask := _local_mask_from_shape(shape=shape)) is not None
    ]
    if not existing_shape_masks:
        return _ExistingShapeMatchResult(
            new_detections=detections[:],
            matching_shapes=[],
        )

    kept: list[Detection] = []
    matching_shapes: list[Shape] = []
    for detection in detections:
        if detection.bbox is None:
            kept.append(detection)
            continue
        new_local = _local_mask_from_detection(detection=detection)
        matches: list[tuple[Shape, _MaskOverlap]] = []
        for shape, existing_mask in existing_shape_masks:
            overlap = _compute_mask_overlap(a=new_local, b=existing_mask)
            if _is_redundant_overlap(
                overlap=overlap,
                iou_threshold=OVERLAP_IOU_THRESHOLD,
            ):
                matches.append((shape, overlap))
        if not matches:
            kept.append(detection)
            continue
        matching_shape, _ = max(matches, key=lambda match: match[1].iou)
        if all(shape is not matching_shape for shape in matching_shapes):
            matching_shapes.append(matching_shape)
    return _ExistingShapeMatchResult(
        new_detections=kept,
        matching_shapes=matching_shapes,
    )


def _is_redundant_overlap(
    *,
    overlap: _MaskOverlap,
    iou_threshold: float,
) -> bool:
    # Containment (intersection-over-smaller) catches nested masks whose IoU
    # is too low for the IoU check (e.g. tree-cluster swallowing a single tree).
    CONTAINMENT_THRESHOLD: Final[float] = 0.85
    return overlap.iou >= iou_threshold or overlap.containment >= CONTAINMENT_THRESHOLD


def _compute_mask_overlap(*, a: _LocalMask, b: _LocalMask) -> _MaskOverlap:
    intersection = _compute_mask_intersection_area(a=a, b=b)
    if intersection == 0:
        return _MaskOverlap(iou=0.0, containment=0.0)
    iou = intersection / (a.area + b.area - intersection)
    containment = intersection / min(a.area, b.area)
    return _MaskOverlap(iou=iou, containment=containment)


def _local_mask_from_detection(*, detection: Detection) -> _LocalMask:
    xmin, ymin, xmax, ymax = np.array(detection.bbox).round().astype(int).tolist()
    if detection.mask is None:
        h, w = ymax - ymin + 1, xmax - xmin + 1
        mask = np.ones((h, w), dtype=np.bool_)
        return _LocalMask(mask=mask, origin_xy=(xmin, ymin), area=h * w)
    # Mask geometry below assumes mask covers exactly the bbox-derived extent
    # (matching the OSAM Annotation contract). Reject inconsistent shapes loudly
    # so a future non-OSAM caller doesn't silently produce wrong IoU values.
    expected_shape = (ymax - ymin + 1, xmax - xmin + 1)
    if detection.mask.shape != expected_shape:
        raise ValueError(
            f"mask shape {detection.mask.shape} does not match "
            f"bbox-derived extent {expected_shape}"
        )
    return _LocalMask(
        mask=detection.mask,
        origin_xy=(xmin, ymin),
        area=int(np.count_nonzero(detection.mask)),
    )


def _local_mask_from_shape(*, shape: Shape) -> _LocalMask | None:
    # Skip non-bbox shapes (point/line/linestrip) so callers can pass
    # canvas.shapes unfiltered.
    if shape.shape_type not in (
        "rectangle",
        "polygon",
        "circle",
        "oriented_rectangle",
        "mask",
    ):
        return None
    bbox = shape_to_xyxy_bbox(shape=shape)
    if bbox is None:
        return None
    xmin, ymin, xmax, ymax = (int(round(v)) for v in bbox.tolist())
    width = xmax - xmin + 1
    height = ymax - ymin + 1
    mask = _rasterize_shape(
        shape=shape, xmin=xmin, ymin=ymin, width=width, height=height
    )
    return _LocalMask(
        mask=mask,
        origin_xy=(xmin, ymin),
        area=int(np.count_nonzero(mask)),
    )


def _rasterize_shape(
    *, shape: Shape, xmin: int, ymin: int, width: int, height: int
) -> NDArray[np.bool_]:
    if shape.shape_type == "mask":
        if shape.mask is None:
            return np.ones((height, width), dtype=np.bool_)
        # Same bbox-extent contract as detection masks.
        if shape.mask.shape != (height, width):
            raise ValueError(
                f"mask shape {shape.mask.shape} does not match "
                f"bbox-derived extent {(height, width)}"
            )
        return shape.mask.astype(np.bool_, copy=False)
    if shape.shape_type == "rectangle":
        return np.ones((height, width), dtype=np.bool_)
    if shape.shape_type == "circle":
        center, edge = shape.points
        cx_local = center[0] - xmin
        cy_local = center[1] - ymin
        radius = float(np.linalg.norm(edge - center))
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
    if shape.shape_type in ("polygon", "oriented_rectangle"):
        image = PIL.Image.new("L", (width, height), 0)
        draw = PIL.ImageDraw.Draw(image)
        points_local = [tuple(point) for point in (shape.points - [xmin, ymin])]
        draw.polygon(points_local, fill=1)
        return np.asarray(image, dtype=np.bool_)
    raise ValueError(f"Unsupported shape_type: {shape.shape_type!r}")


def _compute_mask_intersection_area(*, a: _LocalMask, b: _LocalMask) -> int:
    # bbox endpoints are inclusive pixel coords (mask width = xmax - xmin + 1),
    # so xmin + w is the exclusive x-upper-bound used for clipping.
    a_xmin, a_ymin = a.origin_xy
    b_xmin, b_ymin = b.origin_xy
    a_h, a_w = a.mask.shape
    b_h, b_w = b.mask.shape

    inter_xmin = max(a_xmin, b_xmin)
    inter_ymin = max(a_ymin, b_ymin)
    inter_xmax = min(a_xmin + a_w, b_xmin + b_w)
    inter_ymax = min(a_ymin + a_h, b_ymin + b_h)
    if inter_xmax <= inter_xmin or inter_ymax <= inter_ymin:
        return 0

    sub_a = a.mask[
        inter_ymin - a_ymin : inter_ymax - a_ymin,
        inter_xmin - a_xmin : inter_xmax - a_xmin,
    ]
    sub_b = b.mask[
        inter_ymin - b_ymin : inter_ymax - b_ymin,
        inter_xmin - b_xmin : inter_xmax - b_xmin,
    ]
    return int(np.count_nonzero(sub_a & sub_b))
