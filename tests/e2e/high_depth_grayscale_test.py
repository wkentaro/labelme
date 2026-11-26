from __future__ import annotations

from pathlib import Path

import numpy as np
import PIL.Image
import pytest
import tifffile
from pytestqt.qtbot import QtBot

from ..conftest import close_or_pause
from .conftest import MainWinFactory
from .conftest import canvas_pixels
from .conftest import save_12bit_ramp
from .conftest import show_window_and_wait_for_imagedata


@pytest.mark.parametrize("suffix", [".png", ".pgm"])
def test_12bit_grayscale_shows_from_black_to_white(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    tmp_path: Path,
    pause: bool,
    suffix: str,
) -> None:
    image_path = tmp_path / f"ramp{suffix}"
    save_12bit_ramp(path=image_path)
    win = main_win(file_or_dir=image_path)
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    shown = canvas_pixels(win=win)[..., :3]

    assert (shown.min(), shown.max()) == (0, 255)

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


def test_16bit_grayscale_png_shows_as_the_same_tiff_does(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    blocks = (np.arange(64, dtype=np.uint16) * 65 + 300).reshape(8, 8)
    levels = np.repeat(np.repeat(blocks, 8, axis=0), 8, axis=1)[:, :61]
    tifffile.imwrite(tmp_path / "levels.tif", levels)
    PIL.Image.fromarray(levels).save(tmp_path / "levels.png")

    shown = {}
    for name in ("levels.tif", "levels.png"):
        win = main_win(file_or_dir=tmp_path / name)
        show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
        shown[name] = canvas_pixels(win=win)

    np.testing.assert_array_equal(shown["levels.png"], shown["levels.tif"])
