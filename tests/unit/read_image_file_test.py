from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import PIL.Image
import pytest
import tifffile

from labelme._label_file import read_image_file


def _make_image(
    tmp_path: Path, filename: str, mode: str = "RGB", size: tuple[int, int] = (100, 100)
) -> Path:
    channels = 4 if mode == "RGBA" else 3
    arr = np.random.randint(0, 255, (size[1], size[0], channels), dtype=np.uint8)
    path = tmp_path / filename
    PIL.Image.fromarray(arr, mode=mode).save(str(path))
    return path


def test_tiff_without_alpha_encoded_as_jpeg(tmp_path: Path) -> None:
    path = _make_image(tmp_path, "test.tiff")
    data = read_image_file(filename=str(path))
    assert data[:2] == b"\xff\xd8"


def test_tiff_with_alpha_encoded_as_png(tmp_path: Path) -> None:
    path = _make_image(tmp_path, "test.tiff", mode="RGBA")
    data = read_image_file(filename=str(path))
    assert data[:4] == b"\x89PNG"


def test_jpeg_returns_raw_bytes(tmp_path: Path) -> None:
    path = _make_image(tmp_path, "test.jpg")
    data = read_image_file(filename=str(path))
    assert data == path.read_bytes()


def test_png_returns_raw_bytes(tmp_path: Path) -> None:
    path = _make_image(tmp_path, "test.png")
    data = read_image_file(filename=str(path))
    assert data == path.read_bytes()


@pytest.mark.parametrize("ext", ["gif", "bmp"])
def test_palette_image_without_alpha_encoded_as_jpeg(tmp_path: Path, ext: str) -> None:
    arr = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
    path = tmp_path / f"test.{ext}"
    PIL.Image.fromarray(arr, mode="RGB").convert("P").save(str(path))
    assert PIL.Image.open(str(path)).mode == "P"

    data = read_image_file(filename=str(path))
    assert data[:2] == b"\xff\xd8"


def test_transparent_palette_gif_encoded_as_png(tmp_path: Path) -> None:
    arr = np.random.randint(0, 255, (100, 100, 4), dtype=np.uint8)
    arr[:20, :20, 3] = 0
    path = tmp_path / "test.gif"
    PIL.Image.fromarray(arr, mode="RGBA").save(str(path), transparency=0)
    reopened = PIL.Image.open(str(path))
    assert reopened.mode == "P"
    assert "transparency" in reopened.info

    data = read_image_file(filename=str(path))
    assert data[:4] == b"\x89PNG"
    assert "transparency" in PIL.Image.open(io.BytesIO(data)).info


def test_palette_with_alpha_tiff_encoded_as_png(tmp_path: Path) -> None:
    path = tmp_path / "test.tiff"
    PIL.Image.new("PA", (100, 100)).save(str(path))
    assert PIL.Image.open(str(path)).mode == "PA"

    data = read_image_file(filename=str(path))
    assert data[:4] == b"\x89PNG"


def test_bilevel_image_encoded_as_jpeg_without_widening(tmp_path: Path) -> None:
    path = tmp_path / "test.bmp"
    PIL.Image.new("1", (100, 100)).save(str(path))
    assert PIL.Image.open(str(path)).mode == "1"

    data = read_image_file(filename=str(path))
    assert data[:2] == b"\xff\xd8"
    assert PIL.Image.open(io.BytesIO(data)).mode == "L"


def test_multispectral_tiff_float32(tmp_path: Path) -> None:
    arr = np.random.rand(64, 64, 5).astype(np.float32) * 0.5
    path = tmp_path / "multispectral.tif"
    tifffile.imwrite(str(path), arr)

    data = read_image_file(filename=str(path))
    assert data[:2] == b"\xff\xd8"

    img = PIL.Image.open(io.BytesIO(data))
    assert img.mode == "RGB"
    assert img.size == (64, 64)


def test_grayscale_tiff_float32(tmp_path: Path) -> None:
    arr = np.random.rand(64, 64).astype(np.float32)
    path = tmp_path / "grayscale.tif"
    tifffile.imwrite(str(path), arr)

    data = read_image_file(filename=str(path))
    img = PIL.Image.open(io.BytesIO(data))
    assert img.size == (64, 64)


def test_constant_value_tiff_returns_black(tmp_path: Path) -> None:
    arr = np.full((64, 64), 42.0, dtype=np.float32)
    path = tmp_path / "constant.tif"
    tifffile.imwrite(str(path), arr)

    data = read_image_file(filename=str(path))
    img = PIL.Image.open(io.BytesIO(data))
    assert img.size == (64, 64)
    assert np.array(img).max() == 0


def test_two_band_tiff_falls_back_to_first_band(tmp_path: Path) -> None:
    arr = np.random.rand(64, 64, 2).astype(np.float32)
    path = tmp_path / "twoband.tif"
    tifffile.imwrite(str(path), arr)

    data = read_image_file(filename=str(path))
    img = PIL.Image.open(io.BytesIO(data))
    assert img.size == (64, 64)
