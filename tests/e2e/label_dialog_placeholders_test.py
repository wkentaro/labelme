from __future__ import annotations

import pytest
from pytestqt.qtbot import QtBot

from labelme._locale import TRANSLATE_DIR

from .conftest import MainWinFactory


@pytest.mark.gui
@pytest.mark.parametrize(
    "language", ["en_US", *sorted(path.stem for path in TRANSLATE_DIR.glob("*.qm"))]
)
def test_label_dialog_placeholders_fit(
    *, main_win: MainWinFactory, qtbot: QtBot, language: str
) -> None:
    dialog = main_win(config_overrides={"language": language})._label_dialog
    dialog.show()
    qtbot.waitExposed(dialog)
    for field in (dialog.edit, dialog.edit_group_id):
        text = field.placeholderText()
        assert text != "Enter object label" or language == "en_US"
        # QLineEdit insets its text a few pixels from each side of the frame.
        room = field.contentsRect().width() - 8
        assert field.fontMetrics().horizontalAdvance(text) <= room, text
    dialog.close()
