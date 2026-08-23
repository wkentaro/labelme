from __future__ import annotations

import pytest
from pytestqt.qtbot import QtBot

import labelme._widgets._ai_assisted_annotation_widget as widget_module
from labelme._automation import AiOutputFormat
from labelme._widgets._ai_assisted_annotation_widget import AiAssistedAnnotationWidget
from labelme._widgets._info_button import InfoButton


@pytest.fixture
def models() -> list[str]:
    return []


@pytest.fixture
def formats() -> list[AiOutputFormat]:
    return []


def _make_widget(
    qtbot: QtBot,
    models: list[str],
    formats: list[AiOutputFormat],
    default_model: str,
) -> AiAssistedAnnotationWidget:
    widget = AiAssistedAnnotationWidget(
        default_model=default_model,
        on_model_changed=models.append,
        on_output_format_changed=formats.append,
    )
    qtbot.addWidget(widget)
    return widget


def test_construction_exposes_default_without_firing_callbacks(
    qtbot: QtBot, models: list[str], formats: list[AiOutputFormat]
) -> None:
    widget = _make_widget(
        qtbot=qtbot,
        models=models,
        formats=formats,
        default_model="Sam2 (balanced)",
    )
    assert widget.current_model_id == "sam2:latest"
    assert widget.output_format == "polygon"
    assert models == []
    assert formats == []


def test_first_listed_default_resolves(
    qtbot: QtBot, models: list[str], formats: list[AiOutputFormat]
) -> None:
    widget = _make_widget(
        qtbot=qtbot,
        models=models,
        formats=formats,
        default_model="EfficientSam (speed)",
    )
    assert widget.current_model_id == "efficientsam:10m"


def test_unknown_default_falls_back_to_first_model(
    qtbot: QtBot, models: list[str], formats: list[AiOutputFormat]
) -> None:
    widget = _make_widget(
        qtbot=qtbot,
        models=models,
        formats=formats,
        default_model="does-not-exist",
    )
    assert widget.current_model_id == "efficientsam:10m"


def test_selecting_another_model_fires_callback(
    qtbot: QtBot, models: list[str], formats: list[AiOutputFormat]
) -> None:
    widget = _make_widget(
        qtbot=qtbot,
        models=models,
        formats=formats,
        default_model="EfficientSam (speed)",
    )
    widget._model_combo.setCurrentIndex(widget._model_combo.findData("sam2:latest"))
    assert models == ["sam2:latest"]


def test_selecting_another_output_format_fires_callback(
    qtbot: QtBot, models: list[str], formats: list[AiOutputFormat]
) -> None:
    widget = _make_widget(
        qtbot=qtbot,
        models=models,
        formats=formats,
        default_model="EfficientSam (speed)",
    )
    widget._output_format_combo.setCurrentIndex(
        widget._output_format_combo.findData("mask")
    )
    assert formats == ["mask"]


def test_model_info_button_uses_current_model(
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    models: list[str],
    formats: list[AiOutputFormat],
) -> None:
    requested_models: list[str] = []

    def record_model(*, model_name: str, parent: object) -> None:
        requested_models.append(model_name)

    monkeypatch.setattr(widget_module, "show_ai_model_info", record_model)
    widget = _make_widget(
        qtbot=qtbot,
        models=models,
        formats=formats,
        default_model="Sam2 (balanced)",
    )

    info_button = widget.findChild(InfoButton)
    assert info_button is not None
    assert info_button.accessibleName() == "Model license and source"
    info_button.click()

    assert requested_models == ["sam2:latest"]


def test_distribution_requires_an_ai_assist_model(
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    models: list[str],
    formats: list[AiOutputFormat],
) -> None:
    monkeypatch.setenv("LABELME_AI_MODEL_ALLOWLIST", "yoloworld:latest")

    with pytest.raises(ValueError, match="must include an AI Assist model"):
        _make_widget(
            qtbot=qtbot,
            models=models,
            formats=formats,
            default_model="Sam2 (balanced)",
        )
