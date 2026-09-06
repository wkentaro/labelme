from __future__ import annotations

from collections.abc import Callable
from collections.abc import Iterator

import pytest
from PySide6 import QtCore
from PySide6 import QtWidgets
from pytestqt.qtbot import QtBot

from labelme import _locale
from labelme._widgets.label_dialog import LabelDialog


@pytest.fixture
def make_dialog(*, qtbot: QtBot) -> Callable[[], LabelDialog]:
    def create_dialog() -> LabelDialog:
        dialog = LabelDialog(labels=["cat"])
        qtbot.addWidget(dialog)
        return dialog

    return create_dialog


@pytest.mark.parametrize(
    ("text", "group_id", "description"),
    [
        pytest.param(None, None, None, id="new-shape"),
        pytest.param("cat", 7, "a pet", id="existing-shape"),
    ],
)
def test_popup_exposes_accessible_names(
    *,
    make_dialog: Callable[[], LabelDialog],
    text: str | None,
    group_id: int | None,
    description: str | None,
) -> None:
    dialog = make_dialog()
    observed: dict[str, str] = {}

    def inspect_dialog() -> None:
        observed.update(
            dialog=dialog.accessibleName(),
            title=dialog.windowTitle(),
            label=dialog.edit.accessibleName(),
            group_id=dialog.edit_group_id.accessibleName(),
            description=dialog.edit_description.accessibleName(),
        )
        dialog.reject()

    QtCore.QTimer.singleShot(0, inspect_dialog)
    dialog.popup(
        text=text,
        move=False,
        group_id=group_id,
        description=description,
    )

    assert observed == {
        "dialog": dialog.tr("Shape Label"),
        "title": dialog.tr("Shape Label"),
        "label": dialog.tr("Label"),
        "group_id": dialog.tr("Group ID"),
        "description": dialog.tr("Description"),
    }


def test_choices_and_flags_container_do_not_create_anonymous_focus_stops(
    *, make_dialog: Callable[[], LabelDialog]
) -> None:
    dialog = make_dialog()

    assert dialog.label_list.accessibleName() == dialog.tr("Label choices")
    assert dialog._flags_scroll.accessibleName() == dialog.tr("Label flags")
    assert dialog._flags_scroll.focusPolicy() == QtCore.Qt.FocusPolicy.NoFocus


def test_label_precedes_group_id_in_focus_order(
    *,
    make_dialog: Callable[[], LabelDialog],
    qtbot: QtBot,
) -> None:
    dialog = make_dialog()
    with qtbot.waitExposed(dialog):
        dialog.show()
    dialog.edit.setFocus()

    qtbot.keyClick(dialog.edit, QtCore.Qt.Key.Key_Tab)

    assert QtWidgets.QApplication.focusWidget() is dialog.edit_group_id


def test_label_choices_precede_dynamic_flags_in_focus_order(*, qtbot: QtBot) -> None:
    dialog = LabelDialog(labels=["dog"], flags={"dog": ["leash", "collar"]})
    qtbot.addWidget(dialog)
    dialog.edit.setText("dog")
    with qtbot.waitExposed(dialog):
        dialog.show()
    dialog.label_list.setFocus()

    qtbot.keyClick(dialog.label_list, QtCore.Qt.Key.Key_Tab)
    assert QtWidgets.QApplication.focusWidget() is dialog._flag_checkboxes["leash"]

    qtbot.keyClick(dialog._flag_checkboxes["leash"], QtCore.Qt.Key.Key_Tab)
    assert QtWidgets.QApplication.focusWidget() is dialog._flag_checkboxes["collar"]

    qtbot.keyClick(dialog._flag_checkboxes["collar"], QtCore.Qt.Key.Key_Tab)
    assert QtWidgets.QApplication.focusWidget() is dialog.edit_description


def test_group_id_has_a_visible_buddy_label_at_default_fusion_size(
    *, make_dialog: Callable[[], LabelDialog], qtbot: QtBot
) -> None:
    dialog = make_dialog()
    fusion = QtWidgets.QStyleFactory.create("Fusion")
    assert fusion is not None
    dialog.setStyle(fusion)
    with qtbot.waitExposed(dialog):
        dialog.show()

    group_id_label = next(
        label
        for label in dialog.findChildren(QtWidgets.QLabel)
        if label.buddy() is dialog.edit_group_id
    )
    assert group_id_label.text() == dialog.tr("Group ID")
    assert group_id_label.isVisibleTo(dialog)
    assert group_id_label.width() >= group_id_label.sizeHint().width()


@pytest.fixture()
def install_japanese_translator(*, qapp: QtWidgets.QApplication) -> Iterator[None]:
    translator = QtCore.QTranslator()
    assert translator.load(str(_locale.TRANSLATE_DIR / "ja_JP.qm"))
    qapp.installTranslator(translator)
    yield
    qapp.removeTranslator(translator)


@pytest.mark.usefixtures("install_japanese_translator")
def test_accessible_names_use_installed_translation(
    *, make_dialog: Callable[[], LabelDialog]
) -> None:
    dialog = make_dialog()
    for widget, source in [
        (dialog, "Shape Label"),
        (dialog.edit, "Label"),
        (dialog.edit_group_id, "Group ID"),
        (dialog.edit_description, "Description"),
        (dialog.label_list, "Label choices"),
        (dialog._flags_scroll, "Label flags"),
    ]:
        translated = QtCore.QCoreApplication.translate("LabelDialog", source)
        assert translated != source
        assert widget.accessibleName() == translated
    assert dialog.windowTitle() == dialog.accessibleName()
    assert dialog.edit.placeholderText() == dialog.edit.accessibleName()
    assert (
        dialog.edit_group_id.placeholderText() == dialog.edit_group_id.accessibleName()
    )
    assert (
        dialog.edit_description.placeholderText()
        == dialog.edit_description.accessibleName()
    )
