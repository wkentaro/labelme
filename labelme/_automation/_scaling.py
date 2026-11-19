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
from .._shape import mask_shape_box
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


def _grid_sources(
    *, first: int, start: int, end: int, length: int, factor: float
) -> NDArray[np.intp]:
    sources = np.floor((np.arange(start, end + 1) + 0.5) / factor).astype(np.intp)
    return np.clip(sources - first, 0, length - 1)


def scale_mask(
    *,
    mask: NDArray[np.bool_],
    box: tuple[int, int, int, int],
    factor: tuple[float, float],
) -> tuple[tuple[int, int, int, int], NDArray[np.bool_]]:
    scaled_box = x0, y0, x1, y1 = scale_pixel_box(box=box, factor=factor)
    height, width = mask.shape
    rows = _grid_sources(
        first=box[1], start=y0, end=y1, length=height, factor=factor[1]
    )
    columns = _grid_sources(
        first=box[0], start=x0, end=x1, length=width, factor=factor[0]
    )
    return scaled_box, mask[np.ix_(rows, columns)]


def scale_shape(*, shape: Shape, factor: tuple[float, float]) -> Shape:
    if factor == (1.0, 1.0):
        return shape
    scaled = copy.copy(shape)
    if shape.shape_type == "mask" and shape.mask is not None:
        (x0, y0, x1, y1), scaled.mask = scale_mask(
            mask=shape.mask, box=mask_shape_box(shape=shape), factor=factor
        )
        scaled.points = np.array([[x0, y0], [x1, y1]], dtype=np.float64)
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
        box = (bb.xmin, bb.ymin, bb.xmax, bb.ymax)
        mask = annotation.mask
        if mask is None or annotation.mask_scores is not None:
            box = scale_pixel_box(box=box, factor=shrink)
        elif sent_size != original_size:
            box, mask = scale_mask(mask=mask, box=box, factor=shrink)
        xmin, ymin, xmax, ymax = box
        small = bb.model_copy(
            update={"xmin": xmin, "ymin": ymin, "xmax": xmax, "ymax": ymax}
        )
        if annotation.mask_scores is not None:
            mask = annotation.mask_from_scores(
                bounding_box=small, height=sent_size[1], width=sent_size[0]
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
