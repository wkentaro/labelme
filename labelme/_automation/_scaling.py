from __future__ import annotations

import copy
import dataclasses
import math
from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

from .._shape import Shape
from ._geometry import compute_polygon_from_circle
from ._geometry import round_bbox_to_int
from ._types import AiOutputFormat

if TYPE_CHECKING:
    import osam

    from ._shape_builders import Detection


@dataclass(frozen=True, eq=False)
class AtImageSize:
    annotation: osam.types.Annotation
    image_size: tuple[int, int]

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        bb = self.annotation.bounding_box
        assert bb is not None
        return bb.xmin, bb.ymin, bb.xmax, bb.ymax

    def mask(self) -> NDArray[np.bool_] | None:
        assert self.annotation.bounding_box is not None
        if self.annotation.mask_scores is None:
            return self.annotation.mask
        return self.annotation.mask_from_scores(
            bounding_box=self.annotation.bounding_box,
            height=self.image_size[1],
            width=self.image_size[0],
        )


def _scale_pixel_span(*, first: int, last: int, factor: float) -> tuple[int, int]:
    start, end = round(first * factor), round((last + 1) * factor) - 1
    if start > end:
        start = end = math.floor((first + last + 1) / 2 * factor)
    return start, end


def scale_pixel_box(
    *, box: tuple[int, int, int, int], factor: tuple[float, float]
) -> tuple[int, int, int, int]:
    xmin, ymin, xmax, ymax = box
    x0, x1 = _scale_pixel_span(first=xmin, last=xmax, factor=factor[0])
    y0, y1 = _scale_pixel_span(first=ymin, last=ymax, factor=factor[1])
    return x0, y0, x1, y1


def resize_mask(*, mask: NDArray[np.bool_], size: tuple[int, int]) -> NDArray[np.bool_]:
    width, height = size
    rows = (2 * np.arange(height) + 1) * mask.shape[0] // (2 * height)
    columns = (2 * np.arange(width) + 1) * mask.shape[1] // (2 * width)
    return mask[np.ix_(rows, columns)]


def scale_shape(*, shape: Shape, factor: tuple[float, float]) -> Shape:
    if factor == (1.0, 1.0):
        return shape
    scaled = copy.copy(shape)
    if shape.shape_type == "mask" and shape.mask is not None:
        xmin, ymin = np.round(shape.points.min(axis=0)).astype(int)
        height, width = shape.mask.shape
        x0, y0, x1, y1 = scale_pixel_box(
            box=(xmin, ymin, xmin + width - 1, ymin + height - 1), factor=factor
        )
        scaled.points = np.array([[x0, y0], [x1, y1]], dtype=np.float64)
        scaled.mask = resize_mask(mask=shape.mask, size=(x1 - x0 + 1, y1 - y0 + 1))
        return scaled
    if shape.shape_type == "rectangle" and len(shape.points) == 2:  # noqa: PLR2004
        x0, y0, x1, y1 = scale_pixel_box(
            box=round_bbox_to_int(
                bbox=(*shape.points.min(axis=0), *shape.points.max(axis=0))
            ),
            factor=factor,
        )
        scaled.points = np.array([[x0, y0], [x1, y1]], dtype=np.float64)
        return scaled
    if shape.shape_type == "circle" and len(shape.points) == 2:  # noqa: PLR2004
        center, edge = shape.points
        scaled.shape_type = "polygon"
        scaled.points = compute_polygon_from_circle(
            center=center, radius=float(np.linalg.norm(edge - center)), detail=100
        ) * np.asarray(factor)
        return scaled
    scaled.points = shape.points * np.asarray(factor)
    return scaled


def compare_at_sent_size(
    *,
    annotations: list[osam.types.Annotation],
    sent_size: tuple[int, int] | None,
    original_size: tuple[int, int] | None,
) -> tuple[list[osam.types.Annotation], list[AtImageSize | None], tuple[float, float]]:
    if sent_size is None or original_size is None:
        return annotations, [None] * len(annotations), (1.0, 1.0)
    shrink = (sent_size[0] / original_size[0], sent_size[1] / original_size[1])
    compared: list[osam.types.Annotation] = []
    at_image_size: list[AtImageSize | None] = []
    for annotation in annotations:
        if annotation.bounding_box is None:
            raise ValueError("an annotation has no box to shrink")
        bb = annotation.bounding_box
        xmin, ymin, xmax, ymax = scale_pixel_box(
            box=(bb.xmin, bb.ymin, bb.xmax, bb.ymax), factor=shrink
        )
        small = bb.model_copy(
            update={"xmin": xmin, "ymin": ymin, "xmax": xmax, "ymax": ymax}
        )
        if annotation.mask_scores is not None:
            mask = annotation.mask_from_scores(
                bounding_box=small, height=sent_size[1], width=sent_size[0]
            )
        elif annotation.mask is None or sent_size == original_size:
            mask = annotation.mask
        else:
            mask = resize_mask(
                mask=annotation.mask, size=(xmax - xmin + 1, ymax - ymin + 1)
            )
        compared.append(
            annotation.model_copy(update={"bounding_box": small, "mask": mask})
        )
        at_image_size.append(
            None
            if sent_size == original_size
            else AtImageSize(annotation=annotation, image_size=original_size)
        )
    return compared, at_image_size, shrink


def enlarge_survivors(
    *, detections: list[Detection], shape_type: AiOutputFormat
) -> Iterator[Detection]:
    for detection in detections:
        if detection.at_image_size is None:
            yield detection
            continue
        yield dataclasses.replace(
            detection,
            bbox=detection.at_image_size.bbox,
            mask=None if shape_type == "rectangle" else detection.at_image_size.mask(),
        )
