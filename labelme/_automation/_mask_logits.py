from __future__ import annotations

import dataclasses
from fractions import Fraction
from typing import TYPE_CHECKING
from typing import Final

import numpy as np
from numpy.typing import NDArray

from ._scaling import Scale
from ._scaling import pixels_centered_in

if TYPE_CHECKING:
    import osam

Box = tuple[float, float, float, float]


@dataclasses.dataclass(frozen=True)
class MaskLogits:
    """What osam drew a mask from, to draw it again on a larger image.

    cells tile box, in pixels of the image osam was sent. A point is in the
    mask when it lies in box and in clip and the bilinear sample of cells
    there is above 32768. A box holds a point on its lower edges and not on
    its upper ones, as a pixel covers [k, k + 1).
    """

    cells: NDArray[np.uint16]
    box: Box
    clip: Box

    @classmethod
    def from_annotation(
        cls, *, annotation: osam.types.Annotation, sent_size: tuple[int, int]
    ) -> MaskLogits | None:
        if annotation.mask_logits is None or annotation.mask_logits_box is None:
            return None
        clip: Box = (0, 0, sent_size[0], sent_size[1])
        if annotation.text is not None and annotation.bounding_box is not None:
            bb = annotation.bounding_box
            clip = (
                max(clip[0], bb.xmin),
                max(clip[1], bb.ymin),
                min(clip[2], bb.xmax + 1),
                min(clip[3], bb.ymax + 1),
            )
        return cls(
            cells=annotation.mask_logits, box=annotation.mask_logits_box, clip=clip
        )

    def draw(self, *, scale: Scale) -> tuple[NDArray[np.bool_], tuple[int, int]] | None:
        ZERO_LOGIT: Final = 32768
        rows, columns = self.cells.shape
        left, cell_x, toward_right = _pixels_on_cells(
            start=self.box[0],
            stop=self.box[2],
            clip=(self.clip[0], self.clip[2]),
            cells=columns,
            factor=scale[0],
        )
        top, cell_y, toward_below = _pixels_on_cells(
            start=self.box[1],
            stop=self.box[3],
            clip=(self.clip[1], self.clip[3]),
            cells=rows,
            factor=scale[1],
        )
        if not len(cell_x) or not len(cell_y):
            return None
        below = np.minimum(np.arange(rows) + 1, rows - 1)
        right = np.minimum(np.arange(columns) + 1, columns - 1)
        on = self.cells > ZERO_LOGIT
        cells_around = [on, on[below], on[:, right], on[below][:, right]]
        among_on_cells = np.logical_and.reduce(cells_around)
        on_the_edge = np.logical_or.reduce(cells_around) & ~among_on_cells
        widths = np.bincount(cell_x, minlength=columns)
        heights = np.bincount(cell_y, minlength=rows)
        in_row = among_on_cells[:, widths > 0].any(axis=1)[cell_y]
        in_column = among_on_cells[heights > 0].any(axis=0)[cell_x]
        logits = self.cells.astype(np.float64)
        tops = np.searchsorted(cell_y, np.arange(rows + 1))
        edge_bands = []
        for row in np.flatnonzero(on_the_edge.any(axis=1)):
            ys = slice(int(tops[row]), int(tops[row + 1]))
            xs = np.flatnonzero(on_the_edge[row][cell_x])
            band = _lerp(
                a=logits[row], b=logits[below[row]], toward_b=toward_below[ys, None]
            )
            lefts = cell_x[xs]
            sampled = (
                _lerp(
                    a=band[:, lefts], b=band[:, right[lefts]], toward_b=toward_right[xs]
                )
                > ZERO_LOGIT
            )
            edge_bands.append((ys, xs, sampled))
            in_row[ys] |= sampled.any(axis=1)
            in_column[xs] |= sampled.any(axis=0)
        if not in_row.any():
            return None
        y0, y1 = np.flatnonzero(in_row)[[0, -1]] + [0, 1]
        x0, x1 = np.flatnonzero(in_column)[[0, -1]] + [0, 1]
        mask = np.repeat(
            np.repeat(
                among_on_cells,
                np.bincount(cell_x[x0:x1], minlength=columns),
                axis=1,
            ),
            np.bincount(cell_y[y0:y1], minlength=rows),
            axis=0,
        )
        for ys, xs, sampled in edge_bands:
            band_top, band_bottom = max(ys.start, y0), min(ys.stop, y1)
            if band_top >= band_bottom:
                continue
            kept = (x0 <= xs) & (xs < x1)
            mask[band_top - y0 : band_bottom - y0, xs[kept] - x0] = sampled[
                band_top - ys.start : band_bottom - ys.start, kept
            ]
        return mask, (left + int(x0), top + int(y0))


def _pixels_on_cells(
    *,
    start: float,
    stop: float,
    clip: tuple[float, float],
    cells: int,
    factor: Fraction,
) -> tuple[int, NDArray[np.int64], NDArray[np.float64]]:
    first_pixel, end_pixel = pixels_centered_in(
        low=max(start, clip[0]), high=min(stop, clip[1]), factor=factor
    )
    centers_on_sent_image = (
        (np.arange(first_pixel, end_pixel) + 0.5) * factor.denominator
    ) / factor.numerator
    position = np.clip(
        (centers_on_sent_image - start) / (stop - start) * cells - 0.5, 0, cells - 1
    )
    cell = np.floor(position).astype(np.int64)
    return first_pixel, cell, position - cell


def _lerp(
    *, a: NDArray[np.float64], b: NDArray[np.float64], toward_b: NDArray[np.float64]
) -> NDArray[np.float64]:
    return a * (1 - toward_b) + b * toward_b
