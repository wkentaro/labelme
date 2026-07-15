from __future__ import annotations

import pytest
from pytestqt.qtbot import QtBot

from labelme._widgets.label_dialog import LabelDialog


def _labels(dialog: LabelDialog) -> set[str]:
    label_list = dialog.label_list
    return {label_list.item(i).text() for i in range(label_list.count())}


@pytest.fixture
def dialog(qtbot: QtBot) -> LabelDialog:
    label_dialog = LabelDialog(labels=["cat", "dog"])
    qtbot.addWidget(label_dialog)
    return label_dialog


def test_set_predefined_labels_adds_new_label(dialog: LabelDialog) -> None:
    dialog.set_predefined_labels(["cat", "dog", "bird"])
    assert _labels(dialog) == {"cat", "dog", "bird"}


def test_set_predefined_labels_removes_unused_label(dialog: LabelDialog) -> None:
    dialog.set_predefined_labels(["cat"])
    assert _labels(dialog) == {"cat"}


def test_set_predefined_labels_preserves_session_history(dialog: LabelDialog) -> None:
    dialog.add_label_history("ad-hoc")
    dialog.set_predefined_labels(["cat", "dog", "bird"])
    assert _labels(dialog) == {"cat", "dog", "bird", "ad-hoc"}


def test_removed_predefined_label_kept_when_used_this_session(
    dialog: LabelDialog,
) -> None:
    dialog.add_label_history("dog")
    dialog.set_predefined_labels(["cat"])
    assert _labels(dialog) == {"cat", "dog"}


def test_completer_model_stays_bound_after_update(dialog: LabelDialog) -> None:
    dialog.set_predefined_labels(["cat", "dog", "bird"])
    assert dialog.edit.completer().model() is dialog.label_list.model()


def test_set_predefined_labels_with_selected_item_does_not_raise(
    dialog: LabelDialog,
) -> None:
    dialog.label_list.setCurrentRow(0)
    dialog.set_predefined_labels(["cat", "dog", "bird"])
    assert _labels(dialog) == {"cat", "dog", "bird"}


def test_set_predefined_labels_empty_keeps_only_session_history(
    dialog: LabelDialog,
) -> None:
    dialog.add_label_history("ad-hoc")
    dialog.set_predefined_labels([])
    assert _labels(dialog) == {"ad-hoc"}


def test_update_flags_skips_an_invalid_pattern(qtbot: QtBot) -> None:
    dialog = LabelDialog(labels=["cat"], flags={"cat(": ["occluded"]})
    qtbot.addWidget(dialog)
    dialog._update_flags("cat")
    assert dialog._flag_checkboxes() == []


def test_update_flags_applies_a_valid_pattern_despite_an_invalid_one(
    qtbot: QtBot,
) -> None:
    dialog = LabelDialog(
        labels=["cat"], flags={"cat(": ["broken"], "cat": ["occluded"]}
    )
    qtbot.addWidget(dialog)
    dialog._update_flags("cat")
    assert [cb.text() for cb in dialog._flag_checkboxes()] == ["occluded"]
