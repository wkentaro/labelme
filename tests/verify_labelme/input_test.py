from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any
from typing import Final

import pytest

from labelme import _yaml

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


def _list_rows(*, state: dict[str, Any], dock: str) -> list[dict[str, Any]]:
    found = next(entry for entry in state["docks"] if entry["title"] == dock)
    return found["lists"][0]["rows"]


def _wait_for_dialog_row(*, ctl: Ctl, run: Run, view: str, text: str) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        lists = ctl.ok("state", run=run)["dialog"]["lists"]
        rows = next(entry["rows"] for entry in lists if entry["name"] == view)
        if any(row["text"] == text for row in rows):
            return
        time.sleep(0.2)
    raise AssertionError(f"{text!r} never appeared in {view!r}: {rows}")


def _assert_within_a_pixel(
    *, point: list[float], expected: tuple[float, float]
) -> None:
    assert point == pytest.approx(expected, abs=1)


def _assert_visible(*, point: list[float], canvas: dict[str, Any]) -> None:
    left, top, right, bottom = canvas["visible"]
    assert left <= point[0] <= right, (point, canvas)
    assert top <= point[1] <= bottom, (point, canvas)


def _zoom_in(*, ctl: Ctl, run: Run, steps: int) -> dict[str, Any]:
    if steps:
        ctl.ok("action", "View > Actual Size", run=run)
    for _ in range(steps):
        ctl.ok("action", "View > Zoom In", run=run)
    return ctl.ok("state", run=run)["canvas"]


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
    _wait_for_dialog_row(ctl=ctl, run=run, view="Files", text="zebra.jpg")
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
    canvas = ctl.ok("state", run=run)["canvas"]
    _assert_visible(point=list(end), canvas=canvas)

    _draw_rectangle(
        ctl=ctl, run=run, start=("430", "258"), end=(str(end[0]), str(end[1]))
    )
    ctl.ok("type", "corner", run=run)
    ctl.ok("key", "Return", run=run)

    [shape] = _saved_shapes(ctl=ctl, run=run)
    _assert_within_a_pixel(point=shape["points"][0], expected=(430, 258))
    _assert_within_a_pixel(point=shape["points"][1], expected=end)
    _assert_visible(point=shape["points"][1], canvas=canvas)


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


@pytest.mark.parametrize("zoom_ins", [0, 9], ids=["default", "zoomed_in"])
def test_rectangle_between_the_visible_bounds_saves_inside_them(
    *, ctl: Ctl, zoom_ins: int
) -> None:
    run = ctl.launch(IMAGE)
    canvas = _zoom_in(ctl=ctl, run=run, steps=zoom_ins)
    left, top, right, bottom = (str(bound) for bound in canvas["visible"])

    _draw_rectangle(ctl=ctl, run=run, start=(left, top), end=(right, bottom))
    ctl.ok("type", "bounds", run=run)
    ctl.ok("key", "Return", run=run)

    [shape] = _saved_shapes(ctl=ctl, run=run)
    for point in shape["points"]:
        _assert_visible(point=point, canvas=canvas)


@pytest.mark.parametrize("zoom_ins", [0, 9], ids=["default", "zoomed_in"])
def test_click_a_fraction_beyond_a_visible_bound_is_refused(
    *, ctl: Ctl, zoom_ins: int
) -> None:
    run = ctl.launch(IMAGE)
    canvas = _zoom_in(ctl=ctl, run=run, steps=zoom_ins)
    left, top, right, bottom = canvas["visible"]
    nudge = 1 / canvas["scale"] / 4
    x, y = (left + right) / 2, (top + bottom) / 2

    for beyond in (
        (left - nudge, y),
        (right + nudge, y),
        (x, top - nudge),
        (x, bottom + nudge),
    ):
        refused = ctl("click-canvas", *(str(value) for value in beyond), run=run)
        assert refused.code == 1, (beyond, canvas, refused.body)


