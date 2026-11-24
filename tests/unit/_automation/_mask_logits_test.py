from __future__ import annotations

from fractions import Fraction

import numpy as np
import osam
import pytest
from numpy.typing import NDArray

from labelme._automation._mask_logits import Box
from labelme._automation._mask_logits import MaskLogits
from labelme._automation._scaling import Scale

_OFF, _ON = 0, 65535


def _sampled_at_every_pixel(
    *, logits: MaskLogits, scale: Scale, image_size: tuple[int, int]
) -> NDArray[np.bool_]:
    rows, columns = logits.cells.shape
    xmin, ymin, xmax, ymax = logits.box
    clip = logits.box if logits.clip is None else logits.clip
    cells = logits.cells.astype(np.float32)

    def axis(
        *, size: int, factor: Fraction, start: float, stop: float, count: int
    ) -> tuple[NDArray[np.float64], NDArray[np.int64], NDArray[np.float32]]:
        centers = (np.arange(size) + 0.5) * factor.denominator / factor.numerator
        t = np.clip((centers - start) / (stop - start) * count - 0.5, 0, count - 1)
        cell = np.floor(t).astype(np.int64)
        return centers, cell, (t - cell).astype(np.float32)

    xs, x0, wx = axis(
        size=image_size[0], factor=scale[0], start=xmin, stop=xmax, count=columns
    )
    ys, y0, wy = axis(
        size=image_size[1], factor=scale[1], start=ymin, stop=ymax, count=rows
    )
    x1, y1 = np.minimum(x0 + 1, columns - 1), np.minimum(y0 + 1, rows - 1)
    band = cells[y0] * (1 - wy[:, None]) + cells[y1] * wy[:, None]
    value = band[:, x0] * (1 - wx) + band[:, x1] * wx
    in_x = (max(xmin, clip[0]) <= xs) & (xs < min(xmax, clip[2]))
    in_y = (max(ymin, clip[1]) <= ys) & (ys < min(ymax, clip[3]))
    return (value > 32768) & in_y[:, None] & in_x


def _on_canvas(
    *,
    drawn: tuple[NDArray[np.bool_], tuple[int, int]] | None,
    image_size: tuple[int, int],
) -> NDArray[np.bool_]:
    canvas = np.zeros(image_size[::-1], dtype=bool)
    if drawn is not None:
        mask, (x, y) = drawn
        canvas[y : y + mask.shape[0], x : x + mask.shape[1]] = mask
    return canvas


