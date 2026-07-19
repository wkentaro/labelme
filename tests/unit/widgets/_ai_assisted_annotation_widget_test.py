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


def test_first_listed_default_still_pushes_model(
    qtbot: QtBot, models: list[str], formats: list[AiOutputFormat]
) -> None:
    _make_widget(
        qtbot=qtbot,
        models=models,
        formats=formats,
        default_model="EfficientSam (speed)",
    )
    assert models == ["efficientsam:10m"]
    assert formats == ["polygon"]


def test_non_first_default_pushes_model(
    qtbot: QtBot, models: list[str], formats: list[AiOutputFormat]
) -> None:
    _make_widget(
        qtbot=qtbot,
        models=models,
        formats=formats,
        default_model="Sam2 (balanced)",
    )
    assert models == ["sam2:latest"]
    assert formats == ["polygon"]


def test_unknown_default_falls_back_to_first_model(
    qtbot: QtBot, models: list[str], formats: list[AiOutputFormat]
) -> None:
    _make_widget(
        qtbot=qtbot,
        models=models,
        formats=formats,
        default_model="does-not-exist",
    )
    assert models == ["efficientsam:10m"]


def test_selecting_another_model_pushes_it(
    qtbot: QtBot, models: list[str], formats: list[AiOutputFormat]
) -> None:
    widget = _make_widget(
        qtbot=qtbot,
        models=models,
        formats=formats,
        default_model="EfficientSam (speed)",
    )
    models.clear()
    widget._model_combo.setCurrentIndex(widget._model_combo.findData("sam2:latest"))
    assert models == ["sam2:latest"]