def test_zoomed_in_click_a_fraction_left_of_the_view_is_refused(*, ctl: Ctl) -> None:
    run = ctl.launch(IMAGE)
    ctl.ok("action", "View > Actual Size", run=run)
    for _ in range(7):
        ctl.ok("action", "View > Zoom In", run=run)
    canvas = ctl.ok("state", run=run)["canvas"]
    left, top, _, bottom = canvas["visible"]
    assert left > 0
    widget_pixel = 1 / canvas["scale"]
    y = str((top + bottom) / 2)

    refused = ctl("click-canvas", str(left - widget_pixel / 4), y, run=run)

    assert refused.code == 1
    assert "not visible" in refused.body["error"]
    inside = left + widget_pixel / 4
    _draw_rectangle(ctl=ctl, run=run, start=(str(inside), y), end=("250", "200"))
    ctl.ok("type", "edge", run=run)
    ctl.ok("key", "Return", run=run)
    [shape] = _saved_shapes(ctl=ctl, run=run)
    assert left <= shape["points"][0][0] <= inside + widget_pixel / 2


def test_two_line_description_saves_both_lines(*, ctl: Ctl) -> None:
    run = ctl.launch(IMAGE)
    _draw_rectangle(ctl=ctl, run=run, start=("100", "100"), end=("200", "200"))
    ctl.ok("type", "box", run=run)

    ctl.ok("click", "Description", run=run)
    ctl.ok("type", "line one\nline two", run=run)
    ctl.ok("click", "OK", run=run)

    [shape] = _saved_shapes(ctl=ctl, run=run)
    assert shape["description"] == "line one\nline two"


def test_type_after_a_newline_goes_where_return_moved_focus(*, ctl: Ctl) -> None:
    run = ctl.launch("{data}")
    _draw_rectangle(ctl=ctl, run=run, start=("100", "100"), end=("200", "200"))

    reply = ctl.ok("type", "box\nD", run=run)

    assert reply["state"]["dialog"] is None
    assert "2011_000006.jpg" in reply["state"]["main_window"]["title"]
    annotation = run.data / "2011_000003.json"
    ctl.ok("wait", "--file", str(annotation), run=run)
    [shape] = json.loads(annotation.read_text())["shapes"]
    assert shape["label"] == "box"
    assert not (run.data / "2011_000006.json").exists()


def test_type_after_a_return_that_opens_a_dialog_lands_in_it(*, ctl: Ctl) -> None:
    run = ctl.launch(IMAGE)
    ctl.ok("key", "Ctrl+N", run=run)
    for x, y in (("100", "100"), ("200", "100"), ("200", "200")):
        ctl.ok("click-canvas", x, y, run=run)

    reply = ctl.ok("type", "\nbox", run=run)

    assert reply["state"]["dialog"]["title"] == "Shape Label"
    assert _field_text(state=reply["state"], name="Label") == "box"
    ctl.ok("key", "Return", run=run)
    [shape] = _saved_shapes(ctl=ctl, run=run)
    assert shape["label"] == "box"


def test_type_after_a_file_not_found_prompt_answers_it(*, ctl: Ctl) -> None:
    run = ctl.launch("{data}")
    ctl.ok("action", "File > Open File", run=run)
    _wait_for_dialog_row(ctl=ctl, run=run, view="Files", text="2011_000006.jpg")

    reply = ctl.ok("type", "missing.jpg\n\n", run=run)

    assert reply["state"]["dialog"]["title"] == "Open File"


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
    for command in (["wait", "--no-dialog"], ["doctor"]):
        after = ctl(*command, run=run)
        assert after.code == 1, command
        assert after.body["ok"] is False
        assert after.body["error"]
        assert after.body["exit_code"] == 0


