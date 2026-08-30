from __future__ import annotations

from collections.abc import Callable

import pytest
from PySide6 import QtCore
from PySide6 import QtWidgets
from pytestqt.qtbot import QtBot

from labelme._widgets.label_dialog import LabelDialog
from labelme._widgets.label_dialog import LabelQLineEdit

# Black-box characterization of LabelDialog: behavior is exercised only through
# the public surface (popup(), public methods, public widgets edit/
# edit_group_id/edit_description/label_list, and observable Qt state). No
# private method or attribute is referenced, so a rewrite is free to restructure
# internals while these tests keep pinning observable behavior.


def _add_dialog(qtbot: QtBot, /, *, dialog: LabelDialog) -> LabelDialog:
    qtbot.addWidget(dialog)
    return dialog


def _run_popup(
    *,
    dialog: LabelDialog,
    accept: bool,
    at_show: Callable[[LabelDialog], None] | None,
    text: str | None,
    flags: dict[str, bool] | None,
    group_id: int | None,
    description: str | None,
    flags_disabled: bool,
) -> tuple[str, dict[str, bool], int | None, str] | tuple[None, None, None, None]:
    code = (
        QtWidgets.QDialog.DialogCode.Accepted
        if accept
        else QtWidgets.QDialog.DialogCode.Rejected
    )

    def fake_exec() -> int:
        if at_show is not None:
            at_show(dialog)
        return code

    dialog.exec = fake_exec  # ty: ignore[invalid-assignment]
    return dialog.popup(
        text=text,
        # Keeping the dialog put makes the popup deterministic under a stubbed
        # exec(), which never shows it.
        move=False,
        flags=flags,
        group_id=group_id,
        description=description,
        flags_disabled=flags_disabled,
    )


def _checkboxes(dialog: LabelDialog, /) -> list[QtWidgets.QCheckBox]:
    return dialog.findChildren(QtWidgets.QCheckBox)


def _checkbox(*, dialog: LabelDialog, name: str) -> QtWidgets.QCheckBox:
    matches = [cb for cb in _checkboxes(dialog) if cb.text() == name]
    assert matches, f"no checkbox named {name!r}"
    return matches[0]


def _ok_button(dialog: LabelDialog, /) -> QtWidgets.QPushButton:
    box = dialog.findChild(QtWidgets.QDialogButtonBox)
    assert box is not None
    button = box.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)
    assert button is not None
    return button


# ---------------------------------------------------------------------------
# LabelQLineEdit
# ---------------------------------------------------------------------------


def test_set_list_widget_stores_reference(qtbot: QtBot) -> None:
    edit = LabelQLineEdit()
    qtbot.addWidget(edit)
    list_widget = QtWidgets.QListWidget()
    qtbot.addWidget(list_widget)
    edit.set_list_widget(list_widget)
    assert edit.list_widget is list_widget


def test_key_down_forwarded_to_list_widget(qtbot: QtBot) -> None:
    edit = LabelQLineEdit()
    qtbot.addWidget(edit)
    list_widget = QtWidgets.QListWidget()
    qtbot.addWidget(list_widget)
    list_widget.addItems(["a", "b", "c"])
    list_widget.setCurrentRow(0)
    edit.set_list_widget(list_widget)
    edit.show()
    qtbot.keyClick(edit, QtCore.Qt.Key.Key_Down)
    assert list_widget.currentRow() == 1


def test_key_up_forwarded_to_list_widget(qtbot: QtBot) -> None:
    edit = LabelQLineEdit()
    qtbot.addWidget(edit)
    list_widget = QtWidgets.QListWidget()
    qtbot.addWidget(list_widget)
    list_widget.addItems(["a", "b", "c"])
    list_widget.setCurrentRow(2)
    edit.set_list_widget(list_widget)
    edit.show()
    qtbot.keyClick(edit, QtCore.Qt.Key.Key_Up)
    assert list_widget.currentRow() == 1


