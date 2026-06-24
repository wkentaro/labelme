from __future__ import annotations

import numpy as np
import osam
from loguru import logger
from numpy.typing import NDArray

from .._shape import Shape
from ._osam_session import OsamSession
from ._shape_builders import Detection
from ._shape_builders import shapes_from_detections
from ._suppression import suppress_detections_greedy
from ._suppression import suppress_detections_overlapping_existing_shapes
from ._types import AiOutputFormat


class AiAssistSession:
    model_name: str
    output_format: AiOutputFormat
    _session: OsamSession | None

    def __init__(
        self,
        model_name: str = "sam2:latest",
        output_format: AiOutputFormat = "polygon",
    ) -> None:
        self.model_name = model_name
        self.output_format = output_format
        self._session = None

    def _get_session(self) -> OsamSession:
        if self._session is None or self._session.model_name != self.model_name:
            self._session = OsamSession(model_name=self.model_name)
        return self._session

    def propose_shapes(
        self,
        *,
        image: NDArray[np.uint8],
        image_id: str,
        points: NDArray[np.floating],
        point_labels: NDArray[np.intp],
        existing_shapes: list[Shape],
    ) -> list[Shape]:
        response: osam.types.GenerateResponse = self._get_session().run(
            image=image,
            image_id=image_id,
            points=points,
            point_labels=point_labels,
        )
        # iou_threshold is hardcoded because the AI Assist flow has no
        # user-facing IoU control (unlike the AI Text Prompt flow); 0.5 matches
        # the AI Text Prompt widget default.
        detections = suppress_detections_greedy(
            detections=_detections_from_annotations(response.annotations),
            iou_threshold=0.5,
        )
        detections = suppress_detections_overlapping_existing_shapes(
            detections=detections,
            existing_shapes=existing_shapes,
        )
        return shapes_from_detections(
            detections=detections,
            shape_type=self.output_format,
        )


def _detections_from_annotations(
    annotations: list[osam.types.Annotation],
) -> list[Detection]:
    if not annotations:
        logger.warning("No annotations returned")
        return []
    sorted_annotations = sorted(
        annotations,
        key=lambda a: a.score if a.score is not None else 0,
        reverse=True,
    )
    detections: list[Detection] = []
    for annotation in sorted_annotations:
        bbox: tuple[float, float, float, float] | None = None
        if annotation.bounding_box is not None:
            bb = annotation.bounding_box
            bbox = (bb.xmin, bb.ymin, bb.xmax, bb.ymax)
        detections.append(Detection(bbox=bbox, mask=annotation.mask))
    return detections
