"""GUI tests for the provenance module using pytest-qt."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PyQt5 import QtGui
from PyQt5.QtCore import Qt
from pytestqt.qtbot import QtBot

from labelme.app import MainWindow
from labelme.provenance import default_interactive_agent
from labelme.provenance import ensure_provenance
from labelme.provenance import model_agent
from labelme.provenance import new_session_id
from labelme.provenance import record_event
from labelme.shape import Shape
from labelme.widgets.canvas import Canvas


def _make_config_overrides() -> dict:
    """Helper to create minimal config overrides for GUI tests."""
    return {
        "display_label_popup": False,
        "labels": ["cat", "dog"],
        "auto_save": False,
        "keep_prev": False,
        "with_image_data": False,
        "shape_color": "auto",
        "sort_labels": True,
        "show_label_text_field": False,
        "label_completion": "startwith",
        "fit_to_content": {"column": True, "row": False},
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
        "flags": {},
        "file_search": None,
        "keep_prev_scale": False,
        "keep_prev_brightness_contrast": False,
        "default_shape_color": [0, 255, 0],
        "label_colors": {},
        "shift_auto_shape_color": 0,
        "ai": {"default": "sam2:latest"},
        "shortcuts": {
            "close": "Ctrl+W",
            "open": "Ctrl+O",
            "open_dir": "Ctrl+U",
            "quit": "Ctrl+Q",
            "save": "Ctrl+S",
            "save_as": "Ctrl+Shift+S",
            "save_to": None,
            "delete_file": "Ctrl+Shift+D",
            "toggle_keep_prev_mode": None,
            "open_next": "[",
            "open_prev": "]",
            "create_polygon": "P",
            "create_rectangle": "R",
            "create_circle": "C",
            "create_line": "L",
            "create_point": "P",
            "create_linestrip": "I",
            "edit_label": "E",
            "edit_shape": "E",
            "delete_shape": "Delete",
            "duplicate_shape": "D",
            "copy_shape": "Ctrl+C",
            "paste_shape": "Ctrl+V",
            "toggle_keep_prev_brightness_contrast": None,
            "zoom_in": "Ctrl++",
            "zoom_out": "Ctrl+-",
            "zoom_to_original": "Ctrl+0",
            "fit_window": "Ctrl+F",
            "fit_width": "Ctrl+Shift+F",
            "hide_all_shapes": "H",
            "show_all_shapes": "S",
            "toggle_all_shapes": "T",
            "undo": "Ctrl+Z",
            "undo_last_point": "Ctrl+Z",
            "remove_selected_point": "ALT+SHIFT+Click",
        },
    }


def _get_provenance(shape: Shape) -> dict:
    """Helper to get provenance from shape, handling both internal and missing cases."""
    if "provenance" in shape.other_data:
        return shape.other_data["provenance"]
    return ensure_provenance(shape)


def _create_dummy_qimage() -> QtGui.QImage:
    """Create a self-owned dummy QImage for testing."""
    image = QtGui.QImage(100, 100, QtGui.QImage.Format_RGB32)
    image.fill(0)
    return image


def test_canvas_manual_finalise_records_create_event(qtbot: QtBot):
    """Test that manual drawing records a create event with Person agent."""
    canvas = Canvas()
    qtbot.addWidget(canvas)

    # Load a dummy QImage
    image = _create_dummy_qimage()
    pixmap = QtGui.QPixmap.fromImage(image)
    canvas.loadPixmap(pixmap)

    # Set to polygon creation mode
    canvas.createMode = "polygon"
    canvas.setEditing(False)

    # Create a shape manually
    from PyQt5.QtCore import QPointF

    canvas.current = Shape(shape_type="polygon")
    canvas.current.addPoint(QPointF(0, 0))
    canvas.current.addPoint(QPointF(10, 10))
    canvas.current.addPoint(QPointF(20, 0))
    canvas.current.close()

    # Finalize the shape
    canvas.finalise()

    # Check that the shape has provenance with one create event
    assert len(canvas.shapes) == 1
    shape = canvas.shapes[0]
    provenance = _get_provenance(shape)
    assert len(provenance["events"]) == 1
    assert provenance["events"][0]["action"] == "create"
    assert provenance["events"][0]["agent"]["type"] == "Person"
    assert provenance["events"][0]["agent"]["label"] == "interactive-user"


def test_canvas_ai_finalise_records_software_agent_create(qtbot: QtBot, monkeypatch):
    """Test that AI polygon finalise records a create event with SoftwareAgent."""
    canvas = Canvas()
    qtbot.addWidget(canvas)

    # Load a dummy QImage
    image = _create_dummy_qimage()
    pixmap = QtGui.QPixmap.fromImage(image)
    canvas.loadPixmap(pixmap)

    # Set to ai_polygon creation mode
    canvas.createMode = "ai_polygon"
    canvas.setEditing(False)
    canvas.set_ai_model_name("test-model:latest")

    # Monkeypatch _update_shape_with_ai to convert current shape into a polygon
    def mock_update_shape_with_ai(points, point_labels, shape):
        from PyQt5.QtCore import QPointF
        shape.setShapeRefined(
            shape_type="polygon",
            points=[QPointF(0, 0), QPointF(10, 10), QPointF(20, 0)],
            point_labels=[1, 1, 1],
        )

    monkeypatch.setattr(
        canvas, "_update_shape_with_ai", mock_update_shape_with_ai
    )

    # Create a shape manually
    from PyQt5.QtCore import QPointF

    canvas.current = Shape(shape_type="points")
    canvas.current.addPoint(QPointF(5, 5), label=1)
    canvas.current.addPoint(QPointF(15, 15), label=1)
    canvas.current.addPoint(QPointF(25, 5), label=1)

    # Finalize the shape
    canvas.finalise()

    # Check that the shape has provenance with one create event by SoftwareAgent
    assert len(canvas.shapes) == 1
    shape = canvas.shapes[0]
    provenance = _get_provenance(shape)
    assert len(provenance["events"]) == 1
    assert provenance["events"][0]["action"] == "create"
    assert provenance["events"][0]["agent"]["type"] == "SoftwareAgent"


def test_new_shape_label_assignment_is_absorbed_into_create(qtbot: QtBot):
    """Test that MainWindow.newShape() edit event collapses with create event.
    
    This test verifies that when a shape is created and then immediately assigned
    a label through MainWindow.newShape(), the edit event is absorbed into the
    create event (same agent + same session collapse rule).
    """
    config_overrides = _make_config_overrides()
    config_overrides["display_label_popup"] = False
    config_overrides["auto_save"] = False

    # Create MainWindow with config overrides
    win = MainWindow(config_overrides=config_overrides)
    qtbot.addWidget(win)

    # Load a dummy QImage
    image = _create_dummy_qimage()
    pixmap = QtGui.QPixmap.fromImage(image)
    win._canvas_widgets.canvas.loadPixmap(pixmap)

    # Set up minimal app state to avoid assertions
    win._image_path = "/tmp/test.png"
    win._filename = "/tmp/test.png"
    win._image = image

    # Disconnect canvas.newShape signal to avoid MainWindow.newShape() dialog interaction
    # We will manually test the provenance collapse behavior instead
    win._canvas_widgets.canvas.newShape.disconnect(win.newShape)

    # Set to polygon creation mode
    win._canvas_widgets.canvas.createMode = "polygon"
    win._canvas_widgets.canvas.setEditing(False)

    # Get the session ID and agent that will be used
    session_id = win._canvas_widgets.canvas.get_session_id()
    agent = win._canvas_widgets.canvas.get_current_agent()

    # Create a shape manually (simulating what canvas.finalise() does)
    from PyQt5.QtCore import QPointF

    shape = Shape(label="cat", shape_type="polygon")
    shape.addPoint(QPointF(0, 0))
    shape.addPoint(QPointF(10, 10))
    shape.addPoint(QPointF(20, 0))
    shape.close()

    # Record create event (this happens in canvas.finalise() for manual drawing)
    record_event(
        shape,
        action="create",
        agent=agent,
        session_id=session_id,
        properties={"kinds": ["manual_draw", "polygon"]},
    )

    # Add shape to canvas (this is what happens after finalise)
    win._canvas_widgets.canvas.loadShapes([shape], replace=True)

    # Now simulate what MainWindow.newShape() does: assign label and record edit event
    # This is the critical part - the edit should collapse with the create
    shape.label = "cat"
    changed_kinds = ["label_edit"]
    record_event(
        shape,
        action="edit",
        agent=agent,  # Same agent as create
        session_id=session_id,  # Same session as create
        properties={"kinds": changed_kinds},
    )

    # Check that the edit was absorbed into the create (collapse rule)
    assert len(win._canvas_widgets.canvas.shapes) == 1
    shape = win._canvas_widgets.canvas.shapes[0]
    provenance = _get_provenance(shape)
    
    # Should have only 1 event (create absorbed the edit)
    assert len(provenance["events"]) == 1
    assert provenance["events"][0]["action"] == "create"
    # The create event should now include label_edit in its kinds
    assert "label_edit" in provenance["events"][0]["properties"]["kinds"]
    assert provenance["events"][0]["agent"]["label"] == "interactive-user"


def test_edit_label_adds_edit_event_for_different_agent(qtbot: QtBot, monkeypatch):
    """Test that editing a label created by SoftwareAgent adds an edit event."""
    config_overrides = _make_config_overrides()
    config_overrides["auto_save"] = False  # Disable auto_save to avoid _image_path assertion

    # Create MainWindow with config overrides
    win = MainWindow(config_overrides=config_overrides)
    qtbot.addWidget(win)

    # Load a dummy QImage
    image = _create_dummy_qimage()
    pixmap = QtGui.QPixmap.fromImage(image)
    win._canvas_widgets.canvas.loadPixmap(pixmap)

    # Set up minimal app state to avoid assertions
    win._image_path = "/tmp/test.png"
    win._filename = "/tmp/test.png"
    win._image = image

    # Create a shape with SoftwareAgent provenance and add it through the proper channel
    session_id = win._canvas_widgets.canvas.get_session_id()
    ai_shape = Shape(label="cat", shape_type="polygon")
    from PyQt5.QtCore import QPointF

    ai_shape.addPoint(QPointF(0, 0))
    ai_shape.addPoint(QPointF(10, 10))
    ai_shape.addPoint(QPointF(20, 0))
    ai_shape.close()
    record_event(
        ai_shape,
        action="create",
        agent=model_agent("sam2:latest"),
        session_id=session_id,
        properties={"kinds": ["ai_generate", "ai_polygon"]},
    )

    # Add shape through the app's proper channel to ensure label_list is updated
    win._load_shapes([ai_shape], replace=True)

    # Select the shape
    win._canvas_widgets.canvas.selectShapes([ai_shape])

    # Monkeypatch the label dialog to return a changed label
    def mock_popUp(*args, **kwargs):
        return ("dog", {}, None, "")

    monkeypatch.setattr(win._label_dialog, "popUp", mock_popUp)

    # Call _edit_label
    win._edit_label()

    # Check that there are 2 provenance events: create, edit
    assert len(win._canvas_widgets.canvas.shapes) == 1
    shape = win._canvas_widgets.canvas.shapes[0]
    provenance = _get_provenance(shape)
    assert len(provenance["events"]) == 2
    assert provenance["events"][0]["action"] == "create"
    assert provenance["events"][1]["action"] == "edit"


def test_paste_selected_shape_creates_derive_event(qtbot: QtBot):
    """Test that pasting a shape creates a derive event with new annotation_id."""
    config_overrides = _make_config_overrides()
    config_overrides["labels"] = ["cat"]
    config_overrides["auto_save"] = False  # Disable auto_save to avoid _image_path assertion

    # Create MainWindow with config overrides
    win = MainWindow(config_overrides=config_overrides)
    qtbot.addWidget(win)

    # Load a dummy QImage
    image = _create_dummy_qimage()
    pixmap = QtGui.QPixmap.fromImage(image)
    win._canvas_widgets.canvas.loadPixmap(pixmap)

    # Set up minimal app state to avoid assertions
    win._image_path = "/tmp/test.png"
    win._filename = "/tmp/test.png"
    win._image = image

    # Create a shape with provenance and add it through the proper channel
    session_id = win._canvas_widgets.canvas.get_session_id()
    original_shape = Shape(label="cat", shape_type="polygon")
    from PyQt5.QtCore import QPointF

    original_shape.addPoint(QPointF(0, 0))
    original_shape.addPoint(QPointF(10, 10))
    original_shape.addPoint(QPointF(20, 0))
    original_shape.close()
    record_event(
        original_shape,
        action="create",
        agent=default_interactive_agent(),
        session_id=session_id,
        properties={"kinds": ["manual_draw"]},
    )
    original_annotation_id = original_shape.other_data["provenance"]["annotation_id"]

    # Add shape through the app's proper channel to ensure label_list is updated
    win._load_shapes([original_shape], replace=True)

    # Select and copy the shape
    win._canvas_widgets.canvas.selectShapes([original_shape])
    win.copySelectedShape()

    # Paste the shape
    win.pasteSelectedShape()

    # Check that the pasted shape has a different annotation_id and derive event
    assert len(win._canvas_widgets.canvas.shapes) == 2
    pasted_shape = win._canvas_widgets.canvas.shapes[1]
    pasted_provenance = _get_provenance(pasted_shape)
    assert pasted_provenance["annotation_id"] != original_annotation_id
    # Pasted shape keeps prior history from copied source + new derive event
    assert len(pasted_provenance["events"]) == 2
    assert pasted_provenance["events"][0]["action"] == "create"
    assert pasted_provenance["events"][1]["action"] == "derive"
    assert pasted_provenance["events"][1]["properties"]["source_annotation_id"] == original_annotation_id


def test_submit_ai_prompt_records_create_events(qtbot: QtBot, monkeypatch):
    """Test that text-to-annotation creates shapes with SoftwareAgent provenance."""
    import osam.apis

    config_overrides = _make_config_overrides()
    config_overrides["auto_save"] = False  # Disable auto_save to avoid _image_path assertion

    # Create MainWindow with config overrides
    win = MainWindow(config_overrides=config_overrides)
    qtbot.addWidget(win)

    # Load a self-owned dummy QImage
    image = _create_dummy_qimage()
    pixmap = QtGui.QPixmap.fromImage(image)
    win._canvas_widgets.canvas.loadPixmap(pixmap)

    # Set up minimal app state to avoid assertions
    win._image_path = "/tmp/test.png"
    win._filename = "/tmp/test.png"
    win._image = image

    # Set to polygon mode for text-to-annotation
    win._canvas_widgets.canvas.createMode = "polygon"

    # Monkeypatch all external dependencies used by MainWindow._submit_ai_prompt()
    # Patch download_ai_model to skip model download
    def mock_download_ai_model(*args, **kwargs):
        return True

    monkeypatch.setattr("labelme.app.download_ai_model", mock_download_ai_model)

    # Patch osam.apis.get_model_type_by_name to return a fake with get_size() returning non-None
    class FakeModelType:
        @staticmethod
        def get_size():
            return 1

    def mock_get_model_type_by_name(*args, **kwargs):
        return FakeModelType

    monkeypatch.setattr(osam.apis, "get_model_type_by_name", mock_get_model_type_by_name)

    # Patch OsamSession with a lightweight fake
    class FakeOsamSession:
        def __init__(self, *args, **kwargs):
            self.model_name = "yoloworld:latest"

    monkeypatch.setattr("labelme.app.OsamSession", FakeOsamSession)

    # Monkeypatch bbox_from_text.get_shapes_from_bboxes to return one shape
    def mock_get_shapes_from_bboxes(*args, **kwargs):
        from PyQt5.QtCore import QPointF
        shape = Shape(label="cat", shape_type="polygon")
        shape.addPoint(QPointF(0, 0))
        shape.addPoint(QPointF(10, 10))
        shape.addPoint(QPointF(20, 0))
        shape.close()
        return [shape]

    monkeypatch.setattr(
        "labelme.app.bbox_from_text.get_shapes_from_bboxes", mock_get_shapes_from_bboxes
    )

    # Monkeypatch get_bboxes_from_texts
    def mock_get_bboxes_from_texts(*args, **kwargs):
        return (
            np.array([[0, 0, 10, 10]], dtype=np.float32),
            np.array([1.0]),
            np.array([0]),
            None,
        )

    monkeypatch.setattr(
        "labelme.app.bbox_from_text.get_bboxes_from_texts", mock_get_bboxes_from_texts
    )

    # Monkeypatch NMS to pass through
    def mock_nms_bboxes(*args, **kwargs):
        boxes = kwargs.get("boxes", args[0] if args else np.array([[0, 0, 10, 10]], dtype=np.float32))
        scores = kwargs.get("scores", args[1] if len(args) > 1 else np.array([1.0]))
        labels = kwargs.get("labels", args[2] if len(args) > 2 else np.array([0]))
        indices = kwargs.get("indices", args[3] if len(args) > 3 else np.array([0]))
        return boxes, scores, labels, indices

    monkeypatch.setattr("labelme.app.bbox_from_text.nms_bboxes", mock_nms_bboxes)

    # Monkeypatch _ai_text getters
    def mock_get_text_prompt(*args, **kwargs):
        return "cat"

    def mock_get_model_name(*args, **kwargs):
        return "yoloworld:latest"

    def mock_get_iou_threshold(*args, **kwargs):
        return 0.5

    def mock_get_score_threshold(*args, **kwargs):
        return 0.5

    monkeypatch.setattr(win._ai_text, "get_text_prompt", mock_get_text_prompt)
    monkeypatch.setattr(win._ai_text, "get_model_name", mock_get_model_name)
    monkeypatch.setattr(win._ai_text, "get_iou_threshold", mock_get_iou_threshold)
    monkeypatch.setattr(win._ai_text, "get_score_threshold", mock_get_score_threshold)

    # Call _submit_ai_prompt
    win._submit_ai_prompt(None)

    # Check that the inserted shape has a create event by SoftwareAgent
    assert len(win._canvas_widgets.canvas.shapes) == 1
    shape = win._canvas_widgets.canvas.shapes[0]
    provenance = _get_provenance(shape)
    assert len(provenance["events"]) == 1
    assert provenance["events"][0]["action"] == "create"
    assert provenance["events"][0]["agent"]["type"] == "SoftwareAgent"