def _blobs(*, seed: int, shape: tuple[int, int]) -> NDArray[np.uint16]:
    rng = np.random.default_rng(seed)
    coarse = rng.uniform(-3, 3, size=(shape[0] // 4 + 2, shape[1] // 4 + 2))
    smooth = np.kron(coarse, np.ones((4, 4)))[: shape[0], : shape[1]]
    logit = smooth + rng.uniform(-1, 1, size=shape)
    return np.clip(32768 + 256 * logit, 0, 65535).astype(np.uint16)


@pytest.mark.parametrize("seed", range(20))
@pytest.mark.parametrize(
    ("scale", "box", "clip"),
    [
        pytest.param((Fraction(1), Fraction(1)), (4, 8, 28, 24), None, id="unscaled"),
        pytest.param((Fraction(3), Fraction(3)), (4, 8, 28, 24), None, id="x3"),
        pytest.param(
            (Fraction(3307, 128), Fraction(5723, 256)),
            (4, 8, 28, 24),
            None,
            id="605mp-ratio",
        ),
        pytest.param(
            (Fraction(7, 2), Fraction(5)), (-6, -2, 38, 34), None, id="past-the-image"
        ),
        pytest.param(
            (Fraction(7, 2), Fraction(5)),
            (0, 4, 32, 28),
            (5, 9, 22, 21),
            id="cut-to-a-text-box",
        ),
    ],
)
def test_draw_matches_sampling_every_pixel(
    *, seed: int, scale: Scale, box: Box, clip: Box | None
) -> None:
    logits = MaskLogits(cells=_blobs(seed=seed, shape=(11, 13)), box=box, clip=clip)
    image_size = (round(32 * scale[0]), round(32 * scale[1]))

    drawn = logits.draw(scale=scale, image_size=image_size)

    np.testing.assert_array_equal(
        _on_canvas(drawn=drawn, image_size=image_size),
        _sampled_at_every_pixel(logits=logits, scale=scale, image_size=image_size),
    )
    assert drawn is not None
    mask, _ = drawn
    assert mask[0].any() and mask[-1].any()
    assert mask[:, 0].any() and mask[:, -1].any()


def test_draw_puts_the_edge_where_the_logits_cross_zero() -> None:
    logits = MaskLogits(
        cells=np.array([[_OFF, _ON]], dtype=np.uint16), box=(0, 0, 2, 1)
    )

    drawn = logits.draw(scale=(Fraction(4), Fraction(4)), image_size=(8, 4))

    assert drawn is not None
    mask, origin = drawn
    assert origin == (4, 0)
    np.testing.assert_array_equal(mask, np.ones((4, 4), dtype=bool))


def test_draw_rounds_an_edge_no_coarser_than_an_image_pixel() -> None:
    cells = np.full((3, 3), _OFF, dtype=np.uint16)
    cells[1, 1] = _ON
    logits = MaskLogits(cells=cells, box=(0, 0, 3, 3))

    drawn = logits.draw(scale=(Fraction(100), Fraction(100)), image_size=(300, 300))

    assert drawn is not None
    mask, origin = drawn
    assert origin == (100, 100)
    assert mask.shape == (100, 100)
    assert mask[50].tolist() == [True] * 100
    widths = mask.sum(axis=1)
    assert widths[0] == 2
    assert (np.diff(widths[:50]) >= 0).all() and (np.diff(widths[:50]) <= 4).all()


def test_draw_gives_a_pixel_on_a_shared_edge_to_one_text_box() -> None:
    cells = np.full((1, 1), _ON, dtype=np.uint16)
    left = MaskLogits(cells=cells, box=(0, 0, 2, 2), clip=(0, 0, 1, 1))
    right = MaskLogits(cells=cells, box=(0, 0, 2, 2), clip=(1, 0, 2, 1))
    scale = (Fraction(3, 2), Fraction(3, 2))

    drawn_by = np.sum(
        [
            _on_canvas(
                drawn=logits.draw(scale=scale, image_size=(3, 3)), image_size=(3, 3)
            )
            for logits in (left, right)
        ],
        axis=0,
    )

    assert drawn_by[0].tolist() == [1, 1, 1]


def test_draw_is_none_without_a_pixel_above_zero() -> None:
    logits = MaskLogits(cells=np.full((4, 4), 32768, np.uint16), box=(0, 0, 16, 16))

    assert logits.draw(scale=(Fraction(8), Fraction(8)), image_size=(128, 128)) is None


def test_draw_is_none_when_the_text_box_misses_the_cells() -> None:
    logits = MaskLogits(
        cells=np.full((4, 4), _ON, np.uint16), box=(0, 0, 16, 16), clip=(20, 20, 24, 24)
    )

    assert logits.draw(scale=(Fraction(8), Fraction(8)), image_size=(256, 256)) is None


def test_from_annotation_cuts_only_a_text_annotation_to_its_box() -> None:
    cells = np.full((2, 2), _ON, dtype=np.uint16)

    def annotation(*, text: str | None) -> osam.types.Annotation:
        return osam.types.Annotation(
            text=text,
            bounding_box=osam.types.BoundingBox(xmin=1, ymin=2, xmax=5, ymax=6),
            mask=np.ones((5, 5), dtype=bool),
            mask_logits=cells,
            mask_logits_box=(0.0, 0.0, 8.0, 8.0),
        )

    prompted = MaskLogits.from_annotation(annotation=annotation(text=None))
    found = MaskLogits.from_annotation(annotation=annotation(text="cat"))

    assert prompted is not None and found is not None
    assert prompted.clip is None
    assert found.clip == (1, 2, 6, 7)
    assert prompted.box == found.box == (0.0, 0.0, 8.0, 8.0)


def test_from_annotation_is_none_without_logits() -> None:
    annotation = osam.types.Annotation(
        bounding_box=osam.types.BoundingBox(xmin=0, ymin=0, xmax=1, ymax=1),
        mask=np.ones((2, 2), dtype=bool),
    )

    assert MaskLogits.from_annotation(annotation=annotation) is None
