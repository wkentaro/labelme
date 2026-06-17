from __future__ import annotations

import io
from typing import Final

import numpy as np
import PIL.Image
import pytest

from labelme.utils import image as image_module

from .util import data_dir
from .util import get_img_and_data


def test_img_b64_to_arr() -> None:
    img, _ = get_img_and_data()
    assert img.dtype == np.uint8
    assert img.shape == (907, 1210, 3)


def test_img_arr_to_b64() -> None:
    img_file = data_dir / "annotated_with_data/apc2016_obj3.jpg"
    img_arr = np.asarray(PIL.Image.open(img_file))
    img_b64 = image_module.img_arr_to_b64(img_arr)
    img_arr2 = image_module.img_b64_to_arr(img_b64)
    np.testing.assert_allclose(img_arr, img_arr2)


def test_img_data_to_png_data() -> None:
    img_file = data_dir / "annotated_with_data/apc2016_obj3.jpg"
    img_data = img_file.read_bytes()
    png_data = image_module.img_data_to_png_data(img_data)
    assert png_data[:8] == b"\x89PNG\r\n\x1a\n"
    np.testing.assert_array_equal(
        np.asarray(PIL.Image.open(io.BytesIO(png_data))),
        np.asarray(PIL.Image.open(io.BytesIO(img_data))),
        err_msg="pixels must survive the PNG re-encode",
    )


def _make_jpeg_with_red_marker(orientation: int) -> PIL.Image.Image:
    # Round-trip through JPEG so apply_exif_orientation can read the EXIF
    # Orientation tag; pin quality so the red marker stays the brightest pixel.
    ORIENTATION_TAG: Final = 274  # EXIF Orientation tag (0x0112)
    arr = np.zeros((2, 3, 3), dtype=np.uint8)
    arr[0, 0] = [255, 0, 0]
    img = PIL.Image.fromarray(arr)
    exif = img.getexif()
    exif[ORIENTATION_TAG] = orientation
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif.tobytes(), quality=95, subsampling=0)
    buf.seek(0)
    return PIL.Image.open(buf)


def _find_brightest_red_rowcol(image: PIL.Image.Image) -> tuple[int, int]:
    red = np.asarray(image)[:, :, 0]
    row, col = np.unravel_index(red.argmax(), red.shape)
    return int(row), int(col)


@pytest.mark.parametrize(
    ("orientation", "expected_size", "expected_rowcol"),
    [
        pytest.param(1, (3, 2), (0, 0), id="identity"),
        pytest.param(2, (3, 2), (0, 2), id="mirror-left-right"),
        pytest.param(3, (3, 2), (1, 2), id="rotate-180"),
        pytest.param(4, (3, 2), (1, 0), id="mirror-top-bottom"),
        pytest.param(5, (2, 3), (0, 0), id="transpose"),
        pytest.param(6, (2, 3), (0, 1), id="rotate-270"),
        pytest.param(7, (2, 3), (2, 1), id="transverse"),
        pytest.param(8, (2, 3), (2, 0), id="rotate-90"),
    ],
)
def test_apply_exif_orientation_transforms_marker(
    orientation: int,
    expected_size: tuple[int, int],
    expected_rowcol: tuple[int, int],
) -> None:
    out = image_module.apply_exif_orientation(
        _make_jpeg_with_red_marker(orientation=orientation)
    )
    assert out.size == expected_size
    assert _find_brightest_red_rowcol(out) == expected_rowcol


def test_apply_exif_orientation_passes_through_image_without_exif() -> None:
    arr = np.zeros((4, 4, 3), dtype=np.uint8)
    arr[0, 0] = [255, 0, 0]  # asymmetric marker so a wrongful transform is caught
    out = image_module.apply_exif_orientation(PIL.Image.fromarray(arr))
    np.testing.assert_array_equal(np.asarray(out), arr)


def test_apply_exif_orientation_passes_through_jpeg_without_exif() -> None:
    arr = np.zeros((4, 4, 3), dtype=np.uint8)
    buf = io.BytesIO()
    PIL.Image.fromarray(arr).save(buf, format="JPEG", quality=95, subsampling=0)
    buf.seek(0)
    jpeg = PIL.Image.open(buf)
    assert image_module.apply_exif_orientation(jpeg) is jpeg
