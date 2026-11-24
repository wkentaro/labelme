from __future__ import annotations

from fractions import Fraction
from typing import Final

import numpy as np
import osam
import pytest
from numpy.typing import NDArray

from labelme._automation import _mask_logits
from labelme._automation._mask_logits import Box
from labelme._automation._mask_logits import MaskLogits
from labelme._automation._scaling import Scale
from labelme._automation._scaling import scale_shape
from labelme._shape import Shape

_OFF, _ON = 0, 65535
_SENT_IMAGE: Final[Box] = (0, 0, 32, 32)


def _sampled_at_every_pixel(
    *, logits: MaskLogits, scale: Scale, image_size: tuple[int, int]
) -> NDArray[np.bool_]:
    rows, columns = logits.cells.shape
    xmin, ymin, xmax, ymax = logits.box
    clip = logits.clip
    cells = logits.cells.astype(np.float64) - 32768

    def axis(
        *, size: int, factor: Fraction, start: float, stop: float, count: int
    ) -> tuple[NDArray[np.float64], NDArray[np.int64], NDArray[np.float64]]:
        centers = (np.arange(size) + 0.5) * factor.denominator / factor.numerator
        t = np.clip((centers - start) / (stop - start) * count - 0.5, 0, count - 1)
        cell = np.floor(t).astype(np.int64)
        return centers, cell, t - cell

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
    return (value > 0) & in_y[:, None] & in_x


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
        pytest.param(
            (Fraction(1), Fraction(1)), (4, 8, 28, 24), _SENT_IMAGE, id="unscaled"
        ),
        pytest.param((Fraction(3), Fraction(3)), (4, 8, 28, 24), _SENT_IMAGE, id="x3"),
        pytest.param(
            (Fraction(3307, 128), Fraction(5723, 256)),
            (4, 8, 28, 24),
            _SENT_IMAGE,
            id="605mp-ratio",
        ),
        pytest.param(
            (Fraction(7, 2), Fraction(5)),
            (-6, -2, 38, 34),
            _SENT_IMAGE,
            id="past-the-image",
        ),
        pytest.param(
            (Fraction(1040, 1008), Fraction(65, 63)),
            (3.5, 4.5, 30.5, 27.5),
            _SENT_IMAGE,
            id="fractional-edges",
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
    *, seed: int, scale: Scale, box: Box, clip: Box
) -> None:
    logits = MaskLogits(cells=_blobs(seed=seed, shape=(11, 13)), box=box, clip=clip)
    image_size = (round(32 * scale[0]), round(32 * scale[1]))

    drawn = logits.draw(scale=scale)

    assert logits.draws_nothing(scale=scale) == (drawn is None)
    on_canvas = _on_canvas(drawn=drawn, image_size=image_size)
    np.testing.assert_array_equal(
        on_canvas,
        _sampled_at_every_pixel(logits=logits, scale=scale, image_size=image_size),
    )
    pixels = np.random.default_rng(seed).integers(
        low=(-2, -2), high=(image_size[0] + 2, image_size[1] + 2), size=(300, 2)
    )
    for x, y in pixels.tolist():
        inside = 0 <= x < image_size[0] and 0 <= y < image_size[1]
        assert logits.holds(pixel=(x, y), scale=scale) == (
            inside and bool(on_canvas[y, x])
        )
    assert drawn is not None
    mask, _ = drawn
    assert mask[0].any() and mask[-1].any()
    assert mask[:, 0].any() and mask[:, -1].any()


@pytest.mark.parametrize("seed", range(20))
@pytest.mark.parametrize(
    ("scale", "box", "clip"),
    [
        pytest.param((Fraction(3), Fraction(3)), (4, 8, 28, 24), _SENT_IMAGE, id="x3"),
        pytest.param(
            (Fraction(3307, 128), Fraction(5723, 256)),
            (4, 8, 28, 24),
            _SENT_IMAGE,
            id="605mp-ratio",
        ),
        pytest.param(
            (Fraction(65, 63), Fraction(7, 2)),
            (-6, -2, 38, 34),
            _SENT_IMAGE,
            id="past-the-image",
        ),
        pytest.param(
            (Fraction(2), Fraction(1, 2)), (4, 8, 28, 24), _SENT_IMAGE, id="shorter"
        ),
        pytest.param(
            (Fraction(63, 65), Fraction(1)), (4, 8, 28, 24), _SENT_IMAGE, id="narrower"
        ),
        pytest.param(
            (Fraction(7, 2), Fraction(5)),
            (0, 4, 32, 28),
            (5, 9, 22, 21),
            id="cut-to-a-text-box",
        ),
    ],
)
def test_footprint_is_the_drawn_mask_scaled_back_to_the_sent_image(
    *, seed: int, scale: Scale, box: Box, clip: Box
) -> None:
    logits = MaskLogits(cells=_blobs(seed=seed, shape=(11, 13)), box=box, clip=clip)
    drawn = logits.draw(scale=scale)
    assert drawn is not None
    mask, origin = drawn
    saved = scale_shape(
        shape=Shape(
            shape_type="mask",
            points=np.array(
                [origin, [origin[0] + mask.shape[1] - 1, origin[1] + mask.shape[0] - 1]]
            ),
            mask=mask,
        ),
        factor=(1 / scale[0], 1 / scale[1]),
    )
    assert saved.mask is not None

    footprint = logits.footprint(scale=scale)
    assert footprint is not None
    np.testing.assert_array_equal(
        _on_canvas(drawn=footprint, image_size=(40, 40)),
        _on_canvas(
            drawn=(saved.mask, (int(saved.points[0][0]), int(saved.points[0][1]))),
            image_size=(40, 40),
        ),
    )
    bound = logits.footprint_bound(scale=scale)
    assert (bound is None) == (min(scale) < 1)
    if bound is not None:
        (height, width), (left, top) = footprint[0].shape, footprint[1]
        assert bound[0] <= left
        assert bound[1] <= top
        assert left + width <= bound[2]
        assert top + height <= bound[3]


