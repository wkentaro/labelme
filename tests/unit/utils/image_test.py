import io

import numpy as np
import PIL.Image
import pytest

from labelme.utils import image as image_module

from .util import data_dir
from .util import get_img_and_data


def test_img_b64_to_arr():
    img, _ = get_img_and_data()
    assert img.dtype == np.uint8
    assert img.shape == (907, 1210, 3)


def test_img_arr_to_b64():
    img_file = data_dir / "annotated_with_data/apc2016_obj3.jpg"
    img_arr = np.asarray(PIL.Image.open(img_file))
    img_b64 = image_module.img_arr_to_b64(img_arr)
    img_arr2 = image_module.img_b64_to_arr(img_b64)
    np.testing.assert_allclose(img_arr, img_arr2)


def test_img_data_to_png_data():
    img_file = data_dir / "annotated_with_data/apc2016_obj3.jpg"
    with open(img_file, "rb") as f:
        img_data = f.read()
    png_data = image_module.img_data_to_png_data(img_data)
    assert isinstance(png_data, bytes)


# --- edge cases ---


def _make_png_bytes(arr):
    """Helper: numpy array → PNG bytes."""
    img_pil = PIL.Image.fromarray(arr)
    buf = io.BytesIO()
    img_pil.save(buf, format="PNG")
    return buf.getvalue()


def test_img_data_to_pil_returns_pil_image():
    arr = np.zeros((4, 4, 3), dtype=np.uint8)
    png_bytes = _make_png_bytes(arr)
    img_pil = image_module.img_data_to_pil(png_bytes)
    assert isinstance(img_pil, PIL.Image.Image)


def test_img_data_to_pil_invalid_bytes_raises():
    with pytest.raises(Exception):
        image_module.img_data_to_pil(b"not_an_image")


def test_img_data_to_arr_shape():
    arr = np.ones((8, 6, 3), dtype=np.uint8) * 128
    png_bytes = _make_png_bytes(arr)
    result = image_module.img_data_to_arr(png_bytes)
    assert result.shape == (8, 6, 3)
    assert result.dtype == np.uint8


def test_img_pil_to_data_roundtrip():
    """img_pil_to_data -> img_data_to_pil should return an equivalent image."""
    arr = np.arange(48, dtype=np.uint8).reshape(4, 4, 3)
    img_pil = PIL.Image.fromarray(arr)
    img_data = image_module.img_pil_to_data(img_pil)
    img_pil2 = image_module.img_data_to_pil(img_data)
    np.testing.assert_array_equal(np.asarray(img_pil), np.asarray(img_pil2))


def test_img_arr_to_data_returns_bytes():
    arr = np.zeros((4, 4, 3), dtype=np.uint8)
    data = image_module.img_arr_to_data(arr)
    assert isinstance(data, bytes)
    # should be a valid PNG
    img = PIL.Image.open(io.BytesIO(data))
    assert img.size == (4, 4)


def test_img_arr_to_b64_grayscale_roundtrip():
    """Grayscale (2-D) arrays survive a b64 encode/decode cycle."""
    arr = np.arange(256, dtype=np.uint8).reshape(16, 16)
    img_b64 = image_module.img_arr_to_b64(arr)
    arr2 = image_module.img_b64_to_arr(img_b64)
    np.testing.assert_array_equal(arr, arr2)


def test_img_arr_to_b64_rgba_roundtrip():
    """RGBA (4-channel) arrays survive a b64 encode/decode cycle."""
    arr = np.zeros((4, 4, 4), dtype=np.uint8)
    arr[:, :, 3] = 255  # fully opaque alpha channel
    img_b64 = image_module.img_arr_to_b64(arr)
    arr2 = image_module.img_b64_to_arr(img_b64)
    np.testing.assert_array_equal(arr, arr2)


def test_apply_exif_orientation_no_exif_returns_same():
    """PNG images have no EXIF; function must return the image unchanged."""
    arr = np.arange(48, dtype=np.uint8).reshape(4, 4, 3)
    img_pil = PIL.Image.fromarray(arr)
    result = image_module.apply_exif_orientation(img_pil)
    np.testing.assert_array_equal(np.asarray(img_pil), np.asarray(result))


def test_img_data_to_png_data_is_png():
    """Converted PNG data should start with the PNG magic bytes."""
    img_file = data_dir / "annotated_with_data/apc2016_obj3.jpg"
    with open(img_file, "rb") as f:
        img_data = f.read()
    png_data = image_module.img_data_to_png_data(img_data)
    assert png_data[:8] == b"\x89PNG\r\n\x1a\n", "output must be a valid PNG"