def test_other_keys_edit_text_not_forwarded(qtbot: QtBot) -> None:
    edit = LabelQLineEdit()
    qtbot.addWidget(edit)
    list_widget = QtWidgets.QListWidget()
    qtbot.addWidget(list_widget)
    list_widget.addItems(["a", "b", "c"])
    list_widget.setCurrentRow(0)
    edit.set_list_widget(list_widget)
    edit.show()
    qtbot.keyClicks(edit, "x")
    assert edit.text() == "x"
    assert list_widget.currentRow() == 0


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_default_widgets_exist(qtbot: QtBot) -> None:
    dialog = _add_dialog(qtbot, dialog=LabelDialog())
    assert isinstance(dialog.edit, LabelQLineEdit)
    assert isinstance(dialog.edit_group_id, QtWidgets.QLineEdit)
    assert isinstance(dialog.edit_description, QtWidgets.QTextEdit)
    assert isinstance(dialog.label_list, QtWidgets.QListWidget)


def test_default_placeholder_is_non_empty(qtbot: QtBot) -> None:
    dialog = _add_dialog(qtbot, dialog=LabelDialog())
    assert dialog.edit.placeholderText() != ""


def test_custom_placeholder_text(qtbot: QtBot) -> None:
    dialog = _add_dialog(qtbot, dialog=LabelDialog(text="Type here"))
    assert dialog.edit.placeholderText() == "Type here"


def test_group_id_and_description_placeholders_non_empty(qtbot: QtBot) -> None:
    dialog = _add_dialog(qtbot, dialog=LabelDialog())
    assert dialog.edit_group_id.placeholderText() != ""
    assert dialog.edit_description.placeholderText() != ""


def test_show_text_field_true_parents_edit_to_dialog(qtbot: QtBot) -> None:
    dialog = _add_dialog(qtbot, dialog=LabelDialog(show_text_field=True))
    assert dialog.edit.parent() is dialog


def test_show_text_field_false_leaves_edit_parentless(qtbot: QtBot) -> None:
    dialog = _add_dialog(qtbot, dialog=LabelDialog(show_text_field=False))
    assert dialog.edit.parent() is None


def test_initial_labels_listed(qtbot: QtBot) -> None:
    dialog = _add_dialog(
        qtbot, dialog=LabelDialog(labels=["banana", "apple", "cherry"])
    )
    items = [dialog.label_list.item(i).text() for i in range(dialog.label_list.count())]
    assert set(items) == {"apple", "banana", "cherry"}


def test_sort_labels_true_sorts(qtbot: QtBot) -> None:
    dialog = _add_dialog(
        qtbot,
        dialog=LabelDialog(labels=["banana", "apple", "cherry"], sort_labels=True),
    )
    items = [dialog.label_list.item(i).text() for i in range(dialog.label_list.count())]
    assert items == ["apple", "banana", "cherry"]


def test_sort_labels_false_preserves_order_and_enables_drag(qtbot: QtBot) -> None:
    dialog = _add_dialog(
        qtbot,
        dialog=LabelDialog(labels=["banana", "apple", "cherry"], sort_labels=False),
    )
    items = [dialog.label_list.item(i).text() for i in range(dialog.label_list.count())]
    assert items == ["banana", "apple", "cherry"]
    assert (
        dialog.label_list.dragDropMode()
        == QtWidgets.QAbstractItemView.DragDropMode.InternalMove
    )


@pytest.mark.parametrize("row_off", [True, False])
@pytest.mark.parametrize("col_off", [True, False])
def test_fit_to_content_scrollbar_policies(
    qtbot: QtBot, *, row_off: bool, col_off: bool
) -> None:
    dialog = _add_dialog(
        qtbot, dialog=LabelDialog(fit_to_content={"row": row_off, "column": col_off})
    )
    always_off = QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    if row_off:
        assert dialog.label_list.horizontalScrollBarPolicy() == always_off
    if col_off:
        assert dialog.label_list.verticalScrollBarPolicy() == always_off


# ---------------------------------------------------------------------------
# Completion
# ---------------------------------------------------------------------------


def test_completion_startswith_inline(qtbot: QtBot) -> None:
    dialog = _add_dialog(qtbot, dialog=LabelDialog(completion="startswith"))
    assert (
        dialog.edit.completer().completionMode()
        == QtWidgets.QCompleter.CompletionMode.InlineCompletion
    )


