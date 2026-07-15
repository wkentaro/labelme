from __future__ import annotations

import struct
import zlib
from collections.abc import Callable

import numpy as np
import pytest
from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from labelme import __appname__
from labelme import _app
from labelme import _automation
from labelme._label_file import ShapeDict


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


def _make_png_bytes(
    *,
    width: int,
    height: int,
    image_format: QtGui.QImage.Format = QtGui.QImage.Format.Format_RGB32,
) -> bytes:
    image = QtGui.QImage(width, height, image_format)
    image.fill(0)
    buffer = QtCore.QBuffer()
    buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")  # ty: ignore[no-matching-overload]
    return bytes(buffer.data())  # ty: ignore[invalid-argument-type]


def test_make_image_too_large_message_explains_allocation_limit(
    set_allocation_limit: Callable[[int], None],
) -> None:
    image_data = _make_png_bytes(width=800, height=600)
    set_allocation_limit(1)
    assert QtGui.QImage.fromData(image_data).isNull()

    message = _app._make_image_too_large_message(image_data=image_data)

    assert message is not None
    assert "800x600" in message
    assert "1 MB" in message
    assert "gdal_retile.py" in message


def test_make_image_too_large_message_accounts_for_bit_depth(
    set_allocation_limit: Callable[[int], None],
) -> None:
    # 800x600 at 16 bits per channel decodes to 8 bytes/pixel (~3.7 MB), so a
    # 2 MB limit rejects it even though a flat 4-bytes/pixel estimate
    # (~1.8 MB) would wrongly conclude it fits.
    image_data = _make_png_bytes(
        width=800, height=600, image_format=QtGui.QImage.Format.Format_RGBA64
    )
    set_allocation_limit(2)
    assert QtGui.QImage.fromData(image_data).isNull()

    message = _app._make_image_too_large_message(image_data=image_data)

    assert message is not None
    assert "800x600" in message
    assert "4 MB" in message
    assert "2 MB" in message


def test_make_image_too_large_message_reports_per_side_limit(
    qapp: QtWidgets.QApplication,
) -> None:
    # A hand-built PNG whose header claims the dimensions from #2388 but
    # carries no pixel data: QImageReader reads the size from the header
    # alone, so the real decode path runs without a multi-GB allocation.
    def make_chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload))
        )

    ihdr = struct.pack(">IIBBBBB", 37296, 49319, 8, 2, 0, 0, 0)
    image_data = (
        b"\x89PNG\r\n\x1a\n"
        + make_chunk(b"IHDR", ihdr)
        + make_chunk(b"IDAT", b"")
        + make_chunk(b"IEND", b"")
    )

    message = _app._make_image_too_large_message(image_data=image_data)

    assert message is not None
    assert "37296x49319" in message
    assert "32767" in message
    assert "gdal_retile.py" in message


def test_make_image_too_large_message_rounds_the_need_up(
    set_allocation_limit: Callable[[int], None],
) -> None:
    # 800x680 at 4 bytes/pixel needs ~2.1 MB: over a 2 MB limit, but plain
    # round() would render the contradictory "needs about 2 MB, but the
    # decode limit is 2 MB".
    image_data = _make_png_bytes(width=800, height=680)
    set_allocation_limit(2)
    assert QtGui.QImage.fromData(image_data).isNull()

    message = _app._make_image_too_large_message(image_data=image_data)

    assert message is not None
    assert "3 MB" in message
    assert "2 MB" in message


def test_make_image_too_large_message_is_none_for_undecodable_data(
    qapp: QtWidgets.QApplication,
) -> None:
    assert _app._make_image_too_large_message(image_data=b"not an image") is None


def test_make_image_too_large_message_is_none_within_allocation_limit(
    qapp: QtWidgets.QApplication,
) -> None:
    assert (
        _app._make_image_too_large_message(
            image_data=_make_png_bytes(width=8, height=8)
        )
        is None
    )


def _make_shape_dict(*, label: str, flags: dict[str, bool]) -> ShapeDict:
    return ShapeDict(
        label=label,
        points=[[0.0, 0.0], [10.0, 20.0]],
        shape_type="rectangle",
        flags=flags,
        description="",
        group_id=None,
        mask=None,
        other_data={},
    )


@pytest.mark.parametrize(
    "label, saved_flags, label_flags, expected",
    [
        (
            "cat",
            {},
            {"^cat$": ["occluded", "truncated"]},
            {"occluded": False, "truncated": False},
        ),
        (
            "cat",
            {"occluded": True},
            {"^cat$": ["occluded", "truncated"]},
            {"occluded": True, "truncated": False},
        ),
        (
            "cat",
            {"reviewed": True},
            {"^cat$": ["occluded"]},
            {"occluded": False, "reviewed": True},
        ),
        ("dog", {}, {"^cat$": ["occluded"]}, {}),
        ("bigcat", {}, {"cat$": ["occluded"]}, {}),
        (
            "cat",
            {},
            {"^cat$": ["occluded"], "^ca": ["blurry"], "^dog$": ["truncated"]},
            {"occluded": False, "blurry": False},
        ),
        ("cat", {"occluded": True}, None, {"occluded": True}),
        ("cat", {"occluded": True}, {}, {"occluded": True}),
        ("cat", {}, {"cat(": ["occluded"]}, {}),
        (
            "cat",
            {},
            {"cat(": ["broken"], "^cat$": ["occluded"]},
            {"occluded": False},
        ),
    ],
    ids=[
        "matched-keys-default-to-false",
        "saved-flag-overrides-default",
        "saved-flag-outside-config-kept",
        "unmatched-pattern-seeds-nothing",
        "pattern-anchored-at-the-label-start",
        "matching-patterns-union",
        "label-flags-none",
        "label-flags-empty",
        "invalid-pattern-skipped",
        "valid-pattern-applies-despite-an-invalid-one",
    ],
)
def test_shapes_from_dicts_merges_label_flags(
    label: str,
    saved_flags: dict[str, bool],
    label_flags: dict[str, list[str]] | None,
    expected: dict[str, bool],
) -> None:
    (shape,) = _app._shapes_from_dicts(
        shape_dicts=[_make_shape_dict(label=label, flags=saved_flags)],
        label_flags=label_flags,
    )
    assert shape.flags == expected


def test_shapes_from_dicts_gives_each_shape_its_own_flags() -> None:
    shapes = _app._shapes_from_dicts(
        shape_dicts=[
            _make_shape_dict(label="cat", flags={"occluded": True}),
            _make_shape_dict(label="cat", flags={}),
        ],
        label_flags={"^cat$": ["occluded"]},
    )
    assert [shape.flags for shape in shapes] == [
        {"occluded": True},
        {"occluded": False},
    ]


def test_shapes_from_dicts_carries_over_the_shape_fields() -> None:
    mask = np.ones((2, 3), dtype=bool)
    shape_dict = ShapeDict(
        label="car",
        points=[[1.0, 2.0], [3.0, 4.0]],
        shape_type="mask",
        flags={},
        description="a parked car",
        group_id=7,
        mask=mask,
        other_data={"score": 0.9},
    )

    (shape,) = _app._shapes_from_dicts(shape_dicts=[shape_dict], label_flags=None)

    assert shape.label == "car"
    assert shape.shape_type == "mask"
    assert shape.description == "a parked car"
    assert shape.group_id == 7
    assert shape.other_data == {"score": 0.9}
    np.testing.assert_array_equal(shape.mask, mask)
    assert shape.points.dtype == np.float64
    assert shape.points.tolist() == [[1.0, 2.0], [3.0, 4.0]]
