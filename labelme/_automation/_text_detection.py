from __future__ import annotations

import json
from typing import TYPE_CHECKING

import numpy as np
from loguru import logger
from numpy.typing import NDArray

from .._shape import Shape
from ._shape_builders import MASK_REQUIRED_SHAPE_TYPES
from ._shape_builders import Detection
from ._shape_builders import assign_available_group_ids
from ._shape_builders import shapes_from_detections
from ._suppression import match_detections_to_existing_shapes
from ._suppression import suppress_detections_greedy
from ._types import AiOutputFormat

if TYPE_CHECKING:
    import osam


class MaskOutputUnavailableError(ValueError):
    pass


def propose_shapes_from_texts(
    *,
    annotations: list[osam.types.Annotation],
    texts: list[str],
    shape_type: AiOutputFormat,
    existing_shapes: list[Shape],
    iou_threshold: float,
    score_threshold: float,
    image_size: tuple[int, int] | None,
    polygon_detail: int,
    suppressed_by: str | None = None,
) -> list[Shape]:
    # suppressed_by: the label the results will take, when it isn't their
    # text; only existing Shapes with that label suppress them.
    boxes, scores, labels, masks = get_bboxes_from_texts(
        annotations=annotations, texts=texts
    )
    if masks is None and len(boxes) > 0 and shape_type in MASK_REQUIRED_SHAPE_TYPES:
        raise MaskOutputUnavailableError(f"{shape_type!r} requires model masks")

    # Use the same mask overlap as example boxes; a polygon part can cover an
    # occluded object even when its bounding box is much smaller.
    is_new = np.zeros(len(boxes), dtype=bool)
    for label, text in enumerate(texts):
        indices = np.flatnonzero(labels == label)
        candidates = [
            Detection(
                bbox=(
                    float(boxes[i, 0]),
                    float(boxes[i, 1]),
                    float(boxes[i, 2]),
                    float(boxes[i, 3]),
                ),
                mask=None if masks is None else masks[i],
            )
            for i in indices
        ]
        matches = match_detections_to_existing_shapes(
            detections=candidates,
            existing_shapes=[
                shape
                for shape in existing_shapes
                if shape.shape_type == shape_type
                and shape.label == (text if suppressed_by is None else suppressed_by)
            ],
            iou_threshold=iou_threshold,
        )
        new_ids = {id(detection) for detection in matches.new_detections}
        is_new[indices] = [id(detection) in new_ids for detection in candidates]
    boxes, scores, labels = boxes[is_new], scores[is_new], labels[is_new]
    if masks is not None:
        masks = [mask for mask, keep in zip(masks, is_new) if keep]

    boxes, scores, labels, indices = nms_bboxes(
        boxes=boxes,
        scores=scores,
        labels=labels,
        iou_threshold=iou_threshold,
        score_threshold=score_threshold,
        max_num_detections=100,
    )

    if masks is None:
        masks = [None] * len(boxes)
    else:
        masks = [masks[i] for i in indices]
    del indices

    detections: list[Detection] = []
    for box, score, label, mask in zip(boxes, scores, labels, masks):
        text = texts[label]
        detections.append(
            Detection(
                bbox=(
                    float(box[0]),
                    float(box[1]),
                    float(box[2]),
                    float(box[3]),
                ),
                mask=mask,
                label=text,
                description=json.dumps(dict(score=score.item(), text=text)),
            )
        )
    detections = suppress_detections_greedy(
        detections=detections,
        iou_threshold=iou_threshold,
    )
    shapes = shapes_from_detections(
        detections=detections,
        shape_type=shape_type,
        image_size=image_size,
        polygon_detail=polygon_detail,
    )
    assign_available_group_ids(
        shapes=shapes,
        existing_shapes=existing_shapes,
    )
    return shapes


def get_bboxes_from_texts(
    *, annotations: list[osam.types.Annotation], texts: list[str]
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[NDArray[np.bool_]] | None]:
    num_annotations: int = len(annotations)
    logger.debug("Response: num_annotations={}", num_annotations)

    boxes: NDArray[np.float32] = np.empty((num_annotations, 4), dtype=np.float32)
    scores: NDArray[np.float32] = np.empty((num_annotations,), dtype=np.float32)
    labels: NDArray[np.int32] = np.empty((num_annotations,), dtype=np.int32)
    for i, annotation in enumerate(annotations):
        if annotation.bounding_box is None:
            raise ValueError("Bounding box is missing in the annotation.")
        if annotation.text not in texts:
            raise ValueError(
                f"Unexpected text {annotation.text!r} found in the response."
            )
        boxes[i] = [
            annotation.bounding_box.xmin,
            annotation.bounding_box.ymin,
            annotation.bounding_box.xmax,
            annotation.bounding_box.ymax,
        ]
        scores[i] = annotation.score
        labels[i] = texts.index(annotation.text)

    masks: list[NDArray[np.bool_]] | None = None
    if annotations and annotations[0].mask is not None:
        masks = []
        for annotation in annotations:
            if annotation.mask is None:
                raise ValueError("Mask is missing in the annotation.")
            masks.append(annotation.mask)

    return boxes, scores, labels, masks


def nms_bboxes(
    *,
    boxes: np.ndarray,
    scores: np.ndarray,
    labels: np.ndarray,
    iou_threshold: float,
    score_threshold: float,
    max_num_detections: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    if len(boxes) == 0:
        return boxes, scores, labels, np.empty((0,), dtype=np.int32)

    num_classes: int = max(labels) + 1
    scores_of_all_classes: NDArray[np.float32] = np.zeros(
        (len(boxes), num_classes), dtype=np.float32
    )
    for i, (score, label) in enumerate(zip(scores, labels)):
        scores_of_all_classes[i, label] = score
    logger.debug(
        "Running NMS: iou_threshold={}, score_threshold={}, max_num_detections={}",
        iou_threshold,
        score_threshold,
        max_num_detections,
    )
    logger.debug(f"Input: num_boxes={len(boxes)}")
    import osam  # noqa: PLC0415 -- deferred: ~250ms off importing labelme._app

    boxes, scores, labels, indices = osam.non_maximum_suppression(
        boxes=boxes,
        scores=scores_of_all_classes,
        iou_threshold=iou_threshold,
        score_threshold=score_threshold,
        max_num_detections=max_num_detections,
    )
    logger.debug(f"Output: num_boxes={len(boxes)}")
    return boxes, scores, labels, indices
