from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any
from typing import Final

import pytest

from .conftest import REPO
from .conftest import Ctl
from .conftest import Run

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin", reason="labelme_ctl.py needs macOS sandbox-exec"
)

ANNOTATED: Final = REPO / "tests" / "data" / "annotated"
IMAGE: Final = "{data}/2011_000003.jpg"


def _saved_shapes(*, ctl: Ctl, run: Run) -> list[dict[str, Any]]:
    annotation = run.data / "2011_000003.json"
    ctl.ok("wait", "--status", "Saved", "--file", str(annotation), run=run)
    return json.loads(annotation.read_text())["shapes"]


def _draw_rectangle(
    *,
    ctl: Ctl,
    run: Run,
    start: tuple[str, str],
    end: tuple[str, str],
    shift: bool = False,
) -> dict[str, Any]:
    ctl.ok("key", "Ctrl+R", run=run)
    ctl.ok("click-canvas", *start, run=run)
    modifier = ("--modifier", "shift") if shift else ()
    reply = ctl.ok("click-canvas", *end, *modifier, run=run)
    assert reply["state"]["dialog"]["title"] == "Shape Label"
    return reply


def _field_text(*, state: dict[str, Any], name: str) -> str:
    fields = state["dialog"]["fields"]
    return next(field["text"] for field in fields if field["name"] == name)


def _assert_within_a_pixel(
    *, point: list[float], expected: tuple[float, float]
) -> None:
    assert point == pytest.approx(expected, abs=1)