def test_completion_contains_popup_and_matchcontains(qtbot: QtBot) -> None:
    dialog = _add_dialog(qtbot, dialog=LabelDialog(completion="contains"))
    completer = dialog.edit.completer()
    assert (
        completer.completionMode()
        == QtWidgets.QCompleter.CompletionMode.PopupCompletion
    )
    assert completer.filterMode() == QtCore.Qt.MatchFlag.MatchContains


@pytest.mark.usefixtures("qtbot")
def test_completion_invalid_raises() -> None:
    with pytest.raises(ValueError):
        LabelDialog(completion="fuzzy")


def test_completer_bound_to_label_list_model(qtbot: QtBot) -> None:
    dialog = _add_dialog(qtbot, dialog=LabelDialog(labels=["a", "b"]))
    assert dialog.edit.completer().model() is dialog.label_list.model()


# ---------------------------------------------------------------------------
# Label history / predefined labels
# ---------------------------------------------------------------------------


def test_add_label_history_appends_new(qtbot: QtBot) -> None:
    dialog = _add_dialog(qtbot, dialog=LabelDialog(labels=[]))
    dialog.add_label_history("dog")
    items = [dialog.label_list.item(i).text() for i in range(dialog.label_list.count())]
    assert "dog" in items


def test_add_label_history_no_duplicate(qtbot: QtBot) -> None:
    dialog = _add_dialog(qtbot, dialog=LabelDialog(labels=["dog"]))
    dialog.add_label_history("dog")
    items = [dialog.label_list.item(i).text() for i in range(dialog.label_list.count())]
    assert items.count("dog") == 1


def test_add_label_history_sorts_when_sort_enabled(qtbot: QtBot) -> None:
    dialog = _add_dialog(
        qtbot, dialog=LabelDialog(labels=["banana", "apple"], sort_labels=True)
    )
    dialog.add_label_history("cherry")
    items = [dialog.label_list.item(i).text() for i in range(dialog.label_list.count())]
    assert items == ["apple", "banana", "cherry"]


def test_set_predefined_labels_merges_and_dedups(qtbot: QtBot) -> None:
    dialog = _add_dialog(qtbot, dialog=LabelDialog(labels=["a"], sort_labels=False))
    dialog.add_label_history("b")
    dialog.set_predefined_labels(["a", "c"])
    items = [dialog.label_list.item(i).text() for i in range(dialog.label_list.count())]
    assert set(items) == {"a", "b", "c"}
    assert len(items) == 3


def test_set_predefined_labels_keeps_completer_bound(qtbot: QtBot) -> None:
    dialog = _add_dialog(qtbot, dialog=LabelDialog(labels=["a"]))
    dialog.set_predefined_labels(["a", "b", "c"])
    assert dialog.edit.completer().model() is dialog.label_list.model()


# ---------------------------------------------------------------------------
# Editing behavior
# ---------------------------------------------------------------------------


def test_editing_finished_strips_whitespace(qtbot: QtBot) -> None:
    dialog = _add_dialog(qtbot, dialog=LabelDialog())
    dialog.edit.setText("  hello  ")
    dialog.edit.editingFinished.emit()
    assert dialog.edit.text() == "hello"


def test_selecting_label_sets_edit_text(qtbot: QtBot) -> None:
    dialog = _add_dialog(qtbot, dialog=LabelDialog(labels=["cat", "dog"]))
    item = dialog.label_list.findItems("dog", QtCore.Qt.MatchFlag.MatchExactly)[0]
    dialog.label_list.setCurrentItem(item)
    assert dialog.edit.text() == "dog"


def test_clearing_selection_with_none_does_not_crash(qtbot: QtBot) -> None:
    dialog = _add_dialog(qtbot, dialog=LabelDialog(labels=["cat"]))
    dialog.label_list.setCurrentItem(
        dialog.label_list.findItems("cat", QtCore.Qt.MatchFlag.MatchExactly)[0]
    )
    dialog.label_list.clear()  # fires currentItemChanged(None)
    assert dialog.edit.text() == "cat"


