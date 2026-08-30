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
    *,
    qtbot: QtBot,
    models: list[str],
    formats: list[AiOutputFormat],
    default_model: str,
    details: list[int] | None,
) -> AiAssistedAnnotationWidget:
    widget = AiAssistedAnnotationWidget(
        default_model=default_model,
        polygon_detail=80,
        on_model_changed=models.append,
        on_output_format_changed=formats.append,
        on_polygon_detail_changed=([] if details is None else details).append,
    )
    qtbot.addWidget(widget)
    return widget


def test_construction_exposes_default_without_firing_callbacks(
    *, qtbot: QtBot, models: list[str], formats: list[AiOutputFormat]
) -> None:
    widget = _make_widget(
        qtbot=qtbot,
        models=models,
        formats=formats,
        default_model="Sam2 (balanced)",
        details=None,
    )
    assert widget.current_model_id == "sam2:latest"
    assert widget.output_format == "polygon"
    assert models == []
    assert formats == []


def test_first_listed_default_resolves(
    *, qtbot: QtBot, models: list[str], formats: list[AiOutputFormat]
) -> None:
    widget = _make_widget(
        qtbot=qtbot,
        models=models,
        formats=formats,
        default_model="EfficientSam (speed)",
        details=None,
    )
    assert widget.current_model_id == "efficientsam:10m"


def test_unknown_default_falls_back_to_first_model(
    *, qtbot: QtBot, models: list[str], formats: list[AiOutputFormat]
) -> None:
    widget = _make_widget(
        qtbot=qtbot,
        models=models,
        formats=formats,
        default_model="does-not-exist",
        details=None,
    )
    assert widget.current_model_id == "efficientsam:10m"


def test_selecting_another_model_fires_callback(
    *, qtbot: QtBot, models: list[str], formats: list[AiOutputFormat]
) -> None:
    widget = _make_widget(
        qtbot=qtbot,
        models=models,
        formats=formats,
        default_model="EfficientSam (speed)",
        details=None,
    )
    widget._model_combo.setCurrentIndex(widget._model_combo.findData("sam2:latest"))
    assert models == ["sam2:latest"]


def test_selecting_another_output_format_fires_callback(
    *, qtbot: QtBot, models: list[str], formats: list[AiOutputFormat]
) -> None:
    widget = _make_widget(
        qtbot=qtbot,
        models=models,
        formats=formats,
        default_model="EfficientSam (speed)",
        details=None,
    )
    widget._output_format_combo.setCurrentIndex(
        widget._output_format_combo.findData("mask")
    )
    assert formats == ["mask"]
    assert not widget._polygon_detail_button.isVisibleTo(widget)

    widget._output_format_combo.setCurrentIndex(
        widget._output_format_combo.findData("polygon")
    )
    assert widget._polygon_detail_button.isVisibleTo(widget)


def test_polygon_detail_control_fires_callback_and_exposes_value(
    *, qtbot: QtBot, models: list[str], formats: list[AiOutputFormat]
) -> None:
    details: list[int] = []
    widget = _make_widget(
        qtbot=qtbot,
        models=models,
        formats=formats,
        default_model="EfficientSam (speed)",
        details=details,
    )

    widget._polygon_detail_slider.set_value(60)

    assert details == [60]
    assert widget._polygon_detail_slider.value == 60
    assert widget._polygon_detail_button.accessibleName() == "Polygon detail"


def test_setting_polygon_detail_from_config_does_not_fire_callback(
    *, qtbot: QtBot, models: list[str], formats: list[AiOutputFormat]
) -> None:
    details: list[int] = []
    widget = _make_widget(
        qtbot=qtbot,
        models=models,
        formats=formats,
        default_model="EfficientSam (speed)",
        details=details,
    )

    widget.set_polygon_detail(75)

    assert widget._polygon_detail_slider.value == 75
    assert details == []
