from __future__ import annotations

from pathlib import Path

import pytest
from PySide6 import QtGui
from PySide6 import QtWidgets
from pytestqt.qtbot import QtBot

from labelme._yaml import safe_load

from ..conftest import close_or_pause
from .conftest import MainWinFactory


@pytest.mark.gui
def test_view_menu_changes_and_persists_default_label_color(
    main_win: MainWinFactory,
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    tmp_path: Path,
    pause: bool,
) -> None:
    config_file = tmp_path / "labelmerc.yaml"
    config_file.write_text("", encoding="utf-8")
    win = main_win(config_file=config_file)
    canvas = win._canvas_widgets.canvas

    action = next(
        action
        for action in win._menus.view.actions()
        if action.text() == "Default Label Color…"
    )
    assert canvas._draft_palette.line.getRgb() == (255, 255, 0, 128)
    assert canvas._draft_palette.vertex_fill.getRgb() == (255, 255, 0, 255)
    assert canvas._draft_palette.select_line.getRgb() == (255, 255, 0, 255)
    assert canvas._draft_palette.select_fill.getRgb() == (255, 255, 0, 64)
    assert win._get_rgb_by_label(
        label="new-label",
        unique_label_list=win._docks.unique_label_list,
    ) == (255, 255, 0)

    monkeypatch.setattr(
        QtWidgets.QColorDialog,
        "getColor",
        lambda *args, **kwargs: QtGui.QColor(12, 34, 56),
    )
    action.trigger()

    assert canvas._draft_palette.line.getRgb() == (12, 34, 56, 128)
    assert canvas._draft_palette.vertex_fill.getRgb() == (12, 34, 56, 255)
    assert canvas._draft_palette.select_line.getRgb() == (12, 34, 56, 255)
    assert canvas._draft_palette.select_fill.getRgb() == (12, 34, 56, 64)
    assert win._get_rgb_by_label(
        label="new-label",
        unique_label_list=win._docks.unique_label_list,
    ) == (12, 34, 56)
    assert safe_load(config_file.read_text(encoding="utf-8")) == {
        "shape_color": {
            "uniform": {"color": [12, 34, 56]},
            "by_label": {"fallback": [12, 34, 56]},
        },
        "shape": {
            "line_color": [12, 34, 56, 128],
            "vertex_fill_color": [12, 34, 56, 255],
            "select_line_color": [12, 34, 56, 255],
            "select_fill_color": [12, 34, 56, 64],
        },
    }

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)
