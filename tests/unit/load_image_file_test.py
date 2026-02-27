from __future__ import annotations

from pathlib import Path

import numpy as np
import PIL.Image

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
