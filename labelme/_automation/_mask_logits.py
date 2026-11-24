from __future__ import annotations

import dataclasses
import math
from collections.abc import Iterable
from collections.abc import Iterator
from fractions import Fraction
from typing import TYPE_CHECKING
from typing import Final

import numpy as np
from numpy.typing import NDArray

from ._scaling import Scale
from ._scaling import pixel_holding_center
from ._scaling import pixels_centered_in
from ._scaling import scale_mask

if TYPE_CHECKING:
    import osam

Box = tuple[float, float, float, float]

_ZERO_LOGIT: Final = 32768

_EdgeBand = tuple[slice, NDArray[np.int64], NDArray[np.bool_]]


@dataclasses.dataclass(frozen=True)
class _Sampled:
    left: int
    top: int
    cell_x: NDArray[np.int64]
    cell_y: NDArray[np.int64]
    among_on_cells: NDArray[np.bool_]
    edge_bands: list[_EdgeBand]


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
    _sampled: dict[Scale, _Sampled | None] = dataclasses.field(
        default_factory=dict, init=False, repr=False, compare=False
    )
    _draws_at: dict[Scale, bool] = dataclasses.field(
        default_factory=dict, init=False, repr=False, compare=False
    )

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

    @property
    def reach(self) -> Box:
        return (
            max(self.box[0], self.clip[0]),
            max(self.box[1], self.clip[1]),
            min(self.box[2], self.clip[2]),
            min(self.box[3], self.clip[3]),
        )

    def footprint_bound(self, *, scale: Scale) -> tuple[int, int, int, int] | None:
        if min(scale) < 1:
            return None
        xmin, ymin, xmax, ymax = self.reach
        return math.floor(xmin), math.floor(ymin), math.ceil(xmax), math.ceil(ymax)

    def holds(self, *, pixel: tuple[int, int], scale: Scale) -> bool:
        (left, cell_x, toward_right), (top, cell_y, toward_below) = self._axes(
            scale=scale
        )
        column, row = pixel[0] - left, pixel[1] - top
        if not (0 <= column < len(cell_x) and 0 <= row < len(cell_y)):
            return False
        rows, columns = self.cells.shape
        x, y = cell_x[column], cell_y[row]
        right, below = min(x + 1, columns - 1), min(y + 1, rows - 1)
        around = self.cells[np.ix_([y, below], [x, right])].astype(np.float64)
        band = _lerp(a=around[0], b=around[1], toward_b=toward_below[row])
        return bool(
            _lerp(a=band[0], b=band[1], toward_b=toward_right[column]) > _ZERO_LOGIT
        )

    def draws_nothing(self, *, scale: Scale) -> bool:
        if scale not in self._draws_at:
            axes = self._axes(scale=scale)
            (_, cell_x, _), (_, cell_y, _) = axes
            among_on_cells, on_the_edge = self._cells_by_surroundings()
            self._draws_at[scale] = _draws_a_pixel(
                among_on_cells=among_on_cells,
                cell_x=cell_x,
                cell_y=cell_y,
                edge_bands=self._edge_bands(axes=axes, on_the_edge=on_the_edge),
            )
        return not self._draws_at[scale]

    def draw(self, *, scale: Scale) -> tuple[NDArray[np.bool_], tuple[int, int]] | None:
        sampled = self._sample(scale=scale)
        if sampled is None:
            return None
        rows, columns = self.cells.shape
        cell_x, cell_y = sampled.cell_x, sampled.cell_y
        widths = np.bincount(cell_x, minlength=columns)
        heights = np.bincount(cell_y, minlength=rows)
        among_on_cells = sampled.among_on_cells
        in_row = np.any(among_on_cells[:, widths > 0], axis=1)[cell_y]
        in_column = np.any(among_on_cells[heights > 0], axis=0)[cell_x]
        for ys, xs, on in sampled.edge_bands:
            in_row[ys] |= on.any(axis=1)
            in_column[xs] |= on.any(axis=0)
        y0, y1 = np.flatnonzero(in_row)[[0, -1]] + [0, 1]
        x0, x1 = np.flatnonzero(in_column)[[0, -1]] + [0, 1]
        mask = np.repeat(
            np.repeat(
                sampled.among_on_cells,
                np.bincount(cell_x[x0:x1], minlength=columns),
                axis=1,
            ),
            np.bincount(cell_y[y0:y1], minlength=rows),
            axis=0,
        )
        for ys, xs, on in sampled.edge_bands:
            band_top, band_bottom = max(ys.start, y0), min(ys.stop, y1)
            if band_top >= band_bottom:
                continue
            kept = (x0 <= xs) & (xs < x1)
            mask[band_top - y0 : band_bottom - y0, xs[kept] - x0] = on[
                band_top - ys.start : band_bottom - ys.start, kept
            ]
        return mask, (sampled.left + int(x0), sampled.top + int(y0))

    def footprint(
        self, *, scale: Scale
    ) -> tuple[NDArray[np.bool_], tuple[int, int]] | None:
        sampled = self._sample(scale=scale)
        if sampled is None:
            return None
        columns_of, left, to_sent_x = _grouped_to_sent(
            first=sampled.left, count=len(sampled.cell_x), factor=scale[0]
        )
        rows_of, top, to_sent_y = _grouped_to_sent(
            first=sampled.top, count=len(sampled.cell_y), factor=scale[1]
        )
        footprint = (
            _touched(groups=rows_of, cells=sampled.cell_y, count=self.cells.shape[0])
            @ sampled.among_on_cells.astype(np.float32)
            @ _touched(
                groups=columns_of, cells=sampled.cell_x, count=self.cells.shape[1]
            ).T
        ) > 0
        for ys, xs, on in sampled.edge_bands:
            if not on.size:
                continue
            band_rows, band_columns = rows_of[ys], columns_of[xs]
            row_starts = np.flatnonzero(np.diff(band_rows, prepend=-1))
            column_starts = np.flatnonzero(np.diff(band_columns, prepend=-1))
            footprint[np.ix_(band_rows[row_starts], band_columns[column_starts])] |= (
                np.logical_or.reduceat(
                    np.logical_or.reduceat(on, row_starts, axis=0),
                    column_starts,
                    axis=1,
                )
            )
        mask, box = scale_mask(
            mask=footprint, origin=(left, top), factor=(to_sent_x, to_sent_y)
        )
        return mask, box[:2]

    def _sample(self, *, scale: Scale) -> _Sampled | None:
        if scale in self._sampled:
            return self._sampled[scale]
        axes = self._axes(scale=scale)
        (left, cell_x, _), (top, cell_y, _) = axes
        if self._draws_at.get(scale) is False or not len(cell_x) or not len(cell_y):
            self._sampled[scale] = None
            return None
        among_on_cells, on_the_edge = self._cells_by_surroundings()
        edge_bands = list(self._edge_bands(axes=axes, on_the_edge=on_the_edge))
        if not _draws_a_pixel(
            among_on_cells=among_on_cells,
            cell_x=cell_x,
            cell_y=cell_y,
            edge_bands=edge_bands,
        ):
            self._sampled[scale] = None
            return None
        self._sampled[scale] = _Sampled(
            left=left,
            top=top,
            cell_x=cell_x,
            cell_y=cell_y,
            among_on_cells=among_on_cells,
            edge_bands=edge_bands,
        )
        return self._sampled[scale]

    def _edge_bands(
        self, *, axes: tuple[_Axis, _Axis], on_the_edge: NDArray[np.bool_]
    ) -> Iterator[_EdgeBand]:
        (_, cell_x, toward_right), (_, cell_y, toward_below) = axes
        rows, columns = self.cells.shape
        below, right = _next_cells(count=rows), _next_cells(count=columns)
        logits = self.cells.astype(np.float64)
        tops = np.searchsorted(cell_y, np.arange(rows + 1))
        for row in np.flatnonzero(on_the_edge.any(axis=1)):
            ys = slice(int(tops[row]), int(tops[row + 1]))
            xs = np.flatnonzero(on_the_edge[row][cell_x])
            band = _lerp(
                a=logits[row], b=logits[below[row]], toward_b=toward_below[ys, None]
            )
            lefts = cell_x[xs]
            yield (
                ys,
                xs,
                _lerp(
                    a=band[:, lefts], b=band[:, right[lefts]], toward_b=toward_right[xs]
                )
                > _ZERO_LOGIT,
            )

    def _cells_by_surroundings(self) -> tuple[NDArray[np.bool_], NDArray[np.bool_]]:
        rows, columns = self.cells.shape
        below, right = _next_cells(count=rows), _next_cells(count=columns)
        on = self.cells > _ZERO_LOGIT
        around = [on, on[below], on[:, right], on[below][:, right]]
        among_on_cells = np.logical_and.reduce(around)
        return among_on_cells, np.logical_or.reduce(around) & ~among_on_cells

    def _axes(self, *, scale: Scale) -> tuple[_Axis, _Axis]:
        rows, columns = self.cells.shape
        reach = self.reach
        return (
            _pixels_on_cells(
                start=self.box[0],
                stop=self.box[2],
                reach=(reach[0], reach[2]),
                cells=columns,
                factor=scale[0],
            ),
            _pixels_on_cells(
                start=self.box[1],
                stop=self.box[3],
                reach=(reach[1], reach[3]),
                cells=rows,
                factor=scale[1],
            ),
        )


