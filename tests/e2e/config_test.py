from __future__ import annotations

from pathlib import Path

import pytest
from PyQt5 import QtWidgets
from pytestqt.qtbot import QtBot

import labelme.app


@pytest.mark.gui
@pytest.mark.parametrize(
    "with_config_file",
    [
        pytest.param(True, id="with_config_file"),
        pytest.param(False, id="without_config_file"),
    ],
)
def test_MainWindow_config(
    with_config_file: bool,
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_file: Path | None = None
    auto_save: bool = False
    if with_config_file:
        config_file = tmp_path / "labelmerc.yaml"
        config_file.write_text("auto_save: true\nlabels: [cat, dog]\n")
        auto_save = True

    win: labelme.app.MainWindow = labelme.app.MainWindow(
        config_file=config_file,
        config_overrides={"labels": ["bird"]},
    )
    qtbot.addWidget(win)
    win.show()

    assert win._config["auto_save"] is auto_save
    assert win._config["labels"] == ["bird"]
    assert win._config_file == config_file

    if not with_config_file:
        message_box_shown: list[bool] = [False]

        def mock_information(parent, title, message):
            message_box_shown[0] = True
            assert "No Config File" in title
            return QtWidgets.QMessageBox.Ok

        monkeypatch.setattr(QtWidgets.QMessageBox, "information", mock_information)

        win._open_config_file()
        assert message_box_shown[0] is True

    win.close()