# ---------------------------------------------------------------------------
# Validation (via the OK button)
# ---------------------------------------------------------------------------


def test_ok_with_text_accepts(qtbot: QtBot) -> None:
    dialog = _add_dialog(qtbot, dialog=LabelDialog())
    dialog.edit.setText("car")
    _ok_button(dialog).click()
    assert dialog.result() == QtWidgets.QDialog.DialogCode.Accepted


def test_ok_with_empty_text_does_not_accept(qtbot: QtBot) -> None:
    dialog = _add_dialog(qtbot, dialog=LabelDialog())
    dialog.edit.setText("")
    _ok_button(dialog).click()
    assert dialog.result() != QtWidgets.QDialog.DialogCode.Accepted


def test_ok_with_whitespace_text_does_not_accept(qtbot: QtBot) -> None:
    dialog = _add_dialog(qtbot, dialog=LabelDialog())
    dialog.edit.setText("   ")
    _ok_button(dialog).click()
    assert dialog.result() != QtWidgets.QDialog.DialogCode.Accepted


def test_ok_accepts_when_edit_disabled_even_if_empty(qtbot: QtBot) -> None:
    dialog = _add_dialog(qtbot, dialog=LabelDialog())
    dialog.edit.setText("")
    dialog.edit.setEnabled(False)
    _ok_button(dialog).click()
    assert dialog.result() == QtWidgets.QDialog.DialogCode.Accepted


def test_double_click_label_accepts(qtbot: QtBot) -> None:
    dialog = _add_dialog(qtbot, dialog=LabelDialog(labels=["cat"]))
    item = dialog.label_list.findItems("cat", QtCore.Qt.MatchFlag.MatchExactly)[0]
    dialog.label_list.setCurrentItem(item)  # selection sets the edit text
    dialog.label_list.itemDoubleClicked.emit(item)
    assert dialog.result() == QtWidgets.QDialog.DialogCode.Accepted


# ---------------------------------------------------------------------------
# Flags
# ---------------------------------------------------------------------------


def test_flags_shown_for_matching_label(qtbot: QtBot) -> None:
    dialog = _add_dialog(
        qtbot, dialog=LabelDialog(flags={"^cat$": ["indoor", "outdoor"]})
    )
    dialog.edit.setText("cat")
    names = {cb.text() for cb in _checkboxes(dialog)}
    assert names == {"indoor", "outdoor"}


def test_flags_absent_for_non_matching_label(qtbot: QtBot) -> None:
    dialog = _add_dialog(qtbot, dialog=LabelDialog(flags={"^cat$": ["indoor"]}))
    dialog.edit.setText("dog")
    assert _checkboxes(dialog) == []


def test_flags_shown_for_prefix_match(qtbot: QtBot) -> None:
    dialog = _add_dialog(qtbot, dialog=LabelDialog(flags={"car": ["fast"]}))
    dialog.edit.setText("car_red")
    names = {cb.text() for cb in _checkboxes(dialog)}
    assert names == {"fast"}


def test_flag_checked_state_preserved_across_text_change(qtbot: QtBot) -> None:
    dialog = _add_dialog(qtbot, dialog=LabelDialog(flags={"^cat": ["indoor"]}))
    dialog.edit.setText("cat")
    box = next(cb for cb in _checkboxes(dialog) if cb.text() == "indoor")
    box.setChecked(True)
    dialog.edit.setText("cat2")  # still matches "^cat"
    box2 = next(cb for cb in _checkboxes(dialog) if cb.text() == "indoor")
    assert box2.isChecked()


def test_flag_checked_state_preserved_across_non_matching_text(qtbot: QtBot) -> None:
    dialog = _add_dialog(qtbot, dialog=LabelDialog(flags={"^cat": ["indoor"]}))
    dialog.edit.setText("cat")
    _checkbox(dialog=dialog, name="indoor").setChecked(True)
    dialog.edit.setText("c")  # typing over a selected label dips through "c"
    assert _checkboxes(dialog) == []
    dialog.edit.setText("cat")
    assert _checkbox(dialog=dialog, name="indoor").isChecked()


