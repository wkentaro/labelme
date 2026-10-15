from __future__ import annotations

from concurrent.futures import Future
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Final

from loguru import logger
from PySide6 import QtGui

from ._label_file import read_image_file
from ._utils import get_reader_decode_requirement

_Decoded = tuple[bytes, QtGui.QImage] | None


def _decode(image_path: str, /) -> _Decoded:
    # A neighbor larger than this decodes on demand instead, so two prefetched
    # neighbors stay within a few hundred MB.
    # ponytail: fixed cap, derive it from free memory if large images need prefetch.
    MAX_PREFETCH_MB: Final = 128

    # A re-encoded image (EXIF rotation, TIFF, ...) would need decoding from
    # memory, through a Python-wrapped QBuffer whose virtual calls take the GIL
    # inside Qt's locks and can deadlock the GUI thread. Decode only files the
    # loader uses as-is, straight from disk, and skip other formats before
    # the loader converts them.
    if Path(image_path).suffix.lower() not in (".jpg", ".jpeg", ".png"):
        return None
    # QImage.fromData decodes through this same reader, so a prefetched image
    # is pixel-identical; unlike fromData, read() releases the GIL.
    reader = QtGui.QImageReader(image_path)
    requirement = get_reader_decode_requirement(reader=reader)
    if requirement is None or requirement.required_mb > MAX_PREFETCH_MB:
        return None
    try:
        image_data = read_image_file(filename=image_path)
        if _read_bytes(image_path) != image_data:
            return None
        image = reader.read()
        # The file may have changed while the reader decoded it.
        if image.isNull() or _read_bytes(image_path) != image_data:
            return None
    except OSError as e:
        logger.debug("Skipped prefetching {!r}: {}", image_path, e)
        return None
    return image_data, image


def _read_bytes(path: str, /) -> bytes:
    with open(path, "rb") as f:
        return f.read()


class ImagePrefetcher:
    """Decodes the images next to the current one off the GUI thread."""

    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="image-prefetch"
        )
        self._decoded: dict[str, Future[_Decoded]] = {}

    def retain(
        self,
        *,
        current: tuple[str, bytes, QtGui.QImage] | None,
        neighbors: list[str],
    ) -> None:
        # Keeps exactly these images, so memory stays bounded however far the
        # user navigates; the current one stays decoded for stepping back.
        decoded: dict[str, Future[_Decoded]] = {}
        if current is not None:
            path, image_data, image = current
            decoded[path] = Future()
            decoded[path].set_result((image_data, image))
        for path in neighbors:
            if path not in decoded:
                decoded[path] = self._decoded.pop(path, None) or self._executor.submit(
                    _decode, path
                )
        for future in self._decoded.values():
            future.cancel()
        self._decoded = decoded

    def take(self, *, image_path: str, image_data: bytes) -> QtGui.QImage | None:
        future = self._decoded.get(image_path)
        if future is None:
            return None
        # Waiting on an in-flight decode beats starting a second one.
        decoded = future.result()
        # The file may have changed since it was prefetched.
        if decoded is None or decoded[0] != image_data:
            return None
        return decoded[1]

    def shutdown(self) -> None:
        self._decoded = {}
        # An in-flight decode must not outlive the QApplication.
        self._executor.shutdown(wait=True, cancel_futures=True)
