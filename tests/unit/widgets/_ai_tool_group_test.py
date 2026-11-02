from __future__ import annotations

import pytest
from PySide6 import QtCore
from PySide6 import QtWidgets
from pytestqt.qtbot import QtBot

from labelme._widgets._ai_assisted_annotation_widget import AiAssistedAnnotationWidget
from labelme._widgets._ai_text_to_annotation_widget import AiTextToAnnotationWidget
from labelme._widgets._ai_tool_group import AiToolGroup


def _new_group() -> AiToolGroup:
    detect = AiTextToAnnotationWidget(on_submit=lambda: None)
    detect.set_model_name(model_name="sam3:latest")
    return AiToolGroup(
        assist=AiAssistedAnnotationWidget(
            model_name="sam2:latest",
            polygon_detail=80,
            on_model_changed=lambda _: None,
            on_output_format_changed=lambda _: None,
            on_polygon_detail_changed=lambda _: None,
        ),
        detect=detect,
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
        group._model_button,
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


def _menu_texts(menu: QtWidgets.QMenu, /) -> list[str]:
    return [action.text() for action in menu.actions() if not action.isSeparator()]


@pytest.mark.gui
def test_model_menu_has_a_section_per_tool(*, group: AiToolGroup) -> None:
    menu = group._model_button._build_menu()
    texts = _menu_texts(menu)

    segment = texts.index("AI-Segment")
    find_all = texts.index("AI-Find All")
    assert "SAM 2 Base+" in texts[segment:find_all]
    assert "YOLO-World\tBoxes only" in texts[find_all:]
    assert texts[-1] == "Manage models…"
    # The original SAM folds away; SAM 2 and SAM 3 lead.
    more = next(a.menu() for a in menu.actions() if a.text() == "More models…")
    assert isinstance(more, QtWidgets.QMenu)
    assert _menu_texts(more) == ["SAM Base", "SAM Large", "SAM Huge"]
    checked = [a.text() for a in menu.actions() if a.isChecked()]
    assert checked == ["SAM 2 Base+", "SAM 3"]


@pytest.mark.gui
def test_model_button_names_one_model_when_both_tools_share_it(
    *, group: AiToolGroup
) -> None:
    assert group._model_button.currentText() == "SAM 2 Base+ · SAM 3"

    group._assist.select_model("sam3:latest")

    assert group._model_button.currentText() == "SAM 3"
    assert group._model_button.toolTip() == "AI-Segment: SAM 3\nAI-Find All: SAM 3"


@pytest.mark.gui
def test_choosing_from_the_model_menu_selects_that_tools_model(
    *, group: AiToolGroup
) -> None:
    menu = group._model_button._build_menu()
    yolo = next(a for a in menu.actions() if a.text().startswith("YOLO-World"))

    yolo.trigger()

    assert group._detect.get_model_name() == "yoloworld:latest"
    assert group._assist.current_model_id == "sam2:latest"
    assert group._model_button.currentText() == "SAM 2 Base+ · YOLO-World"


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


@pytest.mark.gui
def test_model_button_opens_the_model_menu(*, group: AiToolGroup, qtbot: QtBot) -> None:
    group._model_button.showPopup()
    menu = QtWidgets.QApplication.activePopupWidget()
    assert isinstance(menu, QtWidgets.QMenu)
    qtbot.waitExposed(menu)
    assert "AI-Find All" in _menu_texts(menu)

    menu.hide()


@pytest.mark.gui
def test_model_menu_shows_the_download_size_of_missing_models(
    *, group: AiToolGroup
) -> None:
    group._assist._model_combo.set_available_models(
        available={"sam2:latest"}, downloading=set()
    )
    group._detect._model_combo.set_available_models(
        available={"sam3:latest"}, downloading=set()
    )

    texts = _menu_texts(group._model_button._build_menu())

    assert "SAM 2 Base+" in texts
    assert "SAM 2 Large\t868 MB" in texts
    assert "SAM 3\t3.4 GB" in texts
    assert "YOLO-World\tBoxes only · 642 MB" in texts