def test_footprint_is_none_without_a_pixel_above_zero() -> None:
    logits = MaskLogits(
        cells=np.full((4, 4), 32768, np.uint16), box=(0, 0, 16, 16), clip=(0, 0, 16, 16)
    )

    assert logits.footprint(scale=(Fraction(8), Fraction(8))) is None


def test_draw_puts_the_edge_where_the_logits_cross_zero() -> None:
    logits = MaskLogits(
        cells=np.array([[_OFF, _ON]], dtype=np.uint16),
        box=(0, 0, 2, 1),
        clip=(0, 0, 2, 1),
    )

    drawn = logits.draw(scale=(Fraction(4), Fraction(4)))

    assert drawn is not None
    mask, origin = drawn
    assert origin == (4, 0)
    np.testing.assert_array_equal(mask, np.ones((4, 4), dtype=bool))


def test_draw_rounds_an_edge_no_coarser_than_an_image_pixel() -> None:
    cells = np.full((3, 3), _OFF, dtype=np.uint16)
    cells[1, 1] = _ON
    logits = MaskLogits(cells=cells, box=(0, 0, 3, 3), clip=(0, 0, 3, 3))

    drawn = logits.draw(scale=(Fraction(100), Fraction(100)))

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
            _on_canvas(drawn=logits.draw(scale=scale), image_size=(3, 3))
            for logits in (left, right)
        ],
        axis=0,
    )

    assert drawn_by[0].tolist() == [1, 1, 1]


def test_draw_is_none_without_a_pixel_above_zero() -> None:
    logits = MaskLogits(
        cells=np.full((4, 4), 32768, np.uint16), box=(0, 0, 16, 16), clip=(0, 0, 16, 16)
    )

    assert logits.draw(scale=(Fraction(8), Fraction(8))) is None


def test_draw_is_none_when_the_text_box_misses_the_cells() -> None:
    logits = MaskLogits(
        cells=np.full((4, 4), _ON, np.uint16), box=(0, 0, 16, 16), clip=(20, 20, 24, 24)
    )

    assert logits.draw(scale=(Fraction(8), Fraction(8))) is None


def test_draw_gives_a_pixel_centered_on_a_fractional_shared_edge_to_the_upper_box() -> (
    None
):
    cells = np.full((1, 1), _ON, dtype=np.uint16)
    scale = (Fraction(1040, 1008), Fraction(1))
    image: Box = (0, 0, 1008, 1)

    left = MaskLogits(cells=cells, box=(91.0, 0, 94.5, 1), clip=image).draw(scale=scale)
    right = MaskLogits(cells=cells, box=(94.5, 0, 98.0, 1), clip=image).draw(
        scale=scale
    )

    assert left is not None and right is not None
    assert left[1][0] + left[0].shape[1] == 97
    assert right[1][0] == 97


def test_draw_keeps_a_pixel_that_float32_rounds_onto_zero() -> None:
    cells = np.full((256, 256), 32768, dtype=np.uint16)
    cells[128, 128] = 32769
    logits = MaskLogits(cells=cells, box=(0, 0, 1024, 1024), clip=(0, 0, 1024, 1024))

    drawn = logits.draw(scale=(Fraction(12289, 1024), Fraction(12289, 1024)))

    assert drawn is not None
    mask, (x, _) = drawn
    assert (x, x + mask.shape[1] - 1) == (6120, 6216)


def test_a_pixel_whose_sample_is_exactly_zero_is_left_out() -> None:
    cells = np.full((256, 256), 30720, dtype=np.uint16)
    cells[127:129, 127:129] = [[6880, 58656], [9413, 56123]]
    logits = MaskLogits(cells=cells, box=(0, 0, 1024, 1024), clip=(0, 0, 1024, 1024))
    scale = (Fraction(101, 1024), Fraction(2049, 1024))

    assert not logits.holds(pixel=(50, 1022), scale=scale)
    assert logits.draw(scale=scale) is None


