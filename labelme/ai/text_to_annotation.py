import json
import time

import numpy as np
# import osam

from labelme.logger import logger


def get_rectangles_from_texts(
    model: str, image: np.ndarray, texts: list[str]
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    request = None
    logger.debug(
        f"Requesting with model={model!r}, image={(image.shape, image.dtype)}, "
        f"prompt={request.prompt!r}"
    )
    t_start = time.time()
    response = None

    num_annotations = len(response.annotations)
    logger.debug(
        f"Response: num_annotations={num_annotations}, "
        f"elapsed_time={time.time() - t_start:.3f} [s]"
    )

    boxes: np.ndarray = np.empty((num_annotations, 4), dtype=np.float32)
    scores: np.ndarray = np.empty((num_annotations,), dtype=np.float32)
    labels: np.ndarray = np.empty((num_annotations,), dtype=np.int32)
    for i, annotation in enumerate(response.annotations):
        boxes[i] = [
            annotation.bounding_box.xmin,
            annotation.bounding_box.ymin,
            annotation.bounding_box.xmax,
            annotation.bounding_box.ymax,
        ]
        scores[i] = annotation.score
        labels[i] = texts.index(annotation.text)

    return boxes, scores, labels


def non_maximum_suppression(
    boxes: np.ndarray,
    scores: np.ndarray,
    labels: np.ndarray,
    iou_threshold: float,
    score_threshold: float,
    max_num_detections: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    num_classes = np.max(labels) + 1
    scores_of_all_classes = np.zeros((len(boxes), num_classes), dtype=np.float32)
    for i, (score, label) in enumerate(zip(scores, labels)):
        scores_of_all_classes[i, label] = score
    logger.debug(f"Input: num_boxes={len(boxes)}")
    boxes, scores, labels = None, None, None
    logger.debug(f"Output: num_boxes={len(boxes)}")
    return boxes, scores, labels


def get_shapes_from_annotations(
    boxes: np.ndarray, scores: np.ndarray, labels: np.ndarray, texts: list[str]
) -> list[dict]:
    shapes: list[dict] = []
    for box, score, label in zip(boxes.tolist(), scores.tolist(), labels.tolist()):
        text = texts[label]
        xmin, ymin, xmax, ymax = box
        shape = {
            "label": text,
            "points": [[xmin, ymin], [xmax, ymax]],
            "group_id": None,
            "shape_type": "rectangle",
            "flags": {},
            "description": json.dumps(dict(score=score, text=text)),
        }
        shapes.append(shape)
    return shapes
