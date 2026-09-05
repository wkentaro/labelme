from __future__ import annotations

import json
import time
from typing import Final

import numpy as np
import osam
from loguru import logger
from numpy.typing import NDArray

from .._shape import Shape
from ._geometry import shape_to_xyxy_bbox
from ._osam_session import OsamSession
from ._shape_builders import MASK_REQUIRED_SHAPE_TYPES
from ._shape_builders import Detection
from ._shape_builders import assign_available_group_ids
from ._shape_builders import shapes_from_detections
from ._suppression import suppress_detections_greedy
from ._types import AiOutputFormat


class MaskOutputUnavailableError(ValueError):
    pass


def propose_shapes_from_texts(
    *,
    session: OsamSession,
    image: np.ndarray,
    image_id: str,
    texts: list[str],
    shape_type: AiOutputFormat,
    existing_shapes: list[Shape],
    iou_threshold: float,
    score_threshold: float,
    image_size: tuple[int, int] | None,
    polygon_detail: int,
) -> list[Shape]:
    boxes, scores, labels, masks = get_bboxes_from_texts(
        session=session, image=image, image_id=image_id, texts=texts
    )
    if masks is None and len(boxes) > 0 and shape_type in MASK_REQUIRED_SHAPE_TYPES:
        raise MaskOutputUnavailableError(f"{shape_type!r} requires model masks")

    # Existing Shapes outrank model scores so overlapping predictions disappear
    # without returning the existing Shapes as new proposals.
    SCORE_FOR_EXISTING_SHAPE: Final[float] = 1.01
    for shape in existing_shapes:
        if shape.shape_type != shape_type or shape.label not in texts:
            continue
        shape_bbox = shape_to_xyxy_bbox(shape=shape)
        if shape_bbox is None:
            continue
        boxes = np.r_[boxes, [shape_bbox]]
        scores = np.r_[scores, [SCORE_FOR_EXISTING_SHAPE]]
        labels = np.r_[labels, [texts.index(shape.label)]]

    boxes, scores, labels, indices = nms_bboxes(
        boxes=boxes,
        scores=scores,
        labels=labels,
        iou_threshold=iou_threshold,
        score_threshold=score_threshold,
        max_num_detections=100,
    )

    is_new = scores != SCORE_FOR_EXISTING_SHAPE
    boxes = boxes[is_new]
    scores = scores[is_new]
    labels = labels[is_new]
    indices = indices[is_new]

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
    *, session: OsamSession, image: np.ndarray, image_id: str, texts: list[str]
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[NDArray[np.bool_]] | None]:
    logger.debug(
        f"Requesting with model={session.model_name!r}, "
        f"image={(image.shape, image.dtype)}, texts={texts!r}"
    )
    t_start: float = time.time()
    response: osam.types.GenerateResponse = session.run(
        image=image,
        image_id=image_id,
        texts=texts,
    )

    num_annotations: int = len(response.annotations)
    logger.debug(
        f"Response: num_annotations={num_annotations}, "
        f"elapsed_time={time.time() - t_start:.3f} [s]"
    )

    boxes: NDArray[np.float32] = np.empty((num_annotations, 4), dtype=np.float32)
    scores: NDArray[np.float32] = np.empty((num_annotations,), dtype=np.float32)
    labels: NDArray[np.int32] = np.empty((num_annotations,), dtype=np.int32)
    for i, annotation in enumerate(response.annotations):
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
    if response.annotations and response.annotations[0].mask is not None:
        masks = []
        for annotation in response.annotations:
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
    boxes, scores, labels, indices = osam.apis.non_maximum_suppression(
        boxes=boxes,
        scores=scores_of_all_classes,
        iou_threshold=iou_threshold,
        score_threshold=score_threshold,
        max_num_detections=max_num_detections,
    )
    logger.debug(f"Output: num_boxes={len(boxes)}")
    return boxes, scores, labels, indices
