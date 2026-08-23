from __future__ import annotations

import pytest
from pytestqt.qtbot import QtBot

import labelme._widgets._ai_text_to_annotation_widget as widget_module
from labelme._widgets._ai_text_to_annotation_widget import AiTextToAnnotationWidget
from labelme._widgets._info_button import InfoButton


def test_distribution_allowlist_excludes_sam3(
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LABELME_AI_MODEL_ALLOWLIST", "yoloworld:latest")
    widget = AiTextToAnnotationWidget(on_submit=lambda checked: None)
    qtbot.addWidget(widget)

    assert widget._model_combo.count() == 1
    assert widget.get_model_name() == "yoloworld:latest"


def test_model_info_button_uses_current_model(
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested_models: list[str] = []

    def record_model(*, model_name: str, parent: object) -> None:
        requested_models.append(model_name)

    monkeypatch.setattr(widget_module, "show_ai_model_info", record_model)
    widget = AiTextToAnnotationWidget(on_submit=lambda checked: None)
    qtbot.addWidget(widget)

    info_button = widget.findChild(InfoButton)
    assert info_button is not None
    info_button.click()

    assert requested_models == ["yoloworld:latest"]


def test_distribution_without_text_models_stays_disabled(
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LABELME_AI_MODEL_ALLOWLIST", "sam2:latest")
    widget = AiTextToAnnotationWidget(on_submit=lambda checked: None)
    qtbot.addWidget(widget)

    widget.setEnabled(True)

    assert widget._body.isEnabled() is False
    assert widget._body.toolTip() == "No text-to-annotation model is included."
    with pytest.raises(ValueError, match="No text-to-annotation model"):
        widget.get_model_name()
