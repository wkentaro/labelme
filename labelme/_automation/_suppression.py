from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Final

import numpy as np
import PIL.Image
import PIL.ImageDraw
from numpy.typing import NDArray

from .._shape import Shape
from .._shape import mask_shape_box
from ._geometry import round_bbox_to_int
from ._geometry import shape_to_xyxy_bbox
from ._scaling import UNSCALED
from ._scaling import Scale
from ._scaling import scale_pixel_box
from ._scaling import scale_shape
from ._shape_builders import Detection


# eq=False: numpy arrays don't reduce to a scalar bool, so the auto-generated
# dataclass __eq__ (which calls bool() on the result) would raise ValueError.
@dataclass(frozen=True, eq=False)
class _LocalMask:
    mask: NDArray[np.bool_] | None
    extent: tuple[int, int, int, int]
    area: int


def _box_local_mask(*, extent: tuple[int, int, int, int]) -> _LocalMask:
    xmin, ymin, xmax, ymax = extent
    return _LocalMask(
        mask=None, extent=extent, area=(xmax - xmin + 1) * (ymax - ymin + 1)
    )


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
    # Callers pass detections in priority order (highest first): the first
    # detection in each redundant cluster is kept and later ones are dropped.
    # Redundancy combines IoU with intersection-over-smaller (containment), so
    # nested masks (e.g. tree-cluster containing a single tree) deduplicate even
    # when their IoU is low.
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
    kept_masks_by_label: dict[
        str | None, list[tuple[tuple[int, int, int, int] | None, _LocalMask]]
    ] = {}
    for detection in detections:
        if detection.bbox is None:
            kept.append(detection)
            continue
        new_box = _image_box(detection=detection)
        new_local = _local_mask_from_detection(detection=detection)
        peers = kept_masks_by_label.setdefault(detection.label, [])
        if any(
            not _apart_in_image(a=new_box, b=peer_box)
            and _is_redundant_overlap(
                overlap=_compute_mask_overlap(a=new_local, b=peer),
                iou_threshold=iou_threshold,
            )
            for peer_box, peer in peers
        ):
            continue
        kept.append(detection)
        peers.append((new_box, new_local))
    return kept


def match_detections_to_existing_shapes(
    *,
    detections: list[Detection],
    existing_shapes: list[Shape],
    iou_threshold: float = 0.5,
    shrink: Scale = UNSCALED,
) -> _ExistingShapeMatchResult:
    if not detections:
        return _ExistingShapeMatchResult(new_detections=[], matching_shapes=[])
    existing_shape_extents = [
        (shape, extent, _scaled_extent(shape=shape, extent=extent, factor=shrink))
        for shape in existing_shapes
        if (extent := _shape_extent(shape=shape)) is not None
    ]
    detection_extents = [
        (index, round_bbox_to_int(bbox=detection.bbox), _image_box(detection=detection))
        for index, detection in enumerate(detections)
        if detection.bbox is not None
    ]
    detection_masks: dict[int, _LocalMask] = {}
    best_matches: dict[int, tuple[Shape, float]] = {}
    for shape, extent, scaled_extent in existing_shape_extents:
        nearby = [
            index
            for index, detection_extent, image_box in detection_extents
            if _extents_intersect(a=detection_extent, b=scaled_extent)
            and not _apart_in_image(a=image_box, b=extent)
        ]
        if not nearby:
            continue
        for index in nearby:
            if index not in detection_masks:
                detection_masks[index] = _local_mask_from_detection(
                    detection=_as_saved(detection=detections[index], shrink=shrink)
                )
        overlaps = _overlaps_with_shape(
            shape=scale_shape(shape=shape, factor=shrink),
            detection_masks=[detection_masks[index] for index in nearby],
        )
        for index, overlap in zip(nearby, overlaps, strict=True):
            if (
                _is_redundant_overlap(overlap=overlap, iou_threshold=iou_threshold)
                and overlap.iou > best_matches.get(index, (None, 0.0))[1]
            ):
                best_matches[index] = (shape, overlap.iou)

    kept: list[Detection] = []
    matching_shapes: list[Shape] = []
    for index, detection in enumerate(detections):
        if index not in best_matches:
            kept.append(detection)
            continue
        matching_shape, _ = best_matches[index]
        if all(shape is not matching_shape for shape in matching_shapes):
            matching_shapes.append(matching_shape)
    return _ExistingShapeMatchResult(
        new_detections=kept,
        matching_shapes=matching_shapes,
    )


def _as_saved(*, detection: Detection, shrink: Scale) -> Detection:
    source = detection.at_image_size
    if source is None or shrink == UNSCALED or source.annotation.mask_scores is None:
        return detection
    return dataclasses.replace(detection, mask=source.pooled_mask(factor=shrink))


