from __future__ import annotations

import pytest
from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets
from pytestqt.qtbot import QtBot

from labelme._widgets._ai_assisted_annotation_widget import AiAssistedAnnotationWidget
from labelme._widgets._ai_text_to_annotation_widget import AiTextToAnnotationWidget
from labelme._widgets._ai_tool_group import AiToolGroup


@pytest.fixture
def group(*, qtbot: QtBot) -> AiToolGroup:
    group = AiToolGroup(
        assist=AiAssistedAnnotationWidget(
            default_model="Sam2 (balanced)",
            polygon_detail=80,
            on_model_changed=lambda _: None,
            on_output_format_changed=lambda _: None,
            on_polygon_detail_changed=lambda _: None,
        ),
        detect=AiTextToAnnotationWidget(on_submit=lambda: None),
    )
    qtbot.addWidget(group)
    group.show()
    return group


@pytest.mark.gui
@pytest.mark.parametrize(
    ("create_mode", "title", "is_find_all"),
    [
        ("ai_segment", "AI-Segment", False),
        ("ai_find_all", "AI-Find All", True),
    ],
)
def test_group_follows_the_active_tool(
    *, group: AiToolGroup, create_mode: str, title: str, is_find_all: bool
) -> None:
    width = group.width()
    output_geometry = group._assist._output_format_button.geometry()

    group.set_tool(create_mode)

    assert group._title.text() == title
    assert group._model_stack.isEnabled()
    assert group._assist._output_format_button.isEnabled()
    for control in (group._detect._text_input, group._detect._run_button):
        assert control.isEnabled()  # Running switches to AI-Find All.
    assert group._model_stack.currentWidget() is (
        group._detect._model_combo if is_find_all else group._assist._model_combo
    )
    assert group.width() == width
    assert group._assist._output_format_button.geometry() == output_geometry


@pytest.mark.gui
def test_only_the_query_and_run_work_without_an_ai_tool(
    *, group: AiToolGroup, qtbot: QtBot
) -> None:
    group.set_tool("ai_find_all")

    group.set_tool("polygon")

    assert group._title.text() == "AI Assist"
    assert group._detect._text_input.isEnabled()
    assert group._detect._run_button.isEnabled()
    for control in (group._model_stack, group._assist._output_format_button):
        assert not control.isEnabled()
    # Run uses the thresholds from any tool.
    assert group._options_button.isEnabled()
    with qtbot.waitSignal(group.hover_highlight_requested) as blocker:
        QtWidgets.QApplication.sendEvent(
            group._model_stack, QtCore.QEvent(QtCore.QEvent.Type.Enter)
        )
    assert blocker.args == [True]


@pytest.mark.gui
def test_info_button_names_the_tool(*, group: AiToolGroup) -> None:
    group.set_tool("ai_find_all")

    interface = QtGui.QAccessible.queryAccessibleInterface(group._info_button)

    assert interface.text(QtGui.QAccessible.Text.Name) == (
        "Find every object that matches the text prompt or an example box"
    )


@pytest.mark.gui
def test_run_reads_detecting_while_a_job_runs(*, group: AiToolGroup) -> None:
    group.set_tool("ai_find_all")
    detect = group._detect

    detect.set_detecting(True)  # noqa: FBT003 -- state flag

    assert detect._run_button.text() == "Finding…"

    detect.set_detecting(False)  # noqa: FBT003 -- state flag

    assert detect._run_button.text() == "Run"


@pytest.mark.gui
def test_options_button_marks_thresholds_off_their_defaults(
    *, group: AiToolGroup
) -> None:
    assert not group._options_button._changed

    group._detect._score_spinbox.setValue(0.3)
    assert group._options_button._changed

    group._detect._score_spinbox.setValue(group._detect._default_score_threshold)
    assert not group._options_button._changed
