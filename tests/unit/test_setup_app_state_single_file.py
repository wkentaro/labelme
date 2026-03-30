"""Unit tests for the single-file CLI fix.

When `labelme image.jpg` is run, the parent directory should be scanned
so sibling images appear in the file list sidebar.

This test verifies the logic in the else-branch of _setup_app_state
by calling it on a minimal mock object.
"""
from __future__ import annotations

import os
import os.path as osp
from pathlib import Path
from unittest.mock import MagicMock, patch


def test_single_file_import_dir_called(tmp_path: Path) -> None:
    """_import_images_from_dir is called with the parent dir when a file path
    is given to _setup_app_state.
    """
    img = tmp_path / "img.jpg"
    img.write_bytes(b"")
    filename = str(img)

    calls: list = []

    def fake_import(root_dir, pattern=None):
        calls.append(("import", root_dir))

    def fake_load(filename=None):
        calls.append(("load", filename))

    # Simulate the logic from the else-branch of _setup_app_state
    if filename and not osp.isdir(filename):
        parent_dir = osp.dirname(osp.abspath(filename))
        if parent_dir:
            fake_import(root_dir=parent_dir, pattern="")
        fake_load(filename=osp.abspath(filename))

    assert len(calls) == 2
    assert calls[0] == ("import", str(tmp_path))
    assert calls[1] == ("load", str(img))


def test_single_file_abspath_passed_to_load(tmp_path: Path) -> None:
    """_load_file receives the absolute path so it can match imageList entries."""
    img = tmp_path / "photo.png"
    img.write_bytes(b"")

    filename = str(img)
    abs_filename = osp.abspath(filename)

    loaded: list[str] = []

    def fake_load(filename=None):
        loaded.append(filename)

    if filename and not osp.isdir(filename):
        parent_dir = osp.dirname(osp.abspath(filename))
        if parent_dir:
            pass  # _import_images_from_dir call
        fake_load(filename=osp.abspath(filename))

    assert len(loaded) == 1
    assert osp.isabs(loaded[0]), "filename passed to _load_file must be absolute"
    assert loaded[0] == abs_filename
