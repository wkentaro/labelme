"""GUI tests for the provenance module using pytest-qt."""

from __future__ import annotations

from pathlib import Path

import imgviz
import numpy as np
import pytest
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


def _create_dummy_pixmap() -> imgviz.types.Image:
    """Create a dummy pixmap for testing."""
    return np.zeros((100, 100, 3), dtype=np.uint8)


def test_canvas_manual_finalise_records_create_event(qtbot: QtBot):
    """Test that manual drawing records a create event with Person agent."""
    canvas = Canvas()
    qtbot.addWidget(canvas)

    # Load a dummy pixmap
    pixmap = imgviz.asqimage(_create_dummy_pixmap())
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

    # Load a dummy pixmap
    pixmap = imgviz.asqimage(_create_dummy_pixmap())
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
    assert provenance["events"][0]["agent"]["label"] == "test-model:latest"


def test_edit_label_adds_edit_event_for_different_agent(qtbot: QtBot, monkeypatch):
    """Test that editing a label created by SoftwareAgent adds an edit event."""
    config_overrides = _make_config_overrides()

    # Create MainWindow with config overrides
    win = MainWindow(config_overrides=config_overrides)
    qtbot.addWidget(win)

    # Load a dummy pixmap
    from PyQt5 import QtGui

    pixmap = QtGui.QPixmap.fromImage(imgviz.asqimage(_create_dummy_pixmap()))
    win._canvas_widgets.canvas.loadPixmap(pixmap)

    # Create a shape with SoftwareAgent provenance
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
    win._canvas_widgets.canvas.shapes.append(ai_shape)
    win._canvas_widgets.canvas.storeShapes()

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

    # Create MainWindow with config overrides
    win = MainWindow(config_overrides=config_overrides)
    qtbot.addWidget(win)

    # Load a dummy pixmap
    from PyQt5 import QtGui

    pixmap = QtGui.QPixmap.fromImage(imgviz.asqimage(_create_dummy_pixmap()))
    win._canvas_widgets.canvas.loadPixmap(pixmap)

    # Create a shape with provenance
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
    win._canvas_widgets.canvas.shapes.append(original_shape)
    win._canvas_widgets.canvas.storeShapes()

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
    config_overrides = _make_config_overrides()

    # Create MainWindow with config overrides
    win = MainWindow(config_overrides=config_overrides)
    qtbot.addWidget(win)

    # Load a dummy pixmap
    from PyQt5 import QtGui

    pixmap = QtGui.QPixmap.fromImage(imgviz.asqimage(_create_dummy_pixmap()))
    win._canvas_widgets.canvas.loadPixmap(pixmap)

    # Set to polygon mode for text-to-annotation
    win._canvas_widgets.canvas.createMode = "polygon"

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
        win._automation.bbox_from_text, "get_shapes_from_bboxes", mock_get_shapes_from_bboxes
    )

    # Monkeypatch upstream model calls so no real model runs
    def mock_get_bboxes_from_texts(*args, **kwargs):
        return (
            np.array([[0, 0, 10, 10]], dtype=np.float32),
            np.array([1.0]),
            np.array([0]),
            np.array([0]),
        ), None

    monkeypatch.setattr(
        win._automation.bbox_from_text, "get_bboxes_from_texts", mock_get_bboxes_from_texts
    )

    # Monkeypatch NMS to pass through
    def mock_nms_bboxes(*args, **kwargs):
        boxes, scores, labels, indices = args[0], args[1], args[2], args[3]
        return boxes, scores, labels, indices

    monkeypatch.setattr(win._automation.bbox_from_text, "nms_bboxes", mock_nms_bboxes)

    # Monkeypatch model download to skip
    def mock_download_ai_model(*args, **kwargs):
        return True

    monkeypatch.setattr("labelme.app.download_ai_model", mock_download_ai_model)

    # Call _submit_ai_prompt
    win._submit_ai_prompt(None)

    # Check that the inserted shape has a create event by SoftwareAgent
    assert len(win._canvas_widgets.canvas.shapes) == 1
    shape = win._canvas_widgets.canvas.shapes[0]
    provenance = _get_provenance(shape)
    assert len(provenance["events"]) == 1
    assert provenance["events"][0]["action"] == "create"
    assert provenance["events"][0]["agent"]["type"] == "SoftwareAgent"