def test_flag_checked_state_shared_across_labels(qtbot: QtBot) -> None:
    dialog = _add_dialog(
        qtbot, dialog=LabelDialog(flags={"^cat$": ["indoor"], "^dog$": ["indoor"]})
    )
    dialog.edit.setText("cat")
    _checkbox(dialog=dialog, name="indoor").setChecked(True)
    dialog.edit.setText("dog")
    assert _checkbox(dialog=dialog, name="indoor").isChecked()


def test_flag_checkboxes_stay_visible_when_rebuilt_while_shown(qtbot: QtBot) -> None:
    dialog = _add_dialog(qtbot, dialog=LabelDialog(flags={".*": ["occluded"]}))
    dialog.edit.setText("cat")
    with qtbot.waitExposed(dialog):
        dialog.show()
    dialog.edit.setText("dog")  # rebuilds the checkboxes while the dialog is shown
    qtbot.waitUntil(
        lambda: not _checkbox(dialog=dialog, name="occluded").visibleRegion().isEmpty(),
        timeout=1000,
    )


def test_flag_named_by_two_matching_patterns_shown_once(qtbot: QtBot) -> None:
    dialog = _add_dialog(
        qtbot,
        dialog=LabelDialog(flags={".*": ["occluded"], "^cat$": ["occluded", "urgent"]}),
    )
    dialog.edit.setText("cat")
    assert [cb.text() for cb in _checkboxes(dialog)] == ["occluded", "urgent"]


def test_flag_named_by_two_matching_patterns_keeps_its_checked_state(
    qtbot: QtBot,
) -> None:
    dialog = _add_dialog(
        qtbot,
        dialog=LabelDialog(flags={".*": ["occluded"], "^cat$": ["occluded", "urgent"]}),
    )

    _, flags, _, _ = _run_popup(
        dialog=dialog,
        accept=True,
        text="cat",
        at_show=lambda d: _checkbox(dialog=d, name="occluded").setChecked(True),
        flags=None,
        group_id=None,
        description=None,
        flags_disabled=False,
    )
    assert flags == {"occluded": True, "urgent": False}


# ---------------------------------------------------------------------------
# popup() round-trips (exec stubbed)
# ---------------------------------------------------------------------------


def test_popup_returns_typed_values_on_accept(qtbot: QtBot) -> None:
    dialog = _add_dialog(qtbot, dialog=LabelDialog(labels=["cat"]))
    text, flags, group_id, description = _run_popup(
        dialog=dialog,
        accept=True,
        text="cat",
        group_id=3,
        description="a pet",
        at_show=None,
        flags=None,
        flags_disabled=False,
    )
    assert text == "cat"
    assert group_id == 3
    assert description == "a pet"
    assert flags == {}


def test_popup_preserves_html_like_description(qtbot: QtBot) -> None:
    dialog = _add_dialog(qtbot, dialog=LabelDialog())
    _, _, _, description = _run_popup(
        dialog=dialog,
        accept=True,
        text="cat",
        description="<b>bold</b>",
        at_show=None,
        flags=None,
        group_id=None,
        flags_disabled=False,
    )
    assert description == "<b>bold</b>"


def test_popup_returns_all_none_on_reject(qtbot: QtBot) -> None:
    dialog = _add_dialog(qtbot, dialog=LabelDialog())
    result = _run_popup(
        dialog=dialog,
        accept=False,
        text="cat",
        at_show=None,
        flags=None,
        group_id=None,
        description=None,
        flags_disabled=False,
    )
    assert result == (None, None, None, None)


def test_popup_group_id_none_yields_empty_then_none(qtbot: QtBot) -> None:
    seen: dict[str, str] = {}
    dialog = _add_dialog(qtbot, dialog=LabelDialog())
    _, _, group_id, _ = _run_popup(
        dialog=dialog,
        accept=True,
        text="x",
        group_id=None,
        at_show=lambda d: seen.update(gid=d.edit_group_id.text()),
        flags=None,
        description=None,
        flags_disabled=False,
    )
    assert seen["gid"] == ""
    assert group_id is None


