from __future__ import annotations

import io
from typing import Any
from typing import Final

import numpy as np
import PIL.Image
import pytest
from numpy.typing import NDArray

from examples import utils

# The source modes behind the reported failures, with RGB as the control.
_SOURCE_MODES: Final = ["RGB", "RGBA", "LA", "L", "P"]


def _mask_shape(points: list[list[float]], mask: NDArray[np.bool_]) -> dict[str, Any]:
    return dict(
        label="car",
        points=points,
        shape_type="mask",
        flags={},
        description="",
        group_id=None,
        mask=mask,
        other_data={},
    )


def test_shapes_to_label_mask_paints_bbox_pixels() -> None:
    patch = np.ones((3, 5), dtype=bool)
    shape = _mask_shape(points=[[2.0, 1.0], [6.0, 3.0]], mask=patch)
    cls, _ = utils.shapes_to_label((20, 20), [shape], {"car": 1})
    painted = np.zeros((20, 20), dtype=bool)
    painted[1:4, 2:7] = True
    assert np.array_equal(cls > 0, painted)


def test_shapes_to_label_mask_clips_bbox_off_left_edge() -> None:
    patch = np.ones((3, 5), dtype=bool)
    shape = _mask_shape(points=[[-6.0, 1.0], [-2.0, 3.0]], mask=patch)
    cls, _ = utils.shapes_to_label((20, 20), [shape], {"car": 1})
    assert not (cls > 0).any()


def test_shapes_to_label_mask_clips_bbox_over_right_edge() -> None:
    patch = np.ones((3, 5), dtype=bool)
    shape = _mask_shape(points=[[17.0, 1.0], [21.0, 3.0]], mask=patch)
    cls, _ = utils.shapes_to_label((20, 20), [shape], {"car": 1})
    painted = np.zeros((20, 20), dtype=bool)
    painted[1:4, 17:20] = True
    assert np.array_equal(cls > 0, painted)


def test_shapes_to_label_mask_clips_bbox_off_top_left_corner() -> None:
    patch = np.zeros((5, 5), dtype=bool)
    patch[1, 2] = True  # -> canvas (0, 0)
    patch[4, 4] = True  # -> canvas (3, 2)
    shape = _mask_shape(points=[[-2.0, -1.0], [2.0, 3.0]], mask=patch)
    cls, _ = utils.shapes_to_label((20, 20), [shape], {"car": 1})
    painted = np.zeros((20, 20), dtype=bool)
    painted[0, 0] = True
    painted[3, 2] = True
    assert np.array_equal(cls > 0, painted)


def test_shapes_to_label_mask_rounds_origin_without_cropping_mask() -> None:
    patch = np.ones((3, 5), dtype=bool)
    shape = _mask_shape(points=[[2.7, 1.7], [6.3, 3.3]], mask=patch)
    cls, _ = utils.shapes_to_label((20, 20), [shape], {"car": 1})
    painted = np.zeros((20, 20), dtype=bool)
    painted[2:5, 3:8] = True
    assert np.array_equal(cls > 0, painted)


def _encode_png(img_pil: PIL.Image.Image) -> bytes:
    buf = io.BytesIO()
    img_pil.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture(name="source_rgb")
def _make_source_rgb() -> PIL.Image.Image:
    # Saturated, distinct colors so a palette round-trip stays lossless and a
    # channel mix-up is visible.
    arr = np.array(
        [
            [[255, 0, 0], [0, 255, 0]],
            [[0, 0, 255], [255, 255, 0]],
        ],
        dtype=np.uint8,
    )
    return PIL.Image.fromarray(arr)


@pytest.mark.parametrize("mode", _SOURCE_MODES)
def test_decode_img_data_as_rgb_returns_rgb_for_every_source_mode(
    mode: str, source_rgb: PIL.Image.Image
) -> None:
    arr = utils.decode_img_data_as_rgb(_encode_png(source_rgb.convert(mode)))
    assert arr.dtype == np.uint8
    assert arr.shape == (2, 2, 3)


@pytest.mark.parametrize("mode", _SOURCE_MODES)
def test_decode_img_data_as_rgb_output_is_jpeg_writable(
    mode: str, source_rgb: PIL.Image.Image
) -> None:
    # The reported crash: the VOC converters write the decoded array as JPEG,
    # which cannot represent an alpha channel.
    arr = utils.decode_img_data_as_rgb(_encode_png(source_rgb.convert(mode)))
    PIL.Image.fromarray(arr).save(io.BytesIO(), format="JPEG")


def test_decode_img_data_as_rgb_resolves_palette_colors(
    source_rgb: PIL.Image.Image,
) -> None:
    arr = utils.decode_img_data_as_rgb(_encode_png(source_rgb.convert("P")))
    np.testing.assert_array_equal(arr, np.asarray(source_rgb))


def test_decode_img_data_as_rgb_discards_alpha_without_compositing(
    source_rgb: PIL.Image.Image,
) -> None:
    rgba = source_rgb.convert("RGBA")
    rgba.putalpha(PIL.Image.new("L", rgba.size, 0))
    arr = utils.decode_img_data_as_rgb(_encode_png(rgba))
    np.testing.assert_array_equal(arr, np.asarray(source_rgb))