def test_from_annotation_keeps_the_mask_inside_the_sent_image() -> None:
    annotation = osam.types.Annotation(
        bounding_box=osam.types.BoundingBox(xmin=0, ymin=0, xmax=7, ymax=7),
        mask=np.ones((8, 8), dtype=bool),
        mask_logits=np.full((3, 3), _ON, dtype=np.uint16),
        mask_logits_box=(-4.0, -4.0, 12.0, 12.0),
    )

    logits = MaskLogits.from_annotation(annotation=annotation, sent_size=(8, 6))

    assert logits is not None
    drawn = logits.draw(scale=(Fraction(4), Fraction(4)))
    assert drawn is not None
    mask, origin = drawn
    assert origin == (0, 0)
    assert mask.shape == (24, 32)


def test_from_annotation_cuts_a_text_annotation_to_its_box() -> None:
    cells = np.full((2, 2), _ON, dtype=np.uint16)

    def annotation(*, text: str | None) -> osam.types.Annotation:
        return osam.types.Annotation(
            text=text,
            bounding_box=osam.types.BoundingBox(xmin=1, ymin=2, xmax=5, ymax=6),
            mask=np.ones((5, 5), dtype=bool),
            mask_logits=cells,
            mask_logits_box=(0.0, 0.0, 8.0, 8.0),
        )

    prompted = MaskLogits.from_annotation(
        annotation=annotation(text=None), sent_size=(16, 16)
    )
    found = MaskLogits.from_annotation(
        annotation=annotation(text="cat"), sent_size=(16, 16)
    )

    assert prompted is not None and found is not None
    assert prompted.clip == (0, 0, 16, 16)
    assert found.clip == (1, 2, 6, 7)
    assert prompted.box == found.box == (0.0, 0.0, 8.0, 8.0)


def test_from_annotation_is_none_without_logits() -> None:
    annotation = osam.types.Annotation(
        bounding_box=osam.types.BoundingBox(xmin=0, ymin=0, xmax=1, ymax=1),
        mask=np.ones((2, 2), dtype=bool),
    )

    assert MaskLogits.from_annotation(annotation=annotation, sent_size=(2, 2)) is None


def test_draws_nothing_sees_a_pixel_among_on_cells_without_sampling_an_edge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    one_logit = 256
    cells = np.full((8, 8), 32768 - 20 * one_logit, dtype=np.uint16)
    cells[2:6, 2:6] = 32768 + 20 * one_logit
    logits = MaskLogits(cells=cells, box=(0, 0, 8, 8), clip=(0, 0, 8, 8))

    def no_sampling(**_: object) -> None:
        raise AssertionError("an edge was sampled")

    monkeypatch.setattr(_mask_logits, "_lerp", no_sampling)

    assert not logits.draws_nothing(scale=(Fraction(4), Fraction(4)))


def test_draws_nothing_stops_at_the_first_edge_band_that_draws_a_pixel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    one_logit = 256
    cells = np.full((8, 8), 32768 - 20 * one_logit, dtype=np.uint16)
    cells[:, 3] = 32768 + 20 * one_logit
    logits = MaskLogits(cells=cells, box=(0, 0, 8, 8), clip=(0, 0, 8, 8))
    lerp = _mask_logits._lerp
    sampled = []

    def counting(**kwargs: NDArray[np.float64]) -> NDArray[np.float64]:
        sampled.append(None)
        return lerp(**kwargs)

    monkeypatch.setattr(_mask_logits, "_lerp", counting)

    assert not logits.draws_nothing(scale=(Fraction(4), Fraction(4)))
    assert not logits.draws_nothing(scale=(Fraction(4), Fraction(4)))
    lerps_per_band = 2
    assert len(sampled) == lerps_per_band


def test_draw_takes_the_word_that_nothing_is_drawn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    one_logit = 256
    cells = np.full((8, 8), 32768 - 20 * one_logit, dtype=np.uint16)
    cells[3, 3] = 32768 + 20 * one_logit
    logits = MaskLogits(cells=cells, box=(0, 0, 8, 8), clip=(0, 0, 8, 8))
    scale = (Fraction(1, 2), Fraction(1, 2))
    lerp = _mask_logits._lerp
    sampled = []

    def counting(**kwargs: NDArray[np.float64]) -> NDArray[np.float64]:
        sampled.append(None)
        return lerp(**kwargs)

    monkeypatch.setattr(_mask_logits, "_lerp", counting)

    assert logits.draws_nothing(scale=scale)
    edge_rows, lerps_per_band = 2, 2
    assert len(sampled) == edge_rows * lerps_per_band
    assert logits.draw(scale=scale) is None
    assert len(sampled) == edge_rows * lerps_per_band
