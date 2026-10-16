from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import PIL.Image
import pytest
from PySide6 import QtGui

from labelme import _image_prefetcher
from labelme._image_prefetcher import ImagePrefetcher
from labelme._label_file import read_image_file


@pytest.mark.usefixtures("qapp")
def test_prefetched_image_matches_decode_and_misses_changed_file(
    *, tmp_path: Path
) -> None:
    paths = []
    for i in range(3):
        path = tmp_path / f"{i}.jpg"
        PIL.Image.fromarray(np.full((8, 8, 3), i * 80, dtype=np.uint8)).save(path)
        paths.append(str(path))

    prefetcher = ImagePrefetcher()
    try:
        prefetcher.retain(current=None, neighbors=paths[:2])
        data = Path(paths[0]).read_bytes()
        image = prefetcher.take(image_path=paths[0], image_data=data)
        assert image is not None
        assert image == QtGui.QImage.fromData(data)

        # Stale bytes miss rather than show an outdated image.
        assert prefetcher.take(image_path=paths[1], image_data=data) is None
        # Only retained images are kept.
        assert prefetcher.take(image_path=paths[2], image_data=data) is None
        prefetcher.retain(current=(paths[0], data, image), neighbors=[])
        assert prefetcher.take(image_path=paths[0], image_data=data) is image

        # Formats the loader re-encodes decode on demand instead.
        tiff = tmp_path / "3.tiff"
        PIL.Image.open(paths[2]).save(tiff)
        prefetcher.retain(current=None, neighbors=[str(tiff)])
        assert prefetcher.take(image_path=str(tiff), image_data=data) is None
    finally:
        prefetcher.shutdown()


@pytest.mark.usefixtures("qapp")
def test_decode_rejects_file_replaced_after_reader_opened(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "a.png"
    PIL.Image.new("RGB", (8, 8), (255, 0, 0)).save(path)
    replacement = tmp_path / "b.png"
    PIL.Image.new("RGB", (8, 8), (0, 0, 255)).save(replacement)

    def replace_then_read(*, filename: str) -> bytes:
        # Atomic replacement while the reader holds the red file open.
        os.replace(replacement, filename)
        return read_image_file(filename=filename)

    monkeypatch.setattr(_image_prefetcher, "read_image_file", replace_then_read)
    assert _image_prefetcher._decode(str(path)) is None


@pytest.mark.usefixtures("qapp")
def test_retain_drops_current_image_over_cap(*, tmp_path: Path) -> None:
    # 6000 x 6000 at 32 bits per pixel is about 137 MB, over the 128 MB cap.
    image = QtGui.QImage(6000, 6000, QtGui.QImage.Format.Format_RGB32)
    path = str(tmp_path / "big.png")
    prefetcher = ImagePrefetcher()
    try:
        prefetcher.retain(current=(path, b"data", image), neighbors=[])
        assert prefetcher.take(image_path=path, image_data=b"data") is None
    finally:
        prefetcher.shutdown()


@pytest.mark.usefixtures("qapp")
def test_decode_skips_exif_rotated_image_before_converting(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "rotated.jpg"
    exif = PIL.Image.Exif()
    exif[0x0112] = 6  # Orientation: rotate 90 degrees clockwise
    PIL.Image.new("RGB", (8, 4)).save(path, exif=exif)

    def fail(*, filename: str) -> bytes:
        raise AssertionError(f"converted {filename}")

    monkeypatch.setattr(_image_prefetcher, "read_image_file", fail)
    assert _image_prefetcher._decode(str(path)) is None
