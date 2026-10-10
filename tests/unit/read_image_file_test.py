from __future__ import annotations

import io
import struct
import zlib
from pathlib import Path

import numpy as np
import PIL.Image
import pytest
import tifffile

from labelme._label_file import RASTER_MAX_SIDE
from labelme._label_file import ImageTooLargeError
from labelme._label_file import read_image_file


def _make_image(tmp_path: Path, /, *, filename: str, mode: str) -> Path:
    channels = 4 if mode == "RGBA" else 3
    arr = np.random.randint(0, 255, (100, 100, channels), dtype=np.uint8)
    path = tmp_path / filename
    PIL.Image.fromarray(arr, mode=mode).save(str(path))
    return path


def test_tiff_without_alpha_encoded_as_jpeg(*, tmp_path: Path) -> None:
    path = _make_image(tmp_path, filename="test.tiff", mode="RGB")
    data = read_image_file(filename=str(path))
    assert data[:2] == b"\xff\xd8"


def test_tiff_with_alpha_encoded_as_png(*, tmp_path: Path) -> None:
    path = _make_image(tmp_path, filename="test.tiff", mode="RGBA")
    data = read_image_file(filename=str(path))
    assert data[:4] == b"\x89PNG"


def test_corrupt_tiff_raises_os_error(*, tmp_path: Path) -> None:
    path = tmp_path / "corrupt.tiff"
    path.write_bytes(b"II*\x00")

    with pytest.raises(OSError, match="failed to read image"):
        read_image_file(filename=str(path))


def test_jpeg_returns_raw_bytes(*, tmp_path: Path) -> None:
    path = _make_image(tmp_path, filename="test.jpg", mode="RGB")
    data = read_image_file(filename=str(path))
    assert data == path.read_bytes()


def test_png_returns_raw_bytes(*, tmp_path: Path) -> None:
    path = _make_image(tmp_path, filename="test.png", mode="RGB")
    data = read_image_file(filename=str(path))
    assert data == path.read_bytes()


@pytest.mark.parametrize("ext", ["gif", "bmp"])
def test_palette_image_without_alpha_encoded_as_jpeg(
    *, tmp_path: Path, ext: str
) -> None:
    arr = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
    path = tmp_path / f"test.{ext}"
    PIL.Image.fromarray(arr, mode="RGB").convert("P").save(str(path))
    with PIL.Image.open(path) as image:
        assert image.mode == "P"

    data = read_image_file(filename=str(path))
    assert data[:2] == b"\xff\xd8"


def test_transparent_palette_gif_encoded_as_png(*, tmp_path: Path) -> None:
    arr = np.random.randint(0, 255, (100, 100, 4), dtype=np.uint8)
    arr[:20, :20, 3] = 0
    path = tmp_path / "test.gif"
    PIL.Image.fromarray(arr, mode="RGBA").save(str(path), transparency=0)
    with PIL.Image.open(path) as image:
        assert image.mode == "P"
        assert "transparency" in image.info

    data = read_image_file(filename=str(path))
    assert data[:4] == b"\x89PNG"
    with PIL.Image.open(io.BytesIO(data)) as image:
        assert "transparency" in image.info


def test_palette_with_alpha_tiff_encoded_as_png(*, tmp_path: Path) -> None:
    path = tmp_path / "test.tiff"
    PIL.Image.new("PA", (100, 100)).save(str(path))
    with PIL.Image.open(path) as image:
        assert image.mode == "PA"

    data = read_image_file(filename=str(path))
    assert data[:4] == b"\x89PNG"


def test_bilevel_image_encoded_as_jpeg_without_widening(*, tmp_path: Path) -> None:
    path = tmp_path / "test.bmp"
    PIL.Image.new("1", (100, 100)).save(str(path))
    with PIL.Image.open(path) as image:
        assert image.mode == "1"

    data = read_image_file(filename=str(path))
    assert data[:2] == b"\xff\xd8"
    with PIL.Image.open(io.BytesIO(data)) as image:
        assert image.mode == "L"


