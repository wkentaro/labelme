from __future__ import annotations

from collections.abc import Callable
from collections.abc import Iterator

import pytest
from PySide6 import QtCore
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from labelme import _locale
from labelme._widgets.label_dialog import LabelDialog


@pytest.fixture
def make_dialog(qtbot: QtBot) -> Callable[[], LabelDialog]:
    def create_dialog() -> LabelDialog:
        dialog = LabelDialog(labels=["cat"])
        qtbot.addWidget(dialog)
        return dialog

    return create_dialog


@pytest.fixture
def install_japanese_translator(qapp: QApplication) -> Iterator[None]:
    translator = QtCore.QTranslator()
    assert translator.load(str(_locale.TRANSLATE_DIR / "ja_JP.qm"))
    qapp.installTranslator(translator)
    yield
    qapp.removeTranslator(translator)


@pytest.mark.parametrize(
    ("text", "group_id", "description"),
    [
        pytest.param(None, None, None, id="new-shape"),
        pytest.param("cat", 7, "a pet", id="existing-shape"),
    ],
)
def test_popup_exposes_accessible_names(
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


def test_label_precedes_group_id_in_focus_order(
    make_dialog: Callable[[], LabelDialog],
) -> None:
    dialog = make_dialog()
    assert dialog.edit.nextInFocusChain() is dialog.edit_group_id


@pytest.mark.usefixtures("install_japanese_translator")
def test_accessible_names_use_installed_translation(
    make_dialog: Callable[[], LabelDialog],
) -> None:
    dialog = make_dialog()

    assert dialog.windowTitle() == "図形のラベル"
    assert dialog.accessibleName() == "図形のラベル"
    assert dialog.edit.accessibleName() == "ラベル"
    assert dialog.edit_group_id.accessibleName() == "グループ ID"
    assert dialog.edit_group_id.placeholderText() == "グループ ID"
    assert dialog.edit_description.accessibleName() == "説明"
    assert dialog.edit_description.placeholderText() == "説明"
