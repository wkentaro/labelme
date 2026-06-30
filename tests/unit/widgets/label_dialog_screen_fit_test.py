from __future__ import annotations

from pytestqt.qtbot import QtBot

from labelme._widgets.label_dialog import LabelDialog


def _make_dialog(qtbot: QtBot, flag_count: int) -> LabelDialog:
    flags = {f"flag_{i:02d}": False for i in range(flag_count)}
    dialog = LabelDialog(labels=["cat"], flags={".*": list(flags)})
    qtbot.addWidget(dialog)
    dialog._set_flag_checkboxes(flags=flags.items())
    return dialog


def _checkbox_gaps(dialog: LabelDialog) -> list[int]:
    tops = [checkbox.y() for checkbox in dialog._flag_checkboxes()]
    return [bottom - top for top, bottom in zip(tops, tops[1:])]


def test_flag_spacing_is_identical_with_and_without_scrollbar(qtbot: QtBot) -> None:
    few = _make_dialog(qtbot, flag_count=3)
    many = _make_dialog(qtbot, flag_count=12)
    for dialog in (few, many):
        dialog.show()
        qtbot.waitExposed(dialog)

    assert few._flags_scroll.verticalScrollBar().maximum() == 0
    assert many._flags_scroll.verticalScrollBar().maximum() > 0

    few_gaps = set(_checkbox_gaps(few))
    many_gaps = set(_checkbox_gaps(many))
    assert len(few_gaps) == 1
    assert few_gaps == many_gaps


def test_many_flags_are_capped_and_scrollable(qtbot: QtBot) -> None:
    dialog = _make_dialog(qtbot, flag_count=60)
    dialog.show()
    qtbot.waitExposed(dialog)

    assert dialog._flags_scroll.height() <= 150
    assert dialog._flags_scroll.verticalScrollBar().maximum() > 0


def test_few_flags_shrink_below_cap(qtbot: QtBot) -> None:
    dialog = _make_dialog(qtbot, flag_count=2)
    dialog.show()
    qtbot.waitExposed(dialog)

    assert dialog._flags_scroll.height() < 150
    assert dialog._flags_scroll.verticalScrollBar().maximum() == 0