def test_multispectral_tiff_float32(*, tmp_path: Path) -> None:
    arr = np.random.rand(64, 64, 5).astype(np.float32) * 0.5
    path = tmp_path / "multispectral.tif"
    tifffile.imwrite(str(path), arr)

    data = read_image_file(filename=str(path))
    assert data[:2] == b"\xff\xd8"

    with PIL.Image.open(io.BytesIO(data)) as image:
        assert image.mode == "RGB"
        assert image.size == (64, 64)


def test_grayscale_tiff_float32(*, tmp_path: Path) -> None:
    arr = np.random.rand(64, 64).astype(np.float32)
    path = tmp_path / "grayscale.tif"
    tifffile.imwrite(str(path), arr)

    data = read_image_file(filename=str(path))
    with PIL.Image.open(io.BytesIO(data)) as image:
        assert image.size == (64, 64)


def test_constant_value_tiff_returns_black(*, tmp_path: Path) -> None:
    arr = np.full((64, 64), 42.0, dtype=np.float32)
    path = tmp_path / "constant.tif"
    tifffile.imwrite(str(path), arr)

    data = read_image_file(filename=str(path))
    with PIL.Image.open(io.BytesIO(data)) as image:
        assert image.size == (64, 64)
        assert np.array(image).max() == 0


def test_two_band_tiff_falls_back_to_first_band(*, tmp_path: Path) -> None:
    arr = np.random.rand(64, 64, 2).astype(np.float32)
    path = tmp_path / "twoband.tif"
    tifffile.imwrite(str(path), arr)

    data = read_image_file(filename=str(path))
    with PIL.Image.open(io.BytesIO(data)) as image:
        assert image.size == (64, 64)


def test_read_image_file_rejects_oversized_png_from_header(*, tmp_path: Path) -> None:
    def make_chunk(chunk_type: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + chunk_type
            + data
            + struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", 37296, 49319, 8, 2, 0, 0, 0)
    png_bytes = (
        b"\x89PNG\r\n\x1a\n"
        + make_chunk(b"IHDR", ihdr)
        + make_chunk(b"IDAT", b"")
        + make_chunk(b"IEND", b"")
    )
    path = tmp_path / "oversized.png"
    path.write_bytes(png_bytes)

    with pytest.raises(ImageTooLargeError) as exc_info:
        read_image_file(filename=str(path))

    assert exc_info.value.width == 37296
    assert exc_info.value.height == 49319
    assert exc_info.value.max_side == RASTER_MAX_SIDE
    assert "37296x49319" in str(exc_info.value)
    assert str(RASTER_MAX_SIDE) in str(exc_info.value)
    assert "gdal_retile.py" in str(exc_info.value)


def test_read_image_file_rejects_oversized_tiff_from_header(*, tmp_path: Path) -> None:
    # Little-endian TIFF header: 'II', 42, IFD offset 8
    header = b"II\x2a\x00\x08\x00\x00\x00"
    num_tags = struct.pack("<H", 2)
    # Tag 256: ImageWidth LONG=49319, Tag 257: ImageLength LONG=37296
    tag_width = struct.pack("<HHII", 256, 4, 1, 49319)
    tag_height = struct.pack("<HHII", 257, 4, 1, 37296)
    next_ifd = b"\x00\x00\x00\x00"
    tiff_bytes = header + num_tags + tag_width + tag_height + next_ifd

    path = tmp_path / "oversized.tif"
    path.write_bytes(tiff_bytes)

    with pytest.raises(ImageTooLargeError) as exc_info:
        read_image_file(filename=str(path))

    assert exc_info.value.width == 49319
    assert exc_info.value.height == 37296
    assert exc_info.value.max_side == RASTER_MAX_SIDE
    assert "49319x37296" in str(exc_info.value)
