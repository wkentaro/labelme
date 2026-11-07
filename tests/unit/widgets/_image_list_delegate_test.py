from __future__ import annotations

import os
from typing import Final

import pytest
from PySide6 import QtCore
from PySide6 import QtWidgets
from pytestqt.qtbot import QtBot

from labelme._widgets._image_list_delegate import ImageListDelegate

_NESTED: Final = [
    "top.jpg",
    os.path.join("a", "x", "1.jpg"),
    os.path.join("a", "x", "2.jpg"),
    os.path.join("a", "y", "1.jpg"),
    os.path.join("a", "y", "2.jpg"),
    os.path.join("a", "y", "3.jpg"),
]


@pytest.fixture()
def widget(*, qtbot: QtBot) -> QtWidgets.QListWidget:
    widget = QtWidgets.QListWidget()
    qtbot.addWidget(widget)
    widget.addItems(_NESTED)
    return widget


@pytest.fixture()
def delegate(*, widget: QtWidgets.QListWidget) -> ImageListDelegate:
    delegate = ImageListDelegate(parent=widget)
    widget.setItemDelegate(delegate)
    delegate.set_labels(_NESTED)
    return delegate


def _index(delegate: ImageListDelegate, row: int, /) -> QtCore.QModelIndex:
    widget = delegate.parent()
    assert isinstance(widget, QtWidgets.QListWidget)
    return widget.model().index(row, 0)


def _shown_text(delegate: ImageListDelegate, row: int, /) -> str:
    option = QtWidgets.QStyleOptionViewItem()
    delegate.initStyleOption(option, _index(delegate, row))
    return option.text


@pytest.mark.parametrize(
    ("labels", "expected"),
    [
        (["1.jpg", "2.jpg"], False),
        (_NESTED, True),
        ([os.path.join(f"s{i}", "image.jpg") for i in range(4)], False),
    ],
    ids=["flat", "nested", "one-image-per-folder"],
)
def test_set_labels_shows_headings_only_when_they_save_rows(
    *, delegate: ImageListDelegate, labels: list[str], expected: bool
) -> None:
    delegate.set_labels(labels)
    assert (delegate.heading(_index(delegate, 0)) is not None) is expected
    assert (_shown_text(delegate, 1) == "1.jpg") is expected


def test_heading_starts_each_folder_run(*, delegate: ImageListDelegate) -> None:
    assert [delegate.heading(_index(delegate, row)) for row in range(6)] == [
        os.curdir + os.sep,
        os.path.join("a", "x") + os.sep,
        None,
        os.path.join("a", "y") + os.sep,
        None,
        None,
    ]


def test_heading_rows_are_taller(*, delegate: ImageListDelegate) -> None:
    option = QtWidgets.QStyleOptionViewItem()
    with_heading = delegate.sizeHint(option, _index(delegate, 1))
    without = delegate.sizeHint(option, _index(delegate, 2))
    assert with_heading.height() > without.height()