_Axis = tuple[int, NDArray[np.int64], NDArray[np.float64]]


def _next_cells(*, count: int) -> NDArray[np.int64]:
    return np.minimum(np.arange(count) + 1, count - 1)


def _draws_a_pixel(
    *,
    among_on_cells: NDArray[np.bool_],
    cell_x: NDArray[np.int64],
    cell_y: NDArray[np.int64],
    edge_bands: Iterable[_EdgeBand],
) -> bool:
    rows, columns = among_on_cells.shape
    with_pixels = np.ix_(
        np.bincount(cell_y, minlength=rows) > 0,
        np.bincount(cell_x, minlength=columns) > 0,
    )
    return bool(among_on_cells[with_pixels].any()) or any(
        on.any() for _, _, on in edge_bands
    )


def _grouped_to_sent(
    *, first: int, count: int, factor: Fraction
) -> tuple[NDArray[np.int64], int, Fraction]:
    if factor <= 1:
        return np.arange(count), first, 1 / factor
    sent = pixel_holding_center(
        pixel=np.arange(first, first + count), factor=1 / factor
    )
    return sent - sent[0], int(sent[0]), Fraction(1)


def _touched(
    *, groups: NDArray[np.int64], cells: NDArray[np.int64], count: int
) -> NDArray[np.float32]:
    touched = np.zeros((int(groups[-1]) + 1, count), dtype=np.float32)
    touched[groups, cells] = 1
    return touched


def _pixels_on_cells(
    *,
    start: float,
    stop: float,
    reach: tuple[float, float],
    cells: int,
    factor: Fraction,
) -> _Axis:
    first_pixel, end_pixel = pixels_centered_in(
        low=reach[0], high=reach[1], factor=factor
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
