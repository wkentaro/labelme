import json
import time

import numpy as np
import osam
from loguru import logger
from numpy.typing import NDArray
from PyQt5 import QtCore

from labelme.shape import Shape

from ._osam_session import OsamSession


def get_bboxes_from_texts(
    session: OsamSession, image: np.ndarray, image_id: str, texts: list[str]
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
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
    labels: NDArray[np.float32] = np.empty((num_annotations,), dtype=np.int32)
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

    return boxes, scores, labels


def nms_bboxes(
    boxes: np.ndarray,
    scores: np.ndarray,
    labels: np.ndarray,
    iou_threshold: float,
    score_threshold: float,
    max_num_detections: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if len(boxes) == 0:
        return boxes, scores, labels

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
    boxes, scores, labels = osam.apis.non_maximum_suppression(
        boxes=boxes,
        scores=scores_of_all_classes,
        iou_threshold=iou_threshold,
        score_threshold=score_threshold,
        max_num_detections=max_num_detections,
    )
    logger.debug(f"Output: num_boxes={len(boxes)}")
    return boxes, scores, labels


def get_shapes_from_bboxes(
    boxes: np.ndarray, scores: np.ndarray, labels: np.ndarray, texts: list[str]
) -> list[Shape]:
    shapes: list[Shape] = []
    for box, score, label in zip(boxes.tolist(), scores.tolist(), labels.tolist()):
        text: str = texts[label]
        shape = Shape(
            label=text,
            shape_type="rectangle",
            description=json.dumps(dict(score=score, text=text)),
        )
        xmin, ymin, xmax, ymax = box
        shape.addPoint(QtCore.QPointF(xmin, ymin))
        shape.addPoint(QtCore.QPointF(xmax, ymax))
        shapes.append(shape)
    return shapes