def test_double_click_in_the_open_file_dialog_opens_the_file(*, ctl: Ctl) -> None:
    run = ctl.launch("{data}")
    ctl.ok("action", "File > Open File", run=run)
    _wait_for_dialog_row(ctl=ctl, run=run, view="Files", text="2011_000006.jpg")

    reply = ctl.ok("pick", "Files", "2011_000006.jpg", "--double", run=run)

    assert reply["state"]["dialog"] is None
    assert reply["state"]["image_loaded"] is True
    assert "2011_000006.jpg" in reply["state"]["main_window"]["title"]


def test_pick_refuses_a_disabled_row_and_keeps_the_selection(*, ctl: Ctl) -> None:
    run = ctl.launch(IMAGE, seed="annotated")
    ctl.ok("pick", "Label List", "amber_kite", run=run)
    before = _list_rows(state=ctl.ok("state", run=run), dock="Label List")
    assert [row["text"] for row in before if row.get("selected")] == ["amber_kite"]

    reply = ctl("pick", "Label List", "Found in files", run=run)

    assert reply.code == 1
    assert "disabled" in reply.body["error"]
    assert _list_rows(state=ctl.ok("state", run=run), dock="Label List") == before


@pytest.mark.parametrize("sequence", ["Tab, 7", "not a Qt key"])
def test_key_refuses_anything_but_one_known_stroke(*, ctl: Ctl, sequence: str) -> None:
    run = ctl.launch(IMAGE, seed="annotated")
    annotation = run.data / "2011_000003.json"
    before = annotation.read_bytes()
    ctl.ok("pick", "Shape List", "amber_kite", "--double", run=run)

    reply = ctl("key", sequence, run=run)

    assert reply.code == 1
    assert reply.body["ok"] is False
    state = ctl.ok("state", run=run)
    assert _field_text(state=state, name="Label") == "amber_kite"
    assert _field_text(state=state, name="Group ID") == ""
    docks = ctl.ok("click", "OK", run=run)["state"]["docks"]
    shape_list = next(dock for dock in docks if dock["title"] == "Shape List")
    assert shape_list["lists"][0]["rows"][0]["text"] == "amber_kite"
    assert annotation.read_bytes() == before
    [amber_kite] = [
        shape
        for shape in json.loads(annotation.read_text())["shapes"]
        if shape["label"] == "amber_kite"
    ]
    assert amber_kite["group_id"] is None


def test_keys_choose_an_option_in_an_open_settings_combo(*, ctl: Ctl) -> None:
    run = ctl.launch(IMAGE)
    ctl.ok("action", "File > Settings", run=run)
    for stroke in ("Tab", "Tab", "Space"):
        ctl.ok("key", stroke, run=run)

    ctl.ok("key", "Down", run=run)
    reply = ctl.ok("key", "Return", run=run)

    assert reply["state"]["popup"] is None
    combos = reply["state"]["dialog"]["combos"]
    assert {"name": "Color theme", "text": "Light"} in combos
    labelmerc = run.run_dir / "home" / ".labelmerc"
    config = _yaml.safe_load(stream=labelmerc.read_text())
    assert config["color_theme"] == "light"


def test_clicking_a_shape_flag_saves_it_checked(*, ctl: Ctl) -> None:
    run = ctl.launch(IMAGE, "--label-flags", "{.*: [occluded]}")
    _draw_rectangle(ctl=ctl, run=run, start=("100", "100"), end=("200", "200"))
    ctl.ok("type", "box", run=run)

    ctl.ok("click", "occluded", run=run)
    ctl.ok("click", "OK", run=run)

    [shape] = _saved_shapes(ctl=ctl, run=run)
    assert shape["flags"] == {"occluded": True}


def test_type_refuses_empty_text_at_once(*, ctl: Ctl) -> None:
    run = ctl.launch(IMAGE)

    started = time.monotonic()
    reply = ctl("type", "", run=run)

    assert time.monotonic() - started < 10
    assert reply.code == 1
    assert reply.body["ok"] is False
