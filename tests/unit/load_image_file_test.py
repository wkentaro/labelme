from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import PIL.Image
import tifffile

from labelme._label_file import LabelFile


def _make_image(tmp_path: Path, filename: str, mode: str = "RGB", size=(100, 100)):
    channels = 4 if mode == "RGBA" else 3
    arr = np.random.randint(0, 255, (size[1], size[0], channels), dtype=np.uint8)
    path = tmp_path / filename
    PIL.Image.fromarray(arr, mode=mode).save(str(path))
    return path


def test_tiff_without_alpha_encoded_as_jpeg(tmp_path):
    path = _make_image(tmp_path, "test.tiff")
    data = LabelFile.load_image_file(str(path))
    assert data[:2] == b"\xff\xd8"


def test_tiff_with_alpha_encoded_as_png(tmp_path):
    path = _make_image(tmp_path, "test.tiff", mode="RGBA")
    data = LabelFile.load_image_file(str(path))
    assert data[:4] == b"\x89PNG"


def test_jpeg_returns_raw_bytes(tmp_path):
    path = _make_image(tmp_path, "test.jpg")
    data = LabelFile.load_image_file(str(path))
    assert data == path.read_bytes()


def test_png_returns_raw_bytes(tmp_path):
    path = _make_image(tmp_path, "test.png")
    data = LabelFile.load_image_file(str(path))
    assert data == path.read_bytes()


def test_multispectral_tiff_float32(tmp_path):
    arr = np.random.rand(64, 64, 5).astype(np.float32) * 0.5
    path = tmp_path / "multispectral.tif"
    tifffile.imwrite(str(path), arr)

    data = LabelFile.load_image_file(str(path))
    assert data[:2] == b"\xff\xd8"

    img = PIL.Image.open(io.BytesIO(data))
    assert img.mode == "RGB"
    assert img.size == (64, 64)


def test_grayscale_tiff_float32(tmp_path):
    arr = np.random.rand(64, 64).astype(np.float32)
    path = tmp_path / "grayscale.tif"
    tifffile.imwrite(str(path), arr)

    data = LabelFile.load_image_file(str(path))
    img = PIL.Image.open(io.BytesIO(data))
    assert img.size == (64, 64)


def test_two_band_tiff_falls_back_to_first_band(tmp_path):
    arr = np.random.rand(64, 64, 2).astype(np.float32)
    path = tmp_path / "twoband.tif"
    tifffile.imwrite(str(path), arr)

    data = LabelFile.load_image_file(str(path))
    img = PIL.Image.open(io.BytesIO(data))
    assert img.size == (64, 64)