def test_popup_group_id_zero_is_preserved(qtbot: QtBot) -> None:
    dialog = _add_dialog(qtbot, dialog=LabelDialog())
    _, _, group_id, _ = _run_popup(
        dialog=dialog,
        accept=True,
        text="x",
        group_id=0,
        at_show=None,
        flags=None,
        description=None,
        flags_disabled=False,
    )
    assert group_id == 0


def test_popup_sets_group_id_text_at_show(qtbot: QtBot) -> None:
    seen: dict[str, str] = {}
    dialog = _add_dialog(qtbot, dialog=LabelDialog())
    _run_popup(
        dialog=dialog,
        accept=True,
        text="x",
        group_id=7,
        at_show=lambda d: seen.update(gid=d.edit_group_id.text()),
        flags=None,
        description=None,
        flags_disabled=False,
    )
    assert seen["gid"] == "7"


def test_popup_text_none_preserves_existing_edit_text(qtbot: QtBot) -> None:
    seen: dict[str, str] = {}
    dialog = _add_dialog(qtbot, dialog=LabelDialog())
    dialog.edit.setText("preexisting")
    _run_popup(
        dialog=dialog,
        accept=True,
        text=None,
        at_show=lambda d: seen.update(t=d.edit.text()),
        flags=None,
        group_id=None,
        description=None,
        flags_disabled=False,
    )
    assert seen["t"] == "preexisting"


def test_popup_text_none_selects_existing_edit_text(qtbot: QtBot) -> None:
    seen: dict[str, str] = {}
    dialog = _add_dialog(qtbot, dialog=LabelDialog())
    dialog.edit.setText("preexisting")
    _run_popup(
        dialog=dialog,
        accept=True,
        text=None,
        at_show=lambda d: seen.update(sel=d.edit.selectedText()),
        flags=None,
        group_id=None,
        description=None,
        flags_disabled=False,
    )
    assert seen["sel"] == "preexisting"


def test_popup_highlights_matching_label_at_show(qtbot: QtBot) -> None:
    seen: dict[str, object] = {}
    dialog = _add_dialog(qtbot, dialog=LabelDialog(labels=["cat", "dog"]))
    _run_popup(
        dialog=dialog,
        accept=True,
        text="dog",
        at_show=lambda d: seen.update(
            cur=d.label_list.currentItem().text()
            if d.label_list.currentItem()
            else None
        ),
        flags=None,
        group_id=None,
        description=None,
        flags_disabled=False,
    )
    assert seen["cur"] == "dog"


def test_popup_highlights_matching_label_case_insensitively(qtbot: QtBot) -> None:
    seen: dict[str, object] = {}
    dialog = _add_dialog(qtbot, dialog=LabelDialog(labels=["Cat", "Dog"]))
    _run_popup(
        dialog=dialog,
        accept=True,
        text="cat",
        at_show=lambda d: seen.update(
            cur=d.label_list.currentItem().text()
            if d.label_list.currentItem()
            else None
        ),
        flags=None,
        group_id=None,
        description=None,
        flags_disabled=False,
    )
    assert seen["cur"] == "Cat"


def test_popup_sets_description_at_show(qtbot: QtBot) -> None:
    seen: dict[str, str] = {}
    dialog = _add_dialog(qtbot, dialog=LabelDialog())
    _run_popup(
        dialog=dialog,
        accept=True,
        text="x",
        description="hello world",
        at_show=lambda d: seen.update(desc=d.edit_description.toPlainText()),
        flags=None,
        group_id=None,
        flags_disabled=False,
    )
    assert seen["desc"] == "hello world"


def test_popup_flags_disabled_disables_checkboxes(qtbot: QtBot) -> None:
    seen: dict[str, list[bool]] = {}
    dialog = _add_dialog(
        qtbot, dialog=LabelDialog(flags={"^cat": ["indoor", "outdoor"]})
    )
    _run_popup(
        dialog=dialog,
        accept=True,
        text="cat",
        flags={"indoor": True},
        flags_disabled=True,
        at_show=lambda d: seen.update(
            enabled=[cb.isEnabled() for cb in _checkboxes(d)]
        ),
        group_id=None,
        description=None,
    )
    assert seen["enabled"]
    assert not any(seen["enabled"])


