from __future__ import annotations

import pytest
from pytestqt.qtbot import QtBot

from labelme._automation import AiOutputFormat
from labelme._widgets._ai_assisted_annotation_widget import AiAssistedAnnotationWidget


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
