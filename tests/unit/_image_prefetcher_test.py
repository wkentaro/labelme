from __future__ import annotations

from pathlib import Path

import numpy as np
import PIL.Image
import pytest
from PySide6 import QtGui

from labelme._image_prefetcher import ImagePrefetcher


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
