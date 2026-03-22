"""GUI tests for provenance integration."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from contextlib import contextmanager

import numpy as np
import pytest
from PyQt5 import QtGui
from PyQt5 import QtWidgets
from PyQt5.QtCore import QPointF

from labelme.app import MainWindow
from labelme.provenance import default_interactive_agent
from labelme.provenance import ensure_provenance
from labelme.provenance import model_agent
from labelme.provenance import record_event
from labelme.shape import Shape
from labelme.widgets.canvas import Canvas


def _make_config_overrides(labels: list[str] | None = None) -> dict:
    return {
        "display_label_popup": False,
        "labels": labels if labels is not None else ["cat", "dog"],
        "auto_save": False,
        "with_image_data": False,
        "show_label_text_field": False,
        "sort_labels": True,
        "label_flags": {},
        "validate_label": None,
        "epsilon": 10.0,
        "canvas": {
            "double_click": "close",
            "num_backups": 10,
            "crosshair": {
                "polygon": False,
                "rectangle": True,
                "circle": False,
                "line": False,
                "point": False,
                "linestrip": False,
                "ai_polygon": False,
                "ai_mask": False,
            },
            "fill_drawing": True,
        },
        "ai": {"default": "sam2:latest"},
    }


def _create_dummy_qimage() -> QtGui.QImage:
    image = QtGui.QImage(100, 100, QtGui.QImage.Format_RGB32)
    image.fill(0)
    return image


def _make_triangle(*, label: str | None = None, shape_type: str = "polygon") -> Shape:
    shape = Shape(label=label, shape_type=shape_type)
    shape.addPoint(QPointF(0, 0))
    shape.addPoint(QPointF(10, 10))
    shape.addPoint(QPointF(20, 0))
    shape.close()
    return shape


def _get_provenance(shape: Shape) -> dict:
    return ensure_provenance(shape)


def _cleanup_widget(widget: QtWidgets.QWidget, qapp: QtWidgets.QApplication) -> None:
    try:
        widget.hide()
        widget.close()
    finally:
        widget.deleteLater()
        qapp.processEvents()
        QtWidgets.QApplication.processEvents()


@contextmanager
def _main_window(
    qapp: QtWidgets.QApplication,
    *,
    labels: list[str] | None = None,
) -> MainWindow:
    win = MainWindow(config_overrides=_make_config_overrides(labels=labels))
    # Avoid dirty-state save/discard dialogs during teardown in headless tests.
    win.setDirty = lambda: None  # type: ignore[method-assign]
    win.saveLabels = lambda *args, **kwargs: True  # type: ignore[method-assign]
    image = _create_dummy_qimage()
    pixmap = QtGui.QPixmap.fromImage(image)
    win._canvas_widgets.canvas.loadPixmap(pixmap)
    win._image_path = "/tmp/test.png"
    win._filename = "/tmp/test.png"
    win._image = image
    try:
        yield win
    finally:
        win._is_changed = False
        _cleanup_widget(win, qapp)


def test_canvas_manual_finalise_records_create_event(qapp: QtWidgets.QApplication):
    canvas = Canvas()
    image = _create_dummy_qimage()
    pixmap = QtGui.QPixmap.fromImage(image)
    canvas.loadPixmap(pixmap)

    try:
        canvas.createMode = "polygon"
        canvas.setEditing(False)
        canvas.current = _make_triangle(shape_type="polygon")
        canvas.finalise()

        assert len(canvas.shapes) == 1
        shape = canvas.shapes[0]
        provenance = _get_provenance(shape)
        assert len(provenance["events"]) == 1
        assert provenance["events"][0]["action"] == "create"
        assert provenance["events"][0]["agent"]["type"] == "Person"
        assert provenance["events"][0]["agent"]["label"] == "interactive-user"
    finally:
        _cleanup_widget(canvas, qapp)


def test_canvas_ai_finalise_records_software_agent_create(
    qapp: QtWidgets.QApplication,
    monkeypatch: pytest.MonkeyPatch,
):
    canvas = Canvas()
    image = _create_dummy_qimage()
    pixmap = QtGui.QPixmap.fromImage(image)
    canvas.loadPixmap(pixmap)

    def mock_update_shape_with_ai(points, point_labels, shape):
        shape.setShapeRefined(
            shape_type="polygon",
            points=[QPointF(0, 0), QPointF(10, 10), QPointF(20, 0)],
            point_labels=[1, 1, 1],
        )

    monkeypatch.setattr(canvas, "_update_shape_with_ai", mock_update_shape_with_ai)

    try:
        canvas.createMode = "ai_polygon"
        canvas.setEditing(False)
        canvas.set_ai_model_name("test-model:latest")
        canvas.current = Shape(shape_type="points")
        canvas.current.addPoint(QPointF(5, 5), label=1)
        canvas.current.addPoint(QPointF(15, 15), label=1)
        canvas.current.addPoint(QPointF(25, 5), label=1)
        canvas.finalise()

        assert len(canvas.shapes) == 1
        shape = canvas.shapes[0]
        provenance = _get_provenance(shape)
        assert len(provenance["events"]) == 1
        assert provenance["events"][0]["action"] == "create"
        assert provenance["events"][0]["agent"]["type"] == "SoftwareAgent"
        assert provenance["events"][0]["agent"]["label"] == "test-model:latest"
    finally:
        _cleanup_widget(canvas, qapp)


def test_mainwindow_newshape_collapses_label_edit_into_create(
    qapp: QtWidgets.QApplication,
    monkeypatch: pytest.MonkeyPatch,
):
    with _main_window(qapp, labels=["cat"]) as win:
        monkeypatch.setattr(win, "setDirty", lambda: None)
        monkeypatch.setattr(
            win._label_dialog,
            "popUp",
            lambda *args, **kwargs: pytest.fail("unexpected label dialog"),
        )

        item = win._docks.unique_label_list.find_label_item("cat")
        assert item is not None
        win._docks.unique_label_list.setCurrentItem(item)
        item.setSelected(True)

        session_id = win._canvas_widgets.canvas.get_session_id()
        shape = _make_triangle(shape_type="polygon")
        record_event(
            shape,
            action="create",
            agent=default_interactive_agent(),
            session_id=session_id,
            properties={"kinds": ["manual_draw"]},
        )

        def mock_set_last_label(text, flags):
            shape.label = text
            shape.flags = flags
            return shape

        monkeypatch.setattr(win._canvas_widgets.canvas, "setLastLabel", mock_set_last_label)
        win.newShape()

        provenance = _get_provenance(shape)
        assert len(provenance["events"]) == 1
        assert provenance["events"][0]["action"] == "create"
        kinds = provenance["events"][0]["properties"]["kinds"]
        assert "manual_draw" in kinds
        assert "label_edit" in kinds


def test_edit_label_adds_edit_event_for_different_agent(
    qapp: QtWidgets.QApplication,
    monkeypatch: pytest.MonkeyPatch,
):
    with _main_window(qapp) as win:
        monkeypatch.setattr(win, "setDirty", lambda: None)

        session_id = win._canvas_widgets.canvas.get_session_id()
        ai_shape = _make_triangle(label="cat", shape_type="polygon")
        record_event(
            ai_shape,
            action="create",
            agent=model_agent("sam2:latest"),
            session_id=session_id,
            properties={"kinds": ["ai_generate", "ai_polygon"]},
        )
        win._load_shapes([ai_shape], replace=True)

        item = win._docks.label_list.findItemByShape(ai_shape)
        win._docks.label_list.selectItem(item)
        qapp.processEvents()

        monkeypatch.setattr(win._label_dialog, "popUp", lambda *args, **kwargs: ("dog", {}, None, ""))

        win._edit_label()

        provenance = _get_provenance(ai_shape)
        assert [event["action"] for event in provenance["events"]] == ["create", "edit"]
        assert ai_shape.label == "dog"


def test_paste_selected_shape_creates_derive_event(qapp: QtWidgets.QApplication):
    with _main_window(qapp, labels=["cat"]) as win:
        original_shape = _make_triangle(label="cat", shape_type="polygon")
        session_id = win._canvas_widgets.canvas.get_session_id()
        record_event(
            original_shape,
            action="create",
            agent=default_interactive_agent(),
            session_id=session_id,
            properties={"kinds": ["manual_draw"]},
        )
        original_annotation_id = _get_provenance(original_shape)["annotation_id"]

        win._load_shapes([original_shape], replace=True)
        win._canvas_widgets.canvas.selectShapes([original_shape])
        win.copySelectedShape()
        win.pasteSelectedShape()

        assert len(win._canvas_widgets.canvas.shapes) == 2
        pasted_shape = win._canvas_widgets.canvas.shapes[1]
        pasted_provenance = _get_provenance(pasted_shape)
        assert pasted_provenance["annotation_id"] != original_annotation_id
        assert pasted_provenance["events"][0]["action"] == "create"
        assert pasted_provenance["events"][-1]["action"] == "derive"
        assert (
            pasted_provenance["events"][-1]["properties"]["source_annotation_id"]
            == original_annotation_id
        )


def test_submit_ai_prompt_records_create_events(
    qapp: QtWidgets.QApplication,
    monkeypatch: pytest.MonkeyPatch,
):
    import osam.apis

    with _main_window(qapp) as win:
        monkeypatch.setattr(win, "setDirty", lambda: None)
        win._canvas_widgets.canvas.createMode = "polygon"

        monkeypatch.setattr("labelme.app.download_ai_model", lambda *args, **kwargs: True)

        class FakeModelType:
            @staticmethod
            def get_size():
                return 1

        monkeypatch.setattr(osam.apis, "get_model_type_by_name", lambda *args, **kwargs: FakeModelType)

        class FakeOsamSession:
            def __init__(self, *args, **kwargs):
                self.model_name = "yoloworld:latest"

        monkeypatch.setattr("labelme.app.OsamSession", FakeOsamSession)

        monkeypatch.setattr(
            "labelme.app.bbox_from_text.get_bboxes_from_texts",
            lambda *args, **kwargs: (
                np.array([[0, 0, 10, 10]], dtype=np.float32),
                np.array([1.0], dtype=np.float32),
                np.array([0], dtype=np.int32),
                None,
            ),
        )
        monkeypatch.setattr(
            "labelme.app.bbox_from_text.nms_bboxes",
            lambda *args, **kwargs: (
                kwargs.get("boxes", args[0] if args else np.array([[0, 0, 10, 10]], dtype=np.float32)),
                kwargs.get("scores", args[1] if len(args) > 1 else np.array([1.0], dtype=np.float32)),
                kwargs.get("labels", args[2] if len(args) > 2 else np.array([0], dtype=np.int32)),
                np.array([0], dtype=np.int32),
            ),
        )

        def mock_get_shapes_from_bboxes(*args, **kwargs):
            return [_make_triangle(label="cat", shape_type="polygon")]

        monkeypatch.setattr(
            "labelme.app.bbox_from_text.get_shapes_from_bboxes",
            mock_get_shapes_from_bboxes,
        )
        monkeypatch.setattr(win._ai_text, "get_text_prompt", lambda: "cat")
        monkeypatch.setattr(win._ai_text, "get_model_name", lambda: "yoloworld:latest")
        monkeypatch.setattr(win._ai_text, "get_iou_threshold", lambda: 0.5)
        monkeypatch.setattr(win._ai_text, "get_score_threshold", lambda: 0.5)

        win._submit_ai_prompt(None)

        assert len(win._canvas_widgets.canvas.shapes) == 1
        shape = win._canvas_widgets.canvas.shapes[0]
        provenance = _get_provenance(shape)
        assert len(provenance["events"]) == 1
        assert provenance["events"][0]["action"] == "create"
        assert provenance["events"][0]["agent"]["type"] == "SoftwareAgent"
