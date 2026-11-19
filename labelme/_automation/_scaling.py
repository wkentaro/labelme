from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from fractions import Fraction
from typing import TYPE_CHECKING
from typing import Final

import numpy as np
from numpy.typing import NDArray

from .._shape import Shape
from .._shape import mask_shape_box
from ._geometry import compute_polygon_from_circle
from ._geometry import round_bbox_to_int

_HALF: Final = Fraction(1, 2)

Scale = tuple[Fraction, Fraction]
UNSCALED: Final[Scale] = (Fraction(1), Fraction(1))

if TYPE_CHECKING:
    import osam


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
        return self._render(bounding_box=self.annotation.bounding_box)

    def pooled_mask(self, *, factor: Scale) -> NDArray[np.bool_]:
        STRIP_PIXELS: Final = 1 << 22
        bb = self.annotation.bounding_box
        assert bb is not None
        width = bb.xmax - bb.xmin + 1
        if factor[1] < 1:
            sent_ymin, sent_ymax = _scale_pixel_span(
                first=bb.ymin, last=bb.ymax, factor=factor[1]
            )
            step = max(1, STRIP_PIXELS // (width * math.ceil(1 / factor[1])))
            spans = [
                _scale_pixel_span(
                    first=top, last=min(top + step - 1, sent_ymax), factor=1 / factor[1]
                )
                for top in range(sent_ymin, sent_ymax + 1, step)
            ]
        else:
            step = max(1, STRIP_PIXELS // width)
            spans = [(top, top + step - 1) for top in range(bb.ymin, bb.ymax + 1, step)]
        strips = []
        for top, bottom in spans:
            top, bottom = max(top, bb.ymin), min(bottom, bb.ymax)
            _, strip = scale_mask(
                mask=self._render(
                    bounding_box=bb.model_copy(update={"ymin": top, "ymax": bottom})
                ),
                box=(bb.xmin, top, bb.xmax, bottom),
                factor=factor,
            )
            strips.append(strip)
        return np.concatenate(strips)

    def _render(self, *, bounding_box: osam.types.BoundingBox) -> NDArray[np.bool_]:
        return self.annotation.mask_from_scores(
            bounding_box=bounding_box,
            height=self.image_size[1],
            width=self.image_size[0],
        )


def _scale_pixel_span(*, first: int, last: int, factor: Fraction) -> tuple[int, int]:
    if factor <= 1:
        return (
            math.floor((first + _HALF) * factor),
            math.floor((last + _HALF) * factor),
        )
    return (
        math.ceil(first * factor - _HALF),
        math.ceil((last + 1) * factor - _HALF) - 1,
    )


def scale_pixel_box(
    *, box: tuple[int, int, int, int], factor: Scale
) -> tuple[int, int, int, int]:
    xmin, ymin, xmax, ymax = box
    x0, x1 = _scale_pixel_span(first=xmin, last=xmax, factor=factor[0])
    y0, y1 = _scale_pixel_span(first=ymin, last=ymax, factor=factor[1])
    return x0, y0, x1, y1


def _scale_mask_axis(
    *, mask: NDArray[np.bool_], first: int, factor: Fraction, axis: int
) -> NDArray[np.bool_]:
    if factor == 1:
        return mask
    last = first + mask.shape[axis] - 1
    if factor <= 1:
        sent_first, sent_last = _scale_pixel_span(first=first, last=last, factor=factor)
        runs = [
            max(first, _scale_pixel_span(first=sent, last=sent, factor=1 / factor)[0])
            - first
            for sent in range(sent_first, sent_last + 1)
        ]
        return np.logical_or.reduceat(mask, runs, axis=axis)
    sent_starts = [
        _scale_pixel_span(first=source, last=source, factor=factor)[0]
        for source in range(first, last + 2)
    ]
    return np.repeat(mask, np.diff(sent_starts), axis=axis)


def scale_mask(
    *,
    mask: NDArray[np.bool_],
    box: tuple[int, int, int, int],
    factor: Scale,
) -> tuple[tuple[int, int, int, int], NDArray[np.bool_]]:
    for first, axis_factor, axis in sorted(
        [(box[1], factor[1], 0), (box[0], factor[0], 1)], key=lambda step: step[1]
    ):
        mask = _scale_mask_axis(mask=mask, first=first, factor=axis_factor, axis=axis)
    return scale_pixel_box(box=box, factor=factor), mask


def scale_shape(*, shape: Shape, factor: Scale) -> Shape:
    if factor == UNSCALED:
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
    stretch = np.asarray(factor, dtype=np.float64)
    if shape.shape_type == "circle" and len(shape.points) == 2:  # noqa: PLR2004
        center, edge = shape.points
        scaled.shape_type = "polygon"
        scaled.points = (
            compute_polygon_from_circle(
                center=center, radius=float(np.linalg.norm(edge - center)), detail=100
            )
            * stretch
        )
        return scaled
    scaled.points = shape.points * stretch
    return scaled


def compare_at_sent_size(
    *,
    annotations: list[osam.types.Annotation],
    sent_size: tuple[int, int] | None,
    original_size: tuple[int, int] | None,
) -> tuple[list[osam.types.Annotation], list[AtImageSize | None], Scale]:
    if sent_size is None or original_size is None:
        return annotations, [None] * len(annotations), UNSCALED
    shrink = (
        Fraction(sent_size[0], original_size[0]),
        Fraction(sent_size[1], original_size[1]),
    )
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
            AtImageSize(annotation=annotation, image_size=original_size)
        )
    return compared, at_image_size, shrink