def _overlaps_with_shape(
    *,
    shape: Shape,
    detection_masks: list[_LocalMask],
) -> list[_MaskOverlap]:
    if (extent := _shape_extent(shape=shape)) is None:
        return [_MaskOverlap(iou=0.0, containment=0.0)] * len(detection_masks)
    existing_mask = _local_mask_from_shape(shape=shape, extent=extent)
    return [_compute_mask_overlap(a=mask, b=existing_mask) for mask in detection_masks]


def _is_redundant_overlap(
    *,
    overlap: _MaskOverlap,
    iou_threshold: float,
) -> bool:
    # Containment (intersection-over-smaller) catches nested masks whose IoU
    # is too low for the IoU check (e.g. tree-cluster swallowing a single tree).
    CONTAINMENT_THRESHOLD: Final[float] = 0.85
    return overlap.iou > 0 and (
        overlap.iou >= iou_threshold or overlap.containment >= CONTAINMENT_THRESHOLD
    )


def _compute_mask_overlap(*, a: _LocalMask, b: _LocalMask) -> _MaskOverlap:
    intersection = _compute_mask_intersection_area(a=a, b=b)
    if intersection == 0:
        return _MaskOverlap(iou=0.0, containment=0.0)
    iou = intersection / (a.area + b.area - intersection)
    containment = intersection / min(a.area, b.area)
    return _MaskOverlap(iou=iou, containment=containment)


def _image_box(*, detection: Detection) -> tuple[int, int, int, int] | None:
    if detection.at_image_size is None:
        return None
    return detection.at_image_size.bbox


def _apart_in_image(
    *, a: tuple[int, int, int, int] | None, b: tuple[int, int, int, int] | None
) -> bool:
    return a is not None and b is not None and not _extents_intersect(a=a, b=b)


def _local_mask_from_detection(*, detection: Detection) -> _LocalMask:
    assert detection.bbox is not None
    extent = round_bbox_to_int(bbox=detection.bbox)
    if detection.mask is None:
        return _box_local_mask(extent=extent)
    xmin, ymin, xmax, ymax = extent
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
        extent=extent,
        area=int(np.count_nonzero(detection.mask)),
    )


def _shape_extent(*, shape: Shape) -> tuple[int, int, int, int] | None:
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
    if shape.shape_type == "mask" and shape.mask is not None:
        return mask_shape_box(shape=shape)
    return round_bbox_to_int(bbox=bbox)


def _scaled_extent(
    *, shape: Shape, extent: tuple[int, int, int, int], factor: Scale
) -> tuple[int, int, int, int]:
    if shape.shape_type == "mask":
        return scale_pixel_box(box=extent, factor=factor)
    scaled = _shape_extent(shape=scale_shape(shape=shape, factor=factor))
    assert scaled is not None
    return scaled


def _extents_intersect(
    *, a: tuple[int, int, int, int], b: tuple[int, int, int, int]
) -> bool:
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


def _local_mask_from_shape(
    *, shape: Shape, extent: tuple[int, int, int, int]
) -> _LocalMask:
    xmin, ymin, xmax, ymax = extent
    if shape.shape_type == "mask" and shape.mask is not None:
        mask = shape.mask.astype(np.bool_, copy=False)
    elif shape.shape_type in ("rectangle", "mask"):
        return _box_local_mask(extent=extent)
    else:
        mask = rasterize_shape(
            shape=shape,
            xmin=xmin,
            ymin=ymin,
            width=xmax - xmin + 1,
            height=ymax - ymin + 1,
        )
    return _LocalMask(mask=mask, extent=extent, area=int(np.count_nonzero(mask)))


def rasterize_shape(
    *, shape: Shape, xmin: int, ymin: int, width: int, height: int
) -> NDArray[np.bool_]:
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
    xmin = max(a.extent[0], b.extent[0])
    ymin = max(a.extent[1], b.extent[1])
    xmax = min(a.extent[2], b.extent[2])
    ymax = min(a.extent[3], b.extent[3])
    if xmax < xmin or ymax < ymin:
        return 0
    windows = [
        local.mask[
            ymin - local.extent[1] : ymax - local.extent[1] + 1,
            xmin - local.extent[0] : xmax - local.extent[0] + 1,
        ]
        for local in (a, b)
        if local.mask is not None
    ]
    if not windows:
        return (xmax - xmin + 1) * (ymax - ymin + 1)
    if len(windows) == 1:
        return int(np.count_nonzero(windows[0]))
    return int(np.count_nonzero(windows[0] & windows[1]))