def test_popup_flags_enabled_by_default(qtbot: QtBot) -> None:
    seen: dict[str, list[bool]] = {}
    dialog = _add_dialog(
        qtbot, dialog=LabelDialog(flags={"^cat": ["indoor", "outdoor"]})
    )
    _run_popup(
        dialog=dialog,
        accept=True,
        text="cat",
        at_show=lambda d: seen.update(
            enabled=[cb.isEnabled() for cb in _checkboxes(d)]
        ),
        flags=None,
        group_id=None,
        description=None,
        flags_disabled=False,
    )
    assert seen["enabled"]
    assert all(seen["enabled"])


def test_flags_disabled_resets_between_popups(qtbot: QtBot) -> None:
    dialog = _add_dialog(qtbot, dialog=LabelDialog(flags={"^cat": ["indoor"]}))
    _run_popup(
        dialog=dialog,
        accept=True,
        text="cat",
        flags_disabled=True,
        at_show=None,
        flags=None,
        group_id=None,
        description=None,
    )

    seen: dict[str, list[bool]] = {}
    _run_popup(
        dialog=dialog,
        accept=True,
        text="cat",
        at_show=lambda d: seen.update(
            enabled=[cb.isEnabled() for cb in _checkboxes(d)]
        ),
        flags=None,
        group_id=None,
        description=None,
        flags_disabled=False,
    )
    assert seen["enabled"]
    assert all(seen["enabled"])


def test_flag_checked_state_does_not_leak_into_next_new_shape_popup(
    qtbot: QtBot,
) -> None:
    seen: dict[str, bool] = {}
    dialog = _add_dialog(qtbot, dialog=LabelDialog(flags={"^cat$": ["indoor"]}))
    _run_popup(
        dialog=dialog,
        accept=True,
        text="cat",
        at_show=lambda d: _checkbox(dialog=d, name="indoor").setChecked(True),
        flags=None,
        group_id=None,
        description=None,
        flags_disabled=False,
    )
    _run_popup(
        dialog=dialog,
        accept=True,
        text="cat",
        at_show=lambda d: seen.update(
            checked=_checkbox(dialog=d, name="indoor").isChecked()
        ),
        flags=None,
        group_id=None,
        description=None,
        flags_disabled=False,
    )
    assert seen["checked"] is False


def test_edited_shape_flags_do_not_leak_into_next_new_shape_popup(
    qtbot: QtBot,
) -> None:
    seen: dict[str, bool] = {}
    dialog = _add_dialog(qtbot, dialog=LabelDialog(flags={"^cat$": ["indoor"]}))
    _run_popup(
        dialog=dialog,
        accept=True,
        text="cat",
        flags={"indoor": True},
        at_show=None,
        group_id=None,
        description=None,
        flags_disabled=False,
    )
    _run_popup(
        dialog=dialog,
        accept=True,
        text="cat",
        at_show=lambda d: seen.update(
            checked=_checkbox(dialog=d, name="indoor").isChecked()
        ),
        flags=None,
        group_id=None,
        description=None,
        flags_disabled=False,
    )
    assert seen["checked"] is False


def test_flags_disabled_survives_text_edit_rebuild(qtbot: QtBot) -> None:
    seen: dict[str, list[bool]] = {}

    def edit_then_inspect(d: LabelDialog) -> None:
        d.edit.setText("cattle")
        seen.update(enabled=[cb.isEnabled() for cb in _checkboxes(d)])

    dialog = _add_dialog(
        qtbot, dialog=LabelDialog(flags={"^cat": ["indoor", "outdoor"]})
    )
    _run_popup(
        dialog=dialog,
        accept=True,
        text="cat",
        flags_disabled=True,
        at_show=edit_then_inspect,
        flags=None,
        group_id=None,
        description=None,
    )
    assert seen["enabled"]
    assert not any(seen["enabled"])
