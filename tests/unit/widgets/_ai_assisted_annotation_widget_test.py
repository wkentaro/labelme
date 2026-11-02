from __future__ import annotations

import sys

import pytest
from PySide6 import QtGui
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
    model_name: str,
    details: list[int] | None,
) -> AiAssistedAnnotationWidget:
    widget = AiAssistedAnnotationWidget(
        model_name=model_name,
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
        model_name="sam2:latest",
        details=None,
    )
    assert widget.current_model_id == "sam2:latest"
    assert widget.output_format == "polygon"
    assert models == []
    assert formats == []


def test_model_and_output_controls_expose_accessible_purpose(
    *, qtbot: QtBot, models: list[str], formats: list[AiOutputFormat]
) -> None:
    widget = _make_widget(
        qtbot=qtbot,
        models=models,
        formats=formats,
        model_name="efficientsam:10m",
        details=None,
    )

    model = QtGui.QAccessible.queryAccessibleInterface(widget._model_combo)
    output = QtGui.QAccessible.queryAccessibleInterface(widget._output_format_button)
    model_name = (
        widget.tr("Model") if sys.platform == "win32" else "EfficientSam (speed)"
    )
    assert model.text(QtGui.QAccessible.Text.Name) == model_name
    assert model.text(QtGui.QAccessible.Text.Value) == "EfficientSam (speed)"
    assert model.text(QtGui.QAccessible.Text.Description) == widget.tr(
        "AI-assisted annotation model"
    )
    assert output.text(QtGui.QAccessible.Text.Name) == "Output format: Polygon"
    assert output.text(QtGui.QAccessible.Text.Description) == widget.tr(
        "AI-assisted annotation output format"
    )


def test_first_listed_default_resolves(
    *, qtbot: QtBot, models: list[str], formats: list[AiOutputFormat]
) -> None:
    widget = _make_widget(
        qtbot=qtbot,
        models=models,
        formats=formats,
        model_name="efficientsam:10m",
        details=None,
    )
    assert widget.current_model_id == "efficientsam:10m"


def test_unknown_default_leaves_model_unselected(
    *, qtbot: QtBot, models: list[str], formats: list[AiOutputFormat]
) -> None:
    widget = _make_widget(
        qtbot=qtbot,
        models=models,
        formats=formats,
        model_name="does-not-exist",
        details=None,
    )
    assert widget.current_model_id == ""


def test_selecting_another_model_fires_callback(
    *, qtbot: QtBot, models: list[str], formats: list[AiOutputFormat]
) -> None:
    widget = _make_widget(
        qtbot=qtbot,
        models=models,
        formats=formats,
        model_name="efficientsam:10m",
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
        model_name="efficientsam:10m",
        details=None,
    )
    widget._output_format_actions["mask"].trigger()
    assert formats == ["mask"]
    assert widget.output_format == "mask"
    assert widget._output_format_button.toolTip() == "Mask"
    assert not widget._polygon_detail_panel.isVisibleTo(widget)

    widget._output_format_actions["mask"].trigger()
    assert formats == ["mask"]  # Picking the current shape again is a no-op.

    widget._output_format_actions["polygon"].trigger()
    assert formats == ["mask", "polygon"]
    assert widget._output_format_actions["polygon"].isChecked()
    assert not widget._output_format_actions["mask"].isChecked()
    assert widget._polygon_detail_panel.isVisibleTo(widget)


def test_polygon_detail_control_fires_callback_and_exposes_value(
    *, qtbot: QtBot, models: list[str], formats: list[AiOutputFormat]
) -> None:
    details: list[int] = []
    widget = _make_widget(
        qtbot=qtbot,
        models=models,
        formats=formats,
        model_name="efficientsam:10m",
        details=details,
    )

    widget._polygon_detail_slider.set_value(60)

    assert details == [60]
    assert widget._polygon_detail_slider.value == 60
    assert widget._polygon_detail_slider.accessibleName() == "Polygon detail"


def test_setting_polygon_detail_from_config_does_not_fire_callback(
    *, qtbot: QtBot, models: list[str], formats: list[AiOutputFormat]
) -> None:
    details: list[int] = []
    widget = _make_widget(
        qtbot=qtbot,
        models=models,
        formats=formats,
        model_name="efficientsam:10m",
        details=details,
    )

    widget.set_polygon_detail(75)

    assert widget._polygon_detail_slider.value == 75
    assert details == []
