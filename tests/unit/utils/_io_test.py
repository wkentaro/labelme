# MIT License
# Copyright (c) Kentaro Wada

import os

import numpy as np
import PIL.Image
import pytest

from labelme.utils._io import lblsave


def test_lblsave_valid_uint8_labels(tmp_path):
    """Labels in [0, 254] range should be saved as P-mode PNG with colormap."""
    lbl = np.zeros((10, 10), dtype=np.int32)
    lbl[0, 0] = 254
    out = str(tmp_path / "label.png")
    lblsave(out, lbl)
    assert os.path.isfile(out)
    img = PIL.Image.open(out)
    assert img.mode == "P"


def test_lblsave_adds_png_extension(tmp_path):
    """Filename without .png extension should have .png appended automatically."""
    lbl = np.zeros((5, 5), dtype=np.int32)
    out_base = str(tmp_path / "label")
    lblsave(out_base, lbl)
    assert os.path.isfile(out_base + ".png")
    assert not os.path.isfile(out_base)


def test_lblsave_invalid_labels_raises(tmp_path):
    """lbl.max() >= 255 should raise ValueError."""
    lbl = np.zeros((5, 5), dtype=np.int32)
    lbl[0, 0] = 255
    out = str(tmp_path / "label.png")
    with pytest.raises(ValueError, match="Cannot save"):
        lblsave(out, lbl)


def test_lblsave_negative_one_labels_ok(tmp_path):
    """lbl.min() == -1 with lbl.max() < 255 should save successfully."""
    lbl = np.full((8, 8), -1, dtype=np.int32)
    lbl[4, 4] = 100
    out = str(tmp_path / "label.png")
    lblsave(out, lbl)
    assert os.path.isfile(out)
    img = PIL.Image.open(out)
    assert img.mode == "P"