def test_save_outside_the_run_dir_fails_and_keeps_the_file(
    *, ctl: Ctl, tmp_path: Path
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    for name in ("2011_000003.jpg", "2011_000003.json"):
        shutil.copy(ANNOTATED / name, outside)
    annotation = outside / "2011_000003.json"
    before = annotation.read_bytes()
    run = ctl.launch("--no-auto-save", str(annotation), seed="none")

    ctl.ok("pick", "Shape List", "blue_block", run=run)
    ctl.ok("key", "Delete", run=run)
    reply = ctl.ok("key", "Ctrl+S", run=run)

    assert "Save failed" in reply["state"]["status_bar"]
    assert annotation.read_bytes() == before


def test_delete_in_the_open_file_dialog_keeps_the_file(
    *, ctl: Ctl, tmp_path: Path
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    image = outside / "zebra.jpg"
    shutil.copy(ANNOTATED / "2011_000003.jpg", image)
    run = ctl.launch(str(image), seed="none")

    ctl.ok("action", "File > Open File", run=run)
    ctl.ok("key", "Shift+Tab", run=run)
    ctl.ok("key", "Z", run=run)
    reply = ctl.ok("key", "Delete", run=run)
    assert "zebra.jpg" in reply["state"]["dialog"]["text"]
    for _ in range(2):
        if reply["state"]["dialog"]["title"] == "Open File":
            break
        reply = ctl.ok("click", "Yes", run=run)

    assert reply["state"]["dialog"]["title"] == "Open File"
    assert image.read_bytes() == (ANNOTATED / "2011_000003.jpg").read_bytes()


def test_typing_lands_in_the_modeless_settings_dialog(*, ctl: Ctl) -> None:
    run = ctl.launch(IMAGE)
    ctl.ok("action", "File > Settings", run=run)

    reply = ctl.ok("type", "zoom", run=run)

    assert reply["state"]["dialog"]["title"] == "Settings"
    assert _field_text(state=reply["state"], name="Search settings") == "zoom"


@pytest.mark.parametrize("end", [(500, 338), (500, 200), (0, 0)])
def test_rectangle_from_inside_to_an_image_edge_saves_its_corner(
    *, ctl: Ctl, end: tuple[int, int]
) -> None:
    run = ctl.launch(IMAGE)

    _draw_rectangle(
        ctl=ctl, run=run, start=("430", "258"), end=(str(end[0]), str(end[1]))
    )
    ctl.ok("type", "corner", run=run)
    ctl.ok("key", "Return", run=run)

    [shape] = _saved_shapes(ctl=ctl, run=run)
    _assert_within_a_pixel(point=shape["points"][0], expected=(430, 258))
    _assert_within_a_pixel(point=shape["points"][1], expected=end)


def test_shift_click_draws_a_square(*, ctl: Ctl) -> None:
    run = ctl.launch(IMAGE)

    _draw_rectangle(
        ctl=ctl, run=run, start=("100", "100"), end=("200", "160"), shift=True
    )
    ctl.ok("type", "square", run=run)
    ctl.ok("key", "Return", run=run)

    [shape] = _saved_shapes(ctl=ctl, run=run)
    _assert_within_a_pixel(point=shape["points"][0], expected=(100, 100))
    _assert_within_a_pixel(point=shape["points"][1], expected=(160, 160))


def test_zoomed_in_click_out_of_view_is_refused(*, ctl: Ctl) -> None:
    run = ctl.launch(IMAGE)
    for _ in range(4):
        ctl.ok("action", "View > Zoom In", run=run)
    ctl.ok("key", "Ctrl+R", run=run)

    refused = ctl("click-canvas", "0", "0", run=run)
    assert refused.code == 1
    assert refused.body["ok"] is False

    _draw_rectangle(ctl=ctl, run=run, start=("250", "169"), end=("260", "175"))
    ctl.ok("type", "visible", run=run)
    ctl.ok("key", "Return", run=run)
    [shape] = _saved_shapes(ctl=ctl, run=run)
    _assert_within_a_pixel(point=shape["points"][0], expected=(250, 169))
    _assert_within_a_pixel(point=shape["points"][1], expected=(260, 175))


def test_two_line_description_saves_both_lines(*, ctl: Ctl) -> None:
    run = ctl.launch(IMAGE)
    _draw_rectangle(ctl=ctl, run=run, start=("100", "100"), end=("200", "200"))
    ctl.ok("type", "box", run=run)

    ctl.ok("click", "Description", run=run)
    ctl.ok("type", "line one\nline two", run=run)
    ctl.ok("click", "OK", run=run)

    [shape] = _saved_shapes(ctl=ctl, run=run)
    assert shape["description"] == "line one\nline two"


def test_type_refuses_a_tab(*, ctl: Ctl) -> None:
    run = ctl.launch(IMAGE)
    _draw_rectangle(ctl=ctl, run=run, start=("100", "100"), end=("200", "200"))

    reply = ctl("type", "a\tb", run=run)

    assert reply.code == 1
    assert reply.body["ok"] is False
    assert _field_text(state=ctl.ok("state", run=run), name="Label") == ""


def test_file_quit_replies_with_a_clean_exit(*, ctl: Ctl) -> None:
    run = ctl.launch(IMAGE)

    reply = ctl.ok("action", "File > Quit", run=run)

    assert reply["exited"] is True
    assert reply["exit_code"] == 0


@pytest.mark.parametrize("sequence", ["Tab, 7", "not a Qt key"])
def test_key_refuses_anything_but_one_known_stroke(*, ctl: Ctl, sequence: str) -> None:
    run = ctl.launch(IMAGE, seed="annotated")
    annotation = run.data / "2011_000003.json"
    before = annotation.read_bytes()
    ctl.ok("pick", "Shape List", "amber_kite", "--double", run=run)

    reply = ctl("key", sequence, run=run)

    assert reply.code == 1
    assert reply.body["ok"] is False
    label = _field_text(state=ctl.ok("state", run=run), name="Label")
    assert label == "amber_kite"
    docks = ctl.ok("click", "OK", run=run)["state"]["docks"]
    shape_list = next(dock for dock in docks if dock["title"] == "Shape List")
    assert shape_list["lists"][0]["rows"][0]["text"] == "amber_kite"
    assert annotation.read_bytes() == before
