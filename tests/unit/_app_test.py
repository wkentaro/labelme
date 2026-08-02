from __future__ import annotations

import pytest
from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from labelme import __appname__
from labelme import _app
from labelme import _automation


@pytest.mark.parametrize(
    "create_mode, ai_output_format, expected",
    [
        ("ai_points_to_shape", "mask", "mask"),
        ("ai_box_to_shape", "polygon", "polygon"),
        ("polygon", "mask", "polygon"),
        ("rectangle", "mask", "rectangle"),
        ("edit", "polygon", None),
    ],
    ids=[
        "ai-points-passthrough",
        "ai-box-passthrough",
        "text-polygon",
        "text-rectangle",
        "unrelated-mode",
    ],
)
def test_resolve_text_annotation_shape_type(
    create_mode: str,
    ai_output_format: _automation.AiOutputFormat,
    expected: _automation.AiOutputFormat | None,
) -> None:
    assert (
        _app._resolve_text_annotation_shape_type(
            create_mode=create_mode, ai_output_format=ai_output_format
        )
        == expected
    )


@pytest.mark.parametrize(
    "label, existing_labels, policy, expected",
    [
        ("cat", [], None, True),
        ("cat", ["cat"], "exact", True),
        ("cat", ["dog"], "exact", False),
        ("cat", ["cat"], "unknown", False),
    ],
    ids=["policy-none", "exact-match", "exact-no-match", "unknown-policy"],
)
def test_is_valid_label(
    label: str, existing_labels: list[str], policy: str | None, expected: bool
) -> None:
    assert (
        _app._is_valid_label(
            label=label, existing_labels=existing_labels, policy=policy
        )
        is expected
    )


@pytest.mark.parametrize(
    "image_path, file_index, file_count, dirty, expected",
    [
        (None, None, 0, False, __appname__),
        ("img.png", None, 0, False, f"{__appname__} - img.png"),
        ("img.png", 1, 5, False, f"{__appname__} - img.png [2/5]"),
        ("img.png", 0, 5, False, f"{__appname__} - img.png [1/5]"),
        ("img.png", 0, 0, False, f"{__appname__} - img.png"),
        ("img.png", None, 5, False, f"{__appname__} - img.png"),
        ("img.png", 1, 5, True, f"{__appname__} - img.png [2/5]*"),
        (None, None, 0, True, f"{__appname__}*"),
        ("img.png", None, 0, True, f"{__appname__} - img.png*"),
    ],
    ids=[
        "appname-only",
        "path-no-index",
        "path-with-index",
        "first-file-index-zero",
        "index-set-count-zero",
        "count-set-no-index",
        "path-index-dirty",
        "appname-dirty",
        "path-dirty",
    ],
)
def test_format_window_title(
    image_path: str | None,
    file_index: int | None,
    file_count: int,
    dirty: bool,
    expected: str,
) -> None:
    assert (
        _app._format_window_title(
            image_path=image_path,
            file_index=file_index,
            file_count=file_count,
            dirty=dirty,
        )
        == expected
    )


def _png_bytes(*, width: int, height: int) -> bytes:
    image = QtGui.QImage(width, height, QtGui.QImage.Format.Format_RGB32)
    image.fill(0)
    buffer = QtCore.QBuffer()
    buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")  # ty: ignore[no-matching-overload]
    return bytes(buffer.data())  # ty: ignore[invalid-argument-type]


def test_image_too_large_message_explains_allocation_limit(
    qapp: QtWidgets.QApplication,
) -> None:
    image_data = _png_bytes(width=800, height=600)
    original_limit = QtGui.QImageReader.allocationLimit()
    try:
        QtGui.QImageReader.setAllocationLimit(1)
        assert QtGui.QImage.fromData(image_data).isNull()
        message = _app._image_too_large_message(image_data=image_data)
    finally:
        QtGui.QImageReader.setAllocationLimit(original_limit)

    assert message is not None
    assert "800x600" in message
    assert "1 MB" in message
    assert "gdal_retile.py" in message


def test_image_too_large_message_reports_per_side_limit(
    qapp: QtWidgets.QApplication,
) -> None:
    class _Size:
        def isValid(self) -> bool:
            return True

        def width(self) -> int:
            return 37296

        def height(self) -> int:
            return 49319

    class _Reader:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def size(self) -> _Size:
            return _Size()

    original_reader = _app.QtGui.QImageReader
    try:
        _app.QtGui.QImageReader = _Reader  # ty: ignore[invalid-assignment]
        message = _app._image_too_large_message(image_data=b"")
    finally:
        _app.QtGui.QImageReader = original_reader

    assert message is not None
    assert "37296x49319" in message
    assert "32767" in message
    assert "gdal_retile.py" in message


def test_image_too_large_message_is_none_for_undecodable_data(
    qapp: QtWidgets.QApplication,
) -> None:
    assert _app._image_too_large_message(image_data=b"not an image") is None


def test_image_too_large_message_is_none_within_allocation_limit(
    qapp: QtWidgets.QApplication,
) -> None:
    assert (
        _app._image_too_large_message(image_data=_png_bytes(width=8, height=8)) is None
    )
