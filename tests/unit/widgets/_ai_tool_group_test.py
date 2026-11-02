from __future__ import annotations

import pytest
from PySide6 import QtCore
from PySide6 import QtWidgets
from pytestqt.qtbot import QtBot

from labelme._widgets._ai_assisted_annotation_widget import AiAssistedAnnotationWidget
from labelme._widgets._ai_text_to_annotation_widget import AiTextToAnnotationWidget
from labelme._widgets._ai_tool_group import AiToolGroup


def _new_group() -> AiToolGroup:
    return AiToolGroup(
        assist=AiAssistedAnnotationWidget(
            default_model="Sam2 (balanced)",
            polygon_detail=80,
            on_model_changed=lambda _: None,
            on_output_format_changed=lambda _: None,
            on_polygon_detail_changed=lambda _: None,
        ),
        detect=AiTextToAnnotationWidget(on_submit=lambda: None),
    )


@pytest.fixture
def group(*, qtbot: QtBot) -> AiToolGroup:
    group = _new_group()
    qtbot.addWidget(group)
    group.show()
    return group


@pytest.mark.gui
def test_every_control_works_from_any_tool(*, group: AiToolGroup) -> None:
    # Running switches to AI-Find All, so no control waits for an AI tool.
    for control in (
        group._detect._text_input,
        group._detect._run_button,
        group._detect._model_combo,
        group._assist._output_format_button,
        group._options_button,
    ):
        assert control.isVisible()
        assert control.isEnabled()
    assert group.minimumWidth() == group.maximumWidth()


@pytest.mark.gui
def test_run_sits_inside_the_query_field(*, group: AiToolGroup) -> None:
    text_input = group._detect._text_input
    run_button = group._detect._run_button

    assert run_button.parentWidget() is text_input
    assert text_input.rect().contains(run_button.geometry())
    # Typed text stops short of Run.
    assert text_input.textMargins().right() >= run_button.width()


@pytest.mark.gui
def test_run_keeps_clear_of_right_to_left_text(*, qtbot: QtBot) -> None:
    QtWidgets.QApplication.setLayoutDirection(QtCore.Qt.LayoutDirection.RightToLeft)
    try:
        group = _new_group()
        qtbot.addWidget(group)
        group.show()
        text_input = group._detect._text_input

        assert group._detect._run_button.x() < text_input.width() // 2
        assert text_input.textMargins().left() >= group._detect._run_button.width()
    finally:
        QtWidgets.QApplication.setLayoutDirection(QtCore.Qt.LayoutDirection.LeftToRight)


@pytest.mark.gui
def test_options_holds_the_ai_segment_model(*, group: AiToolGroup) -> None:
    menu = group._options_button.menu()

    assert menu.isAncestorOf(group._assist._model_combo)


@pytest.mark.gui
def test_run_reads_detecting_while_a_job_runs(*, group: AiToolGroup) -> None:
    detect = group._detect

    detect.set_detecting(True)  # noqa: FBT003 -- state flag

    assert detect._run_button.text() == "Finding…"

    detect.set_detecting(False)  # noqa: FBT003 -- state flag

    assert detect._run_button.text() == AiTextToAnnotationWidget._RUN_GLYPH


@pytest.mark.gui
def test_options_button_marks_thresholds_off_their_defaults(
    *, group: AiToolGroup
) -> None:
    assert not group._options_button._changed

    group._detect._score_spinbox.setValue(0.3)
    assert group._options_button._changed

    group._detect._score_spinbox.setValue(group._detect._default_score_threshold)
    assert not group._options_button._changed


@pytest.mark.gui
def test_tab_moves_between_fields_in_options(
    *, group: AiToolGroup, qtbot: QtBot
) -> None:
    menu = group._options_button.menu()
    menu.popup(group._options_button.mapToGlobal(QtCore.QPoint(0, 0)))
    qtbot.waitExposed(menu)
    score, iou = group._detect._score_spinbox, group._detect._iou_spinbox
    score.setFocus()

    qtbot.keyClick(QtWidgets.QApplication.focusWidget(), QtCore.Qt.Key.Key_Tab)
    assert iou.hasFocus()

    qtbot.keyClick(
        QtWidgets.QApplication.focusWidget(),
        QtCore.Qt.Key.Key_Tab,
        QtCore.Qt.KeyboardModifier.ShiftModifier,
    )
    assert score.hasFocus()
    menu.hide()
