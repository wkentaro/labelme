from __future__ import annotations

import collections
import dataclasses
import enum
import typing
from collections.abc import Callable
from collections.abc import Sequence
from typing import Any
from typing import Final
from typing import Literal
from typing import cast

import numpy as np
from loguru import logger
from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets
from PySide6.QtCore import QPoint
from PySide6.QtCore import QPointF
from PySide6.QtCore import QRectF
from PySide6.QtCore import Qt

from .. import _automation
from .. import _shape
from .. import _utils
from .._shape import POLYLINE_SHAPE_TYPES
from .._shape import Shape
from .._shape import ShapeType
from . import _canvas_interaction
from ._canvas_interaction import CursorRole
from ._canvas_interaction import HitKind
from ._shape_render import Palette
from ._shape_render import ShapeRenderContext
from ._shape_render import VertexHighlight
from ._shape_render import bounds as _shape_bounds
from ._shape_render import is_hit_by_point
from ._shape_render import render_shape
from .download import download_ai_model

_DEFAULT_SHAPE_RGB: Final[tuple[int, int, int]] = (0, 255, 0)
_DEFAULT_PALETTE: Final[Palette] = Palette.from_rgb(rgb=_DEFAULT_SHAPE_RGB)


@dataclasses.dataclass(frozen=True)
class _DraftShape:
    """In-progress shape held in QPointF while drawing, before it is committed
    to a Qt-free numpy `Shape` at finalize time. Immutable so each edit returns a
    new draft and the canvas reassigns ``self._line`` / ``self._current`` as a
    whole: state changes happen at assignment boundaries that are easy to follow,
    rather than in-place mutation threaded through the drawing methods."""

    shape_type: ShapeType = "polygon"
    points: tuple[QPointF, ...] = ()
    point_labels: tuple[int, ...] = ()
    closed: bool = False

    def close(self) -> _DraftShape:
        return dataclasses.replace(self, closed=True)

    def open(self) -> _DraftShape:
        return dataclasses.replace(self, closed=False)

    def add_point(
        self, point: QPointF, label: int = 1, *, autoclose: bool = False
    ) -> _DraftShape:
        if autoclose and self.points and self.points[0] == point:
            return dataclasses.replace(self, closed=True)
        return dataclasses.replace(
            self,
            points=self.points + (point,),
            point_labels=self.point_labels + (label,),
        )

    def pop_point(self) -> _DraftShape:
        if not self.points:
            return self
        return dataclasses.replace(
            self, points=self.points[:-1], point_labels=self.point_labels[:-1]
        )


def _draft_to_shape(draft: _DraftShape) -> Shape:
    return Shape(
        shape_type=draft.shape_type,
        points=np.array([[p.x(), p.y()] for p in draft.points], dtype=np.float64),
        point_labels=np.array(draft.point_labels, dtype=np.int_),
        closed=draft.closed,
    )


def _shape_to_draft(shape: Shape) -> _DraftShape:
    return _DraftShape(
        shape_type=shape.shape_type,
        points=tuple(QPointF(*point) for point in shape.points),
        point_labels=tuple(int(label) for label in shape.point_labels),
        closed=shape.closed,
    )


MOVE_SPEED: float = 5.0

_CreateMode = Literal[
    "polygon",
    "rectangle",
    "oriented_rectangle",
    "circle",
    "line",
    "point",
    "linestrip",
    "ai_points_to_shape",
    "ai_box_to_shape",
]

_AI_CREATE_MODES: Final[tuple[_CreateMode, ...]] = (
    "ai_points_to_shape",
    "ai_box_to_shape",
)


_CREATE_MODE_TO_SHAPE_TYPE: Final[dict[_CreateMode, ShapeType]] = {
    "polygon": "polygon",
    "rectangle": "rectangle",
    "oriented_rectangle": "oriented_rectangle",
    "circle": "circle",
    "line": "line",
    "point": "point",
    "linestrip": "linestrip",
    "ai_points_to_shape": "points",
    "ai_box_to_shape": "rectangle",
}


# Modes whose seed point cannot be reinterpreted as the start of another mode.
# `point` finalizes on click so never has a partial shape; AI modes carry
# per-point positive/negative labels. Every other mode in _CreateMode shares a
# 1-click anchor and is seed-compatible by default — new modes participate
# unless explicitly listed here.
_SEED_INCOMPATIBLE_CREATE_MODES: Final[tuple[_CreateMode, ...]] = (
    "point",
    "ai_points_to_shape",
    "ai_box_to_shape",
)


class _CanvasMode(enum.Enum):
    CREATE = enum.auto()
    EDIT = enum.auto()


class Canvas(QtWidgets.QWidget):
    pixmap: QtGui.QPixmap
    _pixmap_hash: int | None
    _cursor: CursorRole
    shapes: list[Shape]
    shape_backups: collections.deque[list[Shape]]
    _is_moving_shape: bool
    selected_shapes: list[Shape]
    _selected_shapes_copy: list[Shape]
    _current: _DraftShape | None
    hovered_shape: Shape | None
    _last_hovered_shape: Shape | None
    _hovered_vertex: int | None
    _last_hovered_vertex: int | None
    _hovered_edge: int | None
    _last_hovered_edge: int | None
    _hovered_rotation: int | None

    zoom_request = QtCore.Signal(int, QPointF)
    scroll_request = QtCore.Signal(int, Qt.Orientation)
    pan_request = QtCore.Signal(QPoint)
    new_shape = QtCore.Signal()
    inference_produced_no_shapes = QtCore.Signal()
    inference_failed = QtCore.Signal(str)
    degenerate_shape_rejected = QtCore.Signal()
    selection_changed = QtCore.Signal(list)
    shape_moved = QtCore.Signal()
    drawing_polygon = QtCore.Signal(bool)
    vertex_selected = QtCore.Signal(bool)
    edge_selected = QtCore.Signal(bool)
    mouse_moved = QtCore.Signal(QPointF)
    status_updated = QtCore.Signal(str)

    mode: _CanvasMode = _CanvasMode.EDIT

    _create_mode: _CreateMode = "polygon"

    _fill_drawing = False

    _show_labels = False

    _prev_point: QPointF
    _prev_move_point: QPointF
    _drag_anchor: tuple[QPointF, QRectF]
    _rotation_center: np.ndarray
    _rotation_initial_angle: float
    _rotation_original_points: np.ndarray

    _pan_anchor: QPointF | None

    _highlight: VertexHighlight | None
    _rotation_highlight: VertexHighlight | None
    _color_resolver: Callable[[str], tuple[int, int, int]] | None
    _point_size: int
    _point_type: Literal["square", "round"]
    _draft_palette: Palette
    _palette_cache: dict[str, Palette]

    _ai_assist_session: _automation.AiAssistSession

    def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        self._epsilon: float = kwargs.pop("epsilon", 10.0)
        self._double_click = kwargs.pop("double_click", "close")
        if self._double_click not in [None, "close"]:
            raise ValueError(
                f"Unexpected value for double_click event: {self._double_click}"
            )
        self._num_backups: int = kwargs.pop("num_backups", 10)
        self._allow_out_of_bounds_points: bool = kwargs.pop(
            "allow_out_of_bounds_points", False
        )
        self._crosshair = kwargs.pop(
            "crosshair",
            {
                "polygon": False,
                "rectangle": True,
                "oriented_rectangle": False,
                "circle": False,
                "line": False,
                "point": False,
                "linestrip": False,
                "ai_points_to_shape": False,
                "ai_box_to_shape": True,
            },
        )
        super().__init__(*args, **kwargs)

        self._cursor = CursorRole.DEFAULT
        self.reset_state()

        # self._line represents:
        #   - create_mode == 'polygon': edge from last point to current
        #   - create_mode == 'rectangle': diagonal line of the rectangle
        #   - create_mode == 'line': the line
        #   - create_mode == 'point': the point
        self._line = _DraftShape()
        self._prev_point = QPointF()
        self._prev_move_point = QPointF()
        self._drag_anchor = (QPointF(), QRectF())
        self._rotation_center = np.zeros(2)
        self._rotation_initial_angle = 0.0
        self._rotation_original_points = np.empty((0, 2))
        self.scale: float = 1.0
        self._ai_assist_session = _automation.AiAssistSession()
        self._ai_inference_failed = False
        self._snapping = True
        self._hovered_shape_is_selected: bool = False
        self._painter = QtGui.QPainter()
        self._pan_anchor = None
        self._color_resolver: Callable[[str], tuple[int, int, int]] | None = None
        self._point_size: int = 8
        self._point_type: Literal["square", "round"] = "round"
        self._draft_palette = _DEFAULT_PALETTE
        self._palette_cache = {}
        self.context_menus = _canvas_interaction.ContextMenuPair(
            without_selection=QtWidgets.QMenu(),
            with_selection=QtWidgets.QMenu(),
        )
        self.context_menu_origin: QtCore.QPoint | None = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.WheelFocus)

    def set_fill_drawing(self, value: bool) -> None:
        self._fill_drawing = value

    def set_show_labels(self, value: bool) -> None:
        self._show_labels = value

    def set_allow_out_of_bounds_points(self, value: bool) -> None:
        self._allow_out_of_bounds_points = value

    def set_color_resolver(
        self, resolver: Callable[[str], tuple[int, int, int]]
    ) -> None:
        self._color_resolver = resolver

    def set_point_size(self, point_size: int) -> None:
        self._point_size = point_size

    def _resolve_palette(self, label: str | None) -> Palette:
        if label is None or self._color_resolver is None:
            return _DEFAULT_PALETTE
        # Auto colors depend on the live label ordering, so the palette cannot
        # be cached on the shape. Memoize within a single paint pass instead:
        # many shapes share a few labels, so this collapses the per-shape
        # resolution into one lookup per distinct label per frame.
        palette = self._palette_cache.get(label)
        if palette is None:
            palette = Palette.from_rgb(rgb=self._color_resolver(label))
            self._palette_cache[label] = palette
        return palette

    def set_draft_palette(self, palette: Palette) -> None:
        self._draft_palette = palette

    def _highlight_vertex(self, index: int, mode: Literal["move", "near"]) -> None:
        self._highlight = VertexHighlight(index=index, mode=mode)
        self._rotation_highlight = None

    def _highlight_rotation_point(
        self, index: int, mode: Literal["move", "near"]
    ) -> None:
        self._rotation_highlight = VertexHighlight(index=index, mode=mode)
        self._highlight = None

    def _clear_highlight_state(self) -> None:
        self._highlight = None
        self._rotation_highlight = None

    def _render_context(self, shape: Shape, *, highlighted: bool) -> ShapeRenderContext:
        selected = shape in self.selected_shapes
        return ShapeRenderContext(
            scale=self.scale,
            palette=self._resolve_palette(shape.label),
            point_size=self._point_size,
            point_type=self._point_type,
            selected=selected,
            fill=selected or shape is self.hovered_shape,
            highlight=self._highlight if highlighted else None,
            rotation_highlight=self._rotation_highlight if highlighted else None,
            show_label=self._show_labels,
        )

    def _draft_render_context(
        self,
        *,
        selected: bool,
        fill: bool,
        highlight: VertexHighlight | None,
        rotation_highlight: VertexHighlight | None,
    ) -> ShapeRenderContext:
        return ShapeRenderContext(
            scale=self.scale,
            palette=self._draft_palette,
            point_size=self._point_size,
            point_type=self._point_type,
            selected=selected,
            fill=fill,
            highlight=highlight,
            rotation_highlight=rotation_highlight,
        )

    @property
    def is_drawing(self) -> bool:
        return self._current is not None

    @property
    def create_mode(self) -> _CreateMode:
        return self._create_mode

    @create_mode.setter
    def create_mode(self, value: str) -> None:
        if value not in typing.get_args(_CreateMode):
            raise ValueError(f"Unsupported create_mode: {value}")
        new_mode = cast(_CreateMode, value)
        if new_mode == self._create_mode:
            return
        old_mode = self._create_mode
        # Update the mode before reconciling so any signals fired from a cancel
        # observe the new mode rather than the one being left behind.
        self._create_mode = new_mode
        self._reconcile_partial_shape_on_mode_switch(
            old_mode=old_mode, new_mode=new_mode
        )

    def _reconcile_partial_shape_on_mode_switch(
        self, *, old_mode: _CreateMode, new_mode: _CreateMode
    ) -> None:
        if self._current is None:
            return
        if not (
            len(self._current.points) == 1
            and old_mode not in _SEED_INCOMPATIBLE_CREATE_MODES
            and new_mode not in _SEED_INCOMPATIBLE_CREATE_MODES
        ):
            self._cancel_current_shape()
            return
        # Shape type is identity, not state: construct fresh shapes rather than
        # mutating in place. The prior mode's _update_drawing_line left
        # _line.points as a valid [seed, cursor] pair — carry it forward so a
        # click before the next mouseMoveEvent extends at the real cursor.
        seed_point = self._current.points[0]
        seed_label = self._current.point_labels[0]
        self._current = _DraftShape(shape_type=new_mode).add_point(
            seed_point, label=seed_label
        )
        self._line = dataclasses.replace(self._line, shape_type=new_mode)
        self.update()

    def get_ai_model_name(self) -> str:
        return self._ai_assist_session.model_name

    def set_ai_model_name(self, model_name: str) -> None:
        self._ai_assist_session.model_name = model_name

    def set_ai_output_format(self, output_format: _automation.AiOutputFormat) -> None:
        self._ai_assist_session.output_format = output_format

    def _shapes_from_ai_points(
        self, points: Sequence[QPointF], point_labels: Sequence[int]
    ) -> list[Shape]:
        image: np.ndarray = _utils.img_qt_to_arr(img_qt=self.pixmap.toImage())
        return self._ai_assist_session.propose_shapes(
            image=image[:, :, :3],
            image_id=str(self._pixmap_hash),
            points=np.array([[p.x(), p.y()] for p in points]),
            point_labels=np.array(point_labels),
            existing_shapes=self.shapes,
        )

    def _report_inference_failure(self, error: Exception) -> None:
        self._ai_inference_failed = True
        logger.opt(exception=error).error("AI inference failed")
        self.inference_failed.emit(f"{type(error).__name__}: {error}")

    def backup_shapes(self) -> None:
        self.shape_backups.append([s.copy() for s in self.shapes])

    @property
    def can_restore_shape(self) -> bool:
        # The latest entry on the backup stack mirrors the current state, so
        # at least one prior entry must exist for an undo to be meaningful.
        return len(self.shape_backups) >= 2

    def restore_last_shape(self) -> None:
        # Undo coordinates with app.py::undo_shape_edit, app.py::load_shapes,
        # and Canvas::load_shapes; this method only adjusts the backup stack.
        if not self.can_restore_shape:
            return
        self.shape_backups.pop()  # discard current state

        # load_shapes (called downstream by the application) will re-push
        # this entry as the new current state.
        self.shapes = self.shape_backups.pop()
        self.selected_shapes.clear()
        self.update()

    def enterEvent(self, a0: QtCore.QEvent) -> None:
        self._apply_cursor(self._cursor)
        self._update_status()

    def leaveEvent(self, a0: QtCore.QEvent) -> None:
        if self._set_highlight(
            hovered_shape=None,
            hovered_edge=None,
            hovered_vertex=None,
            hovered_rotation=None,
        ):
            self.update()
        self._release_cursor()
        self._update_status()

    def focusOutEvent(self, a0: QtGui.QFocusEvent) -> None:
        self._release_cursor()
        self._update_status()

    def set_editing(self, value: bool = True) -> None:
        self.mode = _CanvasMode.EDIT if value else _CanvasMode.CREATE
        if self.mode == _CanvasMode.EDIT:
            # CREATE -> EDIT
            self.update()  # clear crosshair
        else:
            # EDIT -> CREATE
            need_update: bool = self._set_highlight(
                hovered_shape=None,
                hovered_edge=None,
                hovered_vertex=None,
                hovered_rotation=None,
            )
            need_update |= self.deselect_shape()
            if need_update:
                self.update()

    def _set_highlight(
        self,
        hovered_shape: Shape | None,
        hovered_edge: int | None,
        hovered_vertex: int | None,
        hovered_rotation: int | None,
    ) -> bool:
        previous_shape: Shape | None = self.hovered_shape
        need_update: bool = hovered_shape is not None
        if previous_shape is not None:
            self._clear_highlight_state()
            need_update = True
        # NOTE: Store last highlighted for adding/removing points.
        self._last_hovered_shape = (
            previous_shape if hovered_shape is None else hovered_shape
        )
        self._last_hovered_vertex = (
            self._hovered_vertex if hovered_vertex is None else hovered_vertex
        )
        self._last_hovered_edge = (
            self._hovered_edge if hovered_edge is None else hovered_edge
        )
        self.hovered_shape = hovered_shape
        self._hovered_vertex = hovered_vertex
        self._hovered_edge = hovered_edge
        self._hovered_rotation = hovered_rotation
        return need_update

    def _is_vertex_selected(self) -> bool:
        return self._hovered_vertex is not None

    def _is_edge_selected(self) -> bool:
        return self._hovered_edge is not None

    def _is_rotation_point_selected(self) -> bool:
        return self._hovered_rotation is not None

    def _update_status(self, extra_messages: list[str] | None = None) -> None:
        messages: list[str] = []
        if self.mode == _CanvasMode.CREATE:
            messages.append(self.tr("Creating %r") % self.create_mode)
            messages.append(self._get_create_mode_message())
            if self._current is not None:
                messages.append(self.tr("ESC to cancel"))
            if self._can_close_shape():
                messages.append(self.tr("Enter or Space to finalize"))
        else:
            assert self.mode == _CanvasMode.EDIT
            messages.append(self.tr("Editing shapes"))
        if extra_messages:
            messages.extend(extra_messages)
        self.status_updated.emit(" • ".join(messages))

    def _get_create_mode_message(self) -> str:
        assert self.mode == _CanvasMode.CREATE
        is_new: bool = self._current is None
        if self.create_mode == "ai_points_to_shape":
            return self.tr(
                "Click points to include or Shift+Click to exclude."
                " Ctrl+LeftClick ends creation."
            )
        if self.create_mode == "ai_box_to_shape":
            if is_new:
                return self.tr("Click first corner of bbox for AI segmentation")
            else:
                return self.tr("Click opposite corner to segment object")
        if self.create_mode == "line":
            if is_new:
                return self.tr("Click start point for line")
            else:
                return self.tr("Click end point for line")
        if self.create_mode == "linestrip":
            if is_new:
                return self.tr("Click start point for linestrip")
            else:
                return self.tr(
                    "Click next point or finish by Ctrl/Cmd+Click for linestrip"
                )
        if self.create_mode == "circle":
            if is_new:
                return self.tr("Click center point for circle")
            else:
                return self.tr("Click point on circumference for circle")
        if self.create_mode == "rectangle":
            if is_new:
                return self.tr("Click first corner for rectangle")
            else:
                return self.tr("Click opposite corner for rectangle (Shift for square)")
        if self.create_mode == "oriented_rectangle":
            if is_new:
                return self.tr("Click first corner for oriented rectangle")
            assert self._current is not None
            if len(self._current.points) == 1:
                return self.tr("Click second corner to set orientation")
            return self.tr("Click third corner to close oriented rectangle")
        return self.tr("Click to add point")

    def mouseMoveEvent(self, a0: QtGui.QMouseEvent) -> None:
        try:
            pos = self._transform_point_widget_to_image(a0.position())
        except AttributeError:
            return
        self.mouse_moved.emit(pos)
        self._prev_move_point = pos
        self._dispatch_pointer_move(pos=pos, event=a0)

    def _dispatch_pointer_move(self, pos: QPointF, event: QtGui.QMouseEvent) -> None:
        if self._pan_anchor is not None:
            self._advance_pan(event=event)
            return
        if self.mode == _CanvasMode.CREATE:
            self._track_drawing_cursor(pos=pos, event=event)
            return
        buttons = event.buttons()
        if buttons & Qt.MouseButton.RightButton:
            self._continue_right_button_drag(pos=pos)
            return
        if buttons & Qt.MouseButton.LeftButton:
            self._continue_left_button_drag(pos=pos, event=event)
            return
        self._refresh_hover_state(pos=pos)

    def _advance_pan(self, event: QtGui.QMouseEvent) -> None:
        assert self._pan_anchor is not None
        # Use screen coordinates so the anchor does not drift when our own
        # pan emit shifts the canvas widget under the scroll area — a
        # widget-local frame would oscillate and cause juggling.
        cursor: QPointF = QPointF(self.mapToGlobal(event.position().toPoint()))
        step: QPointF = cursor - self._pan_anchor
        self._pan_anchor = cursor
        self.pan_request.emit(QPoint(int(step.x()), int(step.y())))

    def _track_drawing_cursor(self, pos: QPointF, event: QtGui.QMouseEvent) -> None:
        desired_line_shape_type = _CREATE_MODE_TO_SHAPE_TYPE[self.create_mode]
        if self._line.shape_type != desired_line_shape_type:
            self._line = dataclasses.replace(
                self._line, shape_type=desired_line_shape_type
            )
        self._apply_cursor(CursorRole.DRAW)
        if self._current is None:
            self.update()
            self._update_status()
            return
        is_shift_pressed = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        pos = self._project_drawing_pos_into_image(pos=pos)
        self._update_drawing_line(pos=pos, is_shift_pressed=is_shift_pressed)
        assert len(self._line.points) == len(self._line.point_labels)
        self.update()
        self._update_status()

    def _project_drawing_pos_into_image(self, pos: QPointF) -> QPointF:
        current = self._current
        assert current is not None
        if self.create_mode == "oriented_rectangle" and len(current.points) == 4:
            # The second click only locks the orientation of the first edge,
            # not its length. The third-corner cursor drives parallelogram
            # completion through the diagonal anchor at points[0], so the
            # clicked points[1] slides along the locked axis as the cursor
            # changes the rectangle's extent in that direction.
            MOVING_CORNER_INDEX: Final[int] = 2
            new_corners = _reproject_oriented_rectangle_corners(
                corners=current.points,
                vertex_index=MOVING_CORNER_INDEX,
                pos=pos,
                image_size=self.pixmap.size(),
                allow_out_of_bounds=self._allow_out_of_bounds_points,
            )
            self._current = dataclasses.replace(current, points=new_corners)
            return self._current.points[MOVING_CORNER_INDEX]
        if self._should_constrain_to_pixmap(pos):
            return _compute_intersection_edges_image(
                current.points[-1], pos, image_size=self.pixmap.size()
            )
        if not self._cursor_should_snap_to_polygon_origin(pos=pos):
            return pos
        self._apply_cursor(CursorRole.HANDLE)
        self._highlight_vertex(index=0, mode="near")
        return current.points[0]

    def _cursor_should_snap_to_polygon_origin(self, pos: QPointF) -> bool:
        if not self._snapping:
            return False
        if self.create_mode != "polygon":
            return False
        current = self._current
        if current is None or len(current.points) <= 1:
            return False
        origin = current.points[0]
        return _canvas_interaction.is_within_pick_threshold(
            a=np.array([pos.x(), pos.y()]),
            b=np.array([origin.x(), origin.y()]),
            scale=self.scale,
            epsilon=self._epsilon,
        )

    def _refresh_hover_state(self, pos: QPointF) -> None:
        status_messages: list[str] = []
        self._highlight_hover_shape(pos=pos, status_messages=status_messages)
        self.vertex_selected.emit(self._hovered_vertex is not None)
        self.edge_selected.emit(self._hovered_edge is not None)
        self._update_status(extra_messages=status_messages)

    def _update_drawing_line(self, pos: QPointF, is_shift_pressed: bool) -> QPointF:
        current = self._current
        assert current is not None
        mode = self.create_mode
        if mode in POLYLINE_SHAPE_TYPES:
            self._line = dataclasses.replace(
                self._line, points=(current.points[-1], pos), point_labels=(1, 1)
            )
        elif mode == "ai_points_to_shape":
            self._line = dataclasses.replace(
                self._line,
                points=(current.points[-1], pos),
                point_labels=(current.point_labels[-1], 0 if is_shift_pressed else 1),
            )
        elif mode in ("rectangle", "ai_box_to_shape"):
            if is_shift_pressed:
                pos = _snap_cursor_pos_for_square(
                    pos=pos, opposite_vertex=current.points[0]
                )
                self._prev_move_point = pos
            self._line = dataclasses.replace(
                self._line,
                points=(current.points[0], pos),
                point_labels=(1, 1),
                closed=True,
            )
        elif mode == "oriented_rectangle":
            origin = (
                current.points[0] if len(current.points) == 1 else current.points[1]
            )
            self._line = dataclasses.replace(
                self._line, points=(origin, pos), point_labels=(1, 1)
            )
        elif mode == "circle":
            self._line = dataclasses.replace(
                self._line, points=(current.points[0], pos), point_labels=(1, 1)
            )
        elif mode == "line":
            self._line = dataclasses.replace(
                self._line,
                points=(current.points[0], pos),
                point_labels=(1, 1),
                closed=True,
            )
        elif mode == "point":
            self._line = dataclasses.replace(
                self._line, points=(current.points[0],), point_labels=(1,), closed=True
            )
        return pos

    def _continue_right_button_drag(self, pos: QPointF) -> None:
        if self._selected_shapes_copy:
            self._apply_cursor(CursorRole.MOVE)
            self._drag_shapes(shapes=self._selected_shapes_copy, cursor=pos)
            self.update()
        elif self.selected_shapes:
            self._selected_shapes_copy = [s.copy() for s in self.selected_shapes]
            self.update()
        self._update_status()

    def _continue_left_button_drag(
        self, pos: QPointF, event: QtGui.QMouseEvent
    ) -> None:
        is_shift_pressed = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if self._is_vertex_selected():
            self._drag_hovered_vertex(pos=pos, is_shift_pressed=is_shift_pressed)
            return
        if self._is_rotation_point_selected():
            self._drag_hovered_rotation_point(pos=pos)
            return
        if not self.selected_shapes:
            return
        self._drag_selected_shapes(pos=pos)

    def _drag_hovered_vertex(self, pos: QPointF, is_shift_pressed: bool) -> None:
        assert self._hovered_vertex is not None
        assert self.hovered_shape is not None
        self._bounded_move_vertex(
            shape=self.hovered_shape,
            vertex_index=self._hovered_vertex,
            pos=pos,
            is_shift_pressed=is_shift_pressed,
        )
        self.update()
        self._is_moving_shape = True

    def _drag_hovered_rotation_point(self, pos: QPointF) -> None:
        assert self.hovered_shape is not None
        assert len(self._rotation_original_points) > 0, (
            "_capture_rotation_anchors must be called before dragging"
        )
        current_angle = _utils.direction_angle(
            start=self._rotation_center, end=(pos.x(), pos.y())
        )
        _shape.rotate(
            shape=self.hovered_shape,
            center=self._rotation_center,
            angle=current_angle - self._rotation_initial_angle,
            source_points=self._rotation_original_points,
        )
        self.update()
        self._is_moving_shape = True

    def _capture_rotation_anchors(self) -> None:
        assert self.hovered_shape is not None
        assert self._hovered_rotation is not None
        handle = _shape.get_rotation_handle(
            shape=self.hovered_shape, index=self._hovered_rotation
        )
        self._rotation_center = _shape.oriented_rectangle_center(
            shape=self.hovered_shape
        )
        self._rotation_initial_angle = _utils.direction_angle(
            start=self._rotation_center, end=handle
        )
        self._rotation_original_points = self.hovered_shape.points.copy()

    def _drag_selected_shapes(self, pos: QPointF) -> None:
        self._apply_cursor(CursorRole.MOVE)
        self._drag_shapes(shapes=self.selected_shapes, cursor=pos)
        self.update()
        self._is_moving_shape = True

    def _highlight_hover_shape(self, pos: QPointF, status_messages: list[str]) -> None:
        target = _canvas_interaction.find_hover_target(
            shapes=self.shapes,
            point=np.array([pos.x(), pos.y()]),
            scale=self.scale,
            epsilon=self._epsilon,
            point_size=self._point_size,
            priority_shape=self.hovered_shape,
        )

        if target is None:
            self._release_cursor()
            if self._set_highlight(
                hovered_shape=None,
                hovered_edge=None,
                hovered_vertex=None,
                hovered_rotation=None,
            ):
                self.update()
            return

        if target.kind is HitKind.VERTEX:
            assert target.index is not None
            self._set_highlight(
                hovered_shape=target.shape,
                hovered_edge=None,
                hovered_vertex=target.index,
                hovered_rotation=None,
            )
            self._highlight_vertex(index=target.index, mode="move")
            self._apply_cursor(CursorRole.HANDLE)
            status_messages.append(self.tr("Click & drag to move point"))
            if target.shape.can_remove_point():
                status_messages.append(self.tr("ALT + SHIFT + Click to delete point"))
            self.update()
            return

        if target.kind is HitKind.ROTATION_HANDLE:
            assert target.index is not None
            self._set_highlight(
                hovered_shape=target.shape,
                hovered_edge=None,
                hovered_vertex=None,
                hovered_rotation=target.index,
            )
            self._highlight_rotation_point(index=target.index, mode="move")
            self._apply_cursor(CursorRole.HANDLE)
            status_messages.append(self.tr("Click & drag to rotate the shape"))
            self.update()
            return

        if target.kind is HitKind.EDGE:
            assert target.index is not None
            self._set_highlight(
                hovered_shape=target.shape,
                hovered_edge=target.index,
                hovered_vertex=None,
                hovered_rotation=None,
            )
            self._apply_cursor(CursorRole.HANDLE)
            status_messages.append(self.tr("ALT + Click to create point on shape"))
            self.update()
            return

        if target.kind is HitKind.BODY:
            self._set_highlight(
                hovered_shape=target.shape,
                hovered_edge=None,
                hovered_vertex=None,
                hovered_rotation=None,
            )
            status_messages.extend(
                [
                    self.tr("Click & drag to move shape"),
                    self.tr("Right-click & drag to copy shape"),
                ]
            )
            self._apply_cursor(CursorRole.GRAB)
            self.update()
            return

        typing.assert_never(target.kind)

    def add_point_to_edge(self) -> None:
        shape = self._last_hovered_shape
        index = self._last_hovered_edge
        point = self._prev_move_point
        if shape is None or index is None or point is None:
            return
        shape.insert_point(index, (point.x(), point.y()))
        self._highlight_vertex(index=index, mode="move")
        self.hovered_shape = shape
        self._hovered_vertex = index
        self._hovered_edge = None
        self._is_moving_shape = True
        # Repaint now; otherwise the edit is invisible until the next mouse move.
        self.update()

    def remove_selected_point(self) -> bool:
        shape = self._last_hovered_shape
        index = self._last_hovered_vertex
        if shape is None or index is None or not shape.can_remove_point():
            return False
        shape.remove_point(index)
        self._clear_highlight_state()
        # Drop the hovered vertex and selection so the press that deleted the
        # point cannot also drag the adjacent vertex (#968) or the whole shape.
        self.deselect_shape()
        self.hovered_shape = shape
        self._hovered_vertex = None
        self._last_hovered_vertex = None
        self._is_moving_shape = True  # commit the removal on release
        # Repaint now; otherwise the edit is invisible until the next mouse move.
        self.update()
        return True

    def mousePressEvent(self, a0: QtGui.QMouseEvent) -> None:
        pos: QPointF = self._transform_point_widget_to_image(a0.position())
        self._dispatch_pointer_press(pos=pos, event=a0)
        self._update_status()

    def _dispatch_pointer_press(self, pos: QPointF, event: QtGui.QMouseEvent) -> None:
        button = event.button()
        if button == Qt.MouseButton.LeftButton:
            self._press_left(pos=pos, event=event)
            return
        if button == Qt.MouseButton.RightButton and self.mode == _CanvasMode.EDIT:
            self._press_right(pos=pos, event=event)
            return
        if (
            button == Qt.MouseButton.MiddleButton
            and self._is_image_overflowing_viewport()
        ):
            self._begin_pan(event=event)

    def _press_left(self, pos: QPointF, event: QtGui.QMouseEvent) -> None:
        is_shift_pressed = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if self.mode == _CanvasMode.CREATE:
            self._press_left_while_drawing(
                pos=pos, event=event, is_shift_pressed=is_shift_pressed
            )
            return
        if self.mode == _CanvasMode.EDIT:
            self._press_left_while_editing(pos=pos, event=event)

    def _press_left_while_drawing(
        self,
        pos: QPointF,
        event: QtGui.QMouseEvent,
        is_shift_pressed: bool,
    ) -> None:
        if self._current is not None:
            self._extend_current_shape(current=self._current, event=event)
            return
        if self._should_constrain_to_pixmap(pos):
            return
        self._start_new_shape(pos=pos, event=event, is_shift_pressed=is_shift_pressed)

    def _extend_current_shape(
        self, current: _DraftShape, event: QtGui.QMouseEvent
    ) -> None:
        mode = self.create_mode
        modifiers = event.modifiers()
        if mode == "polygon":
            current = current.add_point(self._line.points[1], autoclose=True)
            self._current = current
            self._line = dataclasses.replace(
                self._line, points=(current.points[-1],) + self._line.points[1:]
            )
            if current.closed:
                self._finalize()
        elif mode == "oriented_rectangle":
            if len(current.points) == 4:
                self._finalize()
            else:
                assert len(current.points) == 1
                self._lock_oriented_rectangle_first_edge(current=current)
        elif mode in ("rectangle", "circle", "line", "ai_box_to_shape"):
            assert len(current.points) == 1
            self._current = dataclasses.replace(current, points=self._line.points)
            self._finalize()
        elif mode == "linestrip":
            current = current.add_point(self._line.points[1])
            self._current = current
            self._line = dataclasses.replace(
                self._line, points=(current.points[-1],) + self._line.points[1:]
            )
            if modifiers == Qt.KeyboardModifier.ControlModifier:
                self._finalize()
        elif mode == "ai_points_to_shape":
            current = current.add_point(
                self._line.points[1], label=self._line.point_labels[1]
            )
            self._current = current
            self._line = dataclasses.replace(
                self._line,
                points=(current.points[-1],) + self._line.points[1:],
                point_labels=(current.point_labels[-1],) + self._line.point_labels[1:],
            )
            if modifiers & Qt.KeyboardModifier.ControlModifier:
                self._finalize()

    def _lock_oriented_rectangle_first_edge(self, current: _DraftShape) -> None:
        first_corner = self._line.points[0]
        second_corner = self._line.points[1]
        self._current = dataclasses.replace(
            current,
            points=(
                first_corner,
                second_corner,
                QPointF(second_corner),
                QPointF(first_corner),
            ),
            point_labels=(1, 1, 1, 1),
        )
        self._line = dataclasses.replace(
            self._line, points=(second_corner,) + self._line.points[1:]
        )

    def _unlock_oriented_rectangle_first_edge(self, current: _DraftShape) -> None:
        anchor = current.points[0]
        self._current = dataclasses.replace(
            current, points=(anchor,), point_labels=(current.point_labels[0],)
        )
        self._line = dataclasses.replace(self._line, points=(anchor, anchor))

    def _start_new_shape(
        self,
        pos: QPointF,
        event: QtGui.QMouseEvent,
        is_shift_pressed: bool,
    ) -> None:
        mode = self.create_mode
        if mode in ("ai_points_to_shape", "ai_box_to_shape") and not download_ai_model(
            model_name=self.get_ai_model_name(), parent=self
        ):
            return

        self._current = _DraftShape(
            shape_type=_CREATE_MODE_TO_SHAPE_TYPE[mode]
        ).add_point(pos, label=0 if is_shift_pressed else 1)

        if mode == "point":
            self._finalize()
            return
        if (
            mode == "ai_points_to_shape"
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            self._finalize()
            return

        self._line = dataclasses.replace(
            self._line,
            points=(pos, pos),
            point_labels=(
                (0, 0) if mode == "ai_points_to_shape" and is_shift_pressed else (1, 1)
            ),
        )
        self.drawing_polygon.emit(True)
        self.update()

    def _press_left_while_editing(self, pos: QPointF, event: QtGui.QMouseEvent) -> None:
        modifiers = event.modifiers()
        if self._maybe_modify_polygon_topology(modifiers=modifiers):
            # remove_selected_point already repainted; just consume the press.
            return
        if self._is_rotation_point_selected():
            self._capture_rotation_anchors()
        self._select_shape_point(
            pos,
            multiple_selection_mode=modifiers == Qt.KeyboardModifier.ControlModifier,
        )
        self._prev_point = pos
        self.update()

    def _maybe_modify_polygon_topology(self, modifiers: Qt.KeyboardModifier) -> bool:
        # Returns True only when the press is consumed as a terminal edit (a point
        # removal), so the caller skips point selection and starts no drag. Adding
        # a point intentionally falls through so the new vertex can be dragged.
        if self._is_edge_selected() and modifiers == Qt.KeyboardModifier.AltModifier:
            self.add_point_to_edge()
            return False
        if self._is_vertex_selected() and modifiers == (
            Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.ShiftModifier
        ):
            return self.remove_selected_point()
        return False

    def _press_right(self, pos: QPointF, event: QtGui.QMouseEvent) -> None:
        if _should_reselect_on_right_press(
            selected_shapes=self.selected_shapes, hovered_shape=self.hovered_shape
        ):
            self._select_shape_point(
                pos,
                multiple_selection_mode=event.modifiers()
                == Qt.KeyboardModifier.ControlModifier,
            )
            self.update()
        self._prev_point = pos

    def _begin_pan(self, event: QtGui.QMouseEvent) -> None:
        self._apply_cursor(CursorRole.GRAB)
        self._pan_anchor = QPointF(self.mapToGlobal(event.position().toPoint()))

    def mouseReleaseEvent(self, a0: QtGui.QMouseEvent) -> None:
        self._dispatch_pointer_release(event=a0)
        self._commit_pending_shape_move()
        self._update_status()

    def _dispatch_pointer_release(self, event: QtGui.QMouseEvent) -> None:
        button = event.button()
        if button == Qt.MouseButton.RightButton:
            self._release_right(event=event)
            return
        if button == Qt.MouseButton.LeftButton:
            self._release_left()
            return
        if button == Qt.MouseButton.MiddleButton:
            self._finish_pan()

    def _release_right(self, event: QtGui.QMouseEvent) -> None:
        menu = self.context_menus.menu_for(
            has_selection=len(self._selected_shapes_copy) > 0
        )
        self._release_cursor()
        self.context_menu_origin = self.mapToGlobal(event.position().toPoint())
        try:
            triggered = menu.exec(self.context_menu_origin)  # type: ignore
        finally:
            self.context_menu_origin = None
        if triggered:
            return
        if not self._selected_shapes_copy:
            return
        self._selected_shapes_copy.clear()
        self.update()

    def _release_left(self) -> None:
        if self.mode != _CanvasMode.EDIT:
            return
        if self.hovered_shape is None:
            return
        if not self._hovered_shape_is_selected:
            return
        if self._is_moving_shape:
            return
        self.selection_changed.emit(
            [s for s in self.selected_shapes if s != self.hovered_shape]
        )

    def _finish_pan(self) -> None:
        # Reset state and cursor unconditionally so a stray middle-button
        # release can never leave a grab cursor stuck on screen.
        self._pan_anchor = None
        self._release_cursor()

    def _is_image_overflowing_viewport(self) -> bool:
        if self.pixmap.isNull():
            return False
        viewport = self._scroll_viewport()
        if viewport is None:
            return False
        scaled_w = self.pixmap.width() * self.scale
        scaled_h = self.pixmap.height() * self.scale
        return scaled_w > viewport.width() or scaled_h > viewport.height()

    def _scroll_viewport(self) -> QtWidgets.QWidget | None:
        # Walk up the parent chain to the enclosing scroll area and return
        # its viewport. Returning None when no scroll area is found lets
        # callers degrade gracefully if the canvas is reparented (e.g. into
        # a splitter or a test harness).
        node: QtWidgets.QWidget | None = self.parentWidget()
        while node is not None:
            if isinstance(node, QtWidgets.QAbstractScrollArea):
                return node.viewport()
            node = node.parentWidget()
        return None

    def _commit_pending_shape_move(self) -> None:
        moved = _pick_pending_moved_shape(
            is_moving_shape=self._is_moving_shape,
            hovered_shape=self.hovered_shape,
            shapes=self.shapes,
        )
        if moved is None:
            return
        index = self.shapes.index(moved)
        if not np.array_equal(
            self.shape_backups[-1][index].points, self.shapes[index].points
        ):
            self.backup_shapes()
            self.shape_moved.emit()
        self._is_moving_shape = False

    def end_move(self, copy: bool) -> bool:
        assert self.selected_shapes and self._selected_shapes_copy
        assert len(self._selected_shapes_copy) == len(self.selected_shapes)
        if copy:
            self._apply_copy_move()
        else:
            self._apply_in_place_move()
        self._selected_shapes_copy.clear()
        self.update()
        self.backup_shapes()
        return True

    def _apply_copy_move(self) -> None:
        for i, clone in enumerate(self._selected_shapes_copy):
            self.shapes.append(clone)
            self.selected_shapes[i] = clone

    def _apply_in_place_move(self) -> None:
        for original, clone in zip(self.selected_shapes, self._selected_shapes_copy):
            original.points = clone.points

    def _can_close_shape(self) -> bool:
        if self.mode != _CanvasMode.CREATE:
            return False
        if self._current is None:
            return False
        if self.create_mode == "ai_points_to_shape":
            return True
        if self.create_mode == "linestrip":
            return len(self._current.points) >= 2
        if self.create_mode == "oriented_rectangle":
            # Points 2 and 3 are seeded as duplicates of points 1 and 0 after
            # the first edge is locked; mouse movement reprojects them. Treat
            # the shape as closeable only once the third corner has moved.
            return (
                len(self._current.points) == 4
                and self._current.points[2] != self._current.points[1]
            )
        return len(self._current.points) >= 3

    def mouseDoubleClickEvent(self, a0: QtGui.QMouseEvent) -> None:
        if self._double_click != "close":
            return
        if not self._can_close_shape():
            return
        self._finalize()

    def select_shapes(self, shapes: list[Shape]) -> None:
        self.selection_changed.emit(shapes)
        self.update()

    def _select_shape_point(
        self, point: QPointF, multiple_selection_mode: bool
    ) -> None:
        if self._hovered_vertex is not None:
            assert self.hovered_shape is not None
            self._highlight_vertex(index=self._hovered_vertex, mode="move")
            if self.deselect_shape():
                self.update()
            return

        clicked_shape = self._find_shape_at_point(point)
        if clicked_shape is None:
            if self.deselect_shape():
                self.update()
            return

        already_selected = clicked_shape in self.selected_shapes
        if already_selected:
            self._hovered_shape_is_selected = True
        else:
            new_selection = (
                self.selected_shapes + [clicked_shape]
                if multiple_selection_mode
                else [clicked_shape]
            )
            self.selection_changed.emit(new_selection)
            self._hovered_shape_is_selected = False
        self._record_drag_anchor(click=point)

    def _find_shape_at_point(self, point: QPointF) -> Shape | None:
        query = np.array([point.x(), point.y()])
        for shape in reversed(self.shapes):
            if shape.visible and is_hit_by_point(
                shape=shape,
                point=query,
                scale=self.scale,
                point_size=self._point_size,
                epsilon=self._epsilon,
            ):
                return shape
        return None

    def _record_drag_anchor(self, click: QPointF) -> None:
        if not self.selected_shapes:
            self._drag_anchor = (QPointF(), QRectF())
            return
        bounds = _shape_bounds(shape=self.selected_shapes[0])
        for s in self.selected_shapes[1:]:
            bounds = bounds.united(_shape_bounds(shape=s))
        self._drag_anchor = (bounds.topLeft() - click, bounds)

    def _bounded_move_vertex(
        self,
        shape: Shape,
        vertex_index: int,
        pos: QPointF,
        is_shift_pressed: bool,
    ) -> None:
        if vertex_index >= len(shape.points):
            logger.warning(
                "vertex_index is out of range: vertex_index={:d}, len(points)={:d}",
                vertex_index,
                len(shape.points),
            )
            return

        if shape.shape_type == "oriented_rectangle":
            self._bounded_move_oriented_rectangle_vertex(
                shape=shape, vertex_index=vertex_index, pos=pos
            )
            return

        if self._should_constrain_to_pixmap(pos):
            pos = _compute_intersection_edges_image(
                QPointF(*shape.points[vertex_index]), pos, image_size=self.pixmap.size()
            )

        if is_shift_pressed and shape.shape_type == "rectangle":
            pos = _snap_cursor_pos_for_square(
                pos=pos, opposite_vertex=QPointF(*shape.points[1 - vertex_index])
            )

        shape.move_vertex(i=vertex_index, pos=(pos.x(), pos.y()))

    def _bounded_move_oriented_rectangle_vertex(
        self, shape: Shape, vertex_index: int, pos: QPointF
    ) -> None:
        assert len(shape.points) == 4
        corners = tuple(QPointF(*point) for point in shape.points)
        new_corners = _reproject_oriented_rectangle_corners(
            corners=corners,
            vertex_index=vertex_index,
            pos=pos,
            image_size=self.pixmap.size(),
            allow_out_of_bounds=self._allow_out_of_bounds_points,
        )
        for i, corner in enumerate(new_corners):
            shape.move_vertex(i=i, pos=(corner.x(), corner.y()))

    def _drag_shapes(self, shapes: list[Shape], cursor: QPointF) -> bool:
        if self._should_constrain_to_pixmap(cursor):
            return False

        rel_tl, bounds = self._drag_anchor
        target = cursor + rel_tl
        if not self._allow_out_of_bounds_points:
            pw = float(self.pixmap.width())
            ph = float(self.pixmap.height())
            target.setX(max(0.0, target.x()))
            target.setY(max(0.0, target.y()))
            target.setX(min(target.x(), pw - bounds.width()))
            target.setY(min(target.y(), ph - bounds.height()))

        new_cursor = target - rel_tl
        delta = new_cursor - self._prev_point
        if delta.isNull():
            return False

        for shape in shapes:
            shape.translate(offset=(delta.x(), delta.y()))
        self._prev_point = new_cursor
        return True

    def deselect_shape(self) -> bool:
        if not self.selected_shapes:
            return False
        self.selection_changed.emit([])
        self._hovered_shape_is_selected = False
        return True

    def delete_selected(self) -> list[Shape]:
        if not self.selected_shapes:
            return []
        removed = list(self.selected_shapes)
        self.shapes = [s for s in self.shapes if s not in self.selected_shapes]
        self.backup_shapes()
        self.selected_shapes.clear()
        self.update()
        return removed

    def delete_shape(self, shape: Shape) -> None:
        if shape in self.selected_shapes:
            self.selected_shapes.remove(shape)
        self.shapes = [s for s in self.shapes if s is not shape]
        self.backup_shapes()
        self.update()

    def paintEvent(self, a0: QtGui.QPaintEvent) -> None:
        if self.pixmap.isNull():
            super().paintEvent(a0)
            return
        self._render_canvas()
        if self._current is not None:
            self._clear_highlight_state()

    def _render_canvas(self) -> None:
        self._palette_cache.clear()
        painter: QtGui.QPainter = self._painter
        painter.begin(self)
        try:
            self._setup_world_transform(painter=painter)
            for layer in self._render_layers():
                layer(painter)
        finally:
            painter.end()

    def _setup_world_transform(self, painter: QtGui.QPainter) -> None:
        for hint in (
            QtGui.QPainter.RenderHint.Antialiasing,
            QtGui.QPainter.RenderHint.SmoothPixmapTransform,
        ):
            painter.setRenderHint(hint)
        painter.translate(self._compute_image_origin_offset() * self.scale)

    def _render_layers(self) -> tuple[Callable[[QtGui.QPainter], None], ...]:
        # Order is z-order, back-to-front.
        return (
            self._draw_pixmap_layer,
            self._draw_crosshair_layer,
            self._draw_committed_shapes_layer,
            self._draw_active_shape_layer,
            self._draw_drag_copy_layer,
            self._draw_preview_overlay_layer,
        )

    def _draw_pixmap_layer(self, painter: QtGui.QPainter) -> None:
        target = QtCore.QRectF(
            0.0,
            0.0,
            self.pixmap.width() * self.scale,
            self.pixmap.height() * self.scale,
        )
        painter.drawPixmap(target, self.pixmap, QtCore.QRectF(self.pixmap.rect()))

    def _draw_crosshair_layer(self, painter: QtGui.QPainter) -> None:
        cursor: QPointF | None = self._prev_move_point
        if not self._should_draw_crosshair(cursor=cursor):
            return
        assert cursor is not None
        painter.setPen(self.palette().color(QtGui.QPalette.ColorRole.WindowText))
        cx = int(cursor.x() * self.scale)
        cy = int(cursor.y() * self.scale)
        if self._allow_out_of_bounds_points:
            # The cursor may be in the margin around the image, so span the whole
            # viewport instead of stopping the lines at the image edge.
            offset = self._compute_image_origin_offset() * self.scale
            area = super().size()
            left = int(-offset.x())
            top = int(-offset.y())
            right = int(-offset.x() + area.width())
            bottom = int(-offset.y() + area.height())
        else:
            left = top = 0
            right = int(self.pixmap.width() * self.scale) - 1
            bottom = int(self.pixmap.height() * self.scale) - 1
        painter.drawLine(left, cy, right, cy)
        painter.drawLine(cx, top, cx, bottom)

    def _should_draw_crosshair(self, cursor: QPointF | None) -> bool:
        if self.mode != _CanvasMode.CREATE:
            return False
        if not self._crosshair[self._create_mode]:
            return False
        if cursor is None:
            return False
        return not self._should_constrain_to_pixmap(cursor)

    def _draw_committed_shapes_layer(self, painter: QtGui.QPainter) -> None:
        for shape in self.shapes:
            if not shape.visible:
                continue
            context = self._render_context(
                shape=shape, highlighted=shape is self.hovered_shape
            )
            render_shape(painter=painter, shape=shape, context=context)

    def _draw_active_shape_layer(self, painter: QtGui.QPainter) -> None:
        if self._current is None:
            return
        assert len(self._line.points) == len(self._line.point_labels)
        self._render_draft(painter=painter, draft=self._current, highlighted=True)
        self._render_draft(painter=painter, draft=self._line, highlighted=False)

    def _draw_drag_copy_layer(self, painter: QtGui.QPainter) -> None:
        for copy_shape in self._selected_shapes_copy:
            context = ShapeRenderContext(
                scale=self.scale,
                palette=self._resolve_palette(copy_shape.label),
                point_size=self._point_size,
                point_type=self._point_type,
                selected=True,
                fill=True,
                highlight=None,
                rotation_highlight=None,
                show_label=self._show_labels,
            )
            render_shape(painter=painter, shape=copy_shape, context=context)

    def _draw_preview_overlay_layer(self, painter: QtGui.QPainter) -> None:
        preview = self._build_preview_shape()
        if preview is None:
            return
        context = self._draft_render_context(
            selected=self._fill_drawing,
            fill=self._fill_drawing,
            highlight=None,
            rotation_highlight=None,
        )
        render_shape(painter=painter, shape=preview, context=context)

    def _render_draft(
        self, painter: QtGui.QPainter, draft: _DraftShape, highlighted: bool
    ) -> None:
        shape = _draft_to_shape(draft)
        context = self._draft_render_context(
            selected=False,
            fill=False,
            highlight=self._highlight if highlighted else None,
            rotation_highlight=self._rotation_highlight if highlighted else None,
        )
        render_shape(painter=painter, shape=shape, context=context)

    def _build_preview_shape(self) -> Shape | None:
        if self._current is None:
            return None
        if self.create_mode == "polygon":
            return self._build_polygon_preview(current=self._current)
        if self.create_mode == "ai_points_to_shape":
            return self._build_ai_points_preview(current=self._current)
        return None

    def _build_polygon_preview(self, current: _DraftShape) -> Shape:
        preview = current
        if self._fill_drawing and len(preview.points) >= 2:
            preview = preview.add_point(point=self._line.points[1], autoclose=True)
        return _draft_to_shape(preview)

    def _build_ai_points_preview(self, current: _DraftShape) -> Shape:
        preview = current.add_point(
            point=self._line.points[1],
            label=self._line.point_labels[1],
        )
        try:
            ai_shapes = self._shapes_from_ai_points(
                points=preview.points,
                point_labels=preview.point_labels,
            )
        except Exception as e:
            # This runs inside paintEvent on every repaint, so a persistently
            # failing model would report on every frame. Report once; a later
            # success re-arms the report.
            if not self._ai_inference_failed:
                self._report_inference_failure(error=e)
            return _draft_to_shape(preview)
        self._ai_inference_failed = False
        if ai_shapes:
            return ai_shapes[0]
        return _draft_to_shape(preview)

    def _transform_point_widget_to_image(self, point: QPointF) -> QPointF:
        origin = self._compute_image_origin_offset()
        image_x = point.x() / self.scale - origin.x()
        image_y = point.y() / self.scale - origin.y()
        return QPointF(image_x, image_y)

    def _compute_image_origin_offset(self) -> QPointF:
        area = super().size()
        scaled_w = self.pixmap.width() * self.scale
        scaled_h = self.pixmap.height() * self.scale
        slack_w = max(area.width() - scaled_w, 0.0)
        slack_h = max(area.height() - scaled_h, 0.0)
        return QPointF(slack_w, slack_h) / (2.0 * self.scale)

    def is_out_of_pixmap(self, p: QPointF) -> bool:
        return _is_out_of_image(p, self.pixmap.size())

    def _should_constrain_to_pixmap(self, point: QPointF) -> bool:
        return not self._allow_out_of_bounds_points and self.is_out_of_pixmap(point)

    def _finalize(self) -> None:
        assert self._current is not None
        if self.create_mode in _AI_CREATE_MODES:
            try:
                new_shapes = self._build_new_shapes_from_ai_inference()
            except Exception as e:
                self._report_inference_failure(error=e)
                self._cancel_current_shape()
                return
            self._ai_inference_failed = False
            if not new_shapes:
                self.inference_produced_no_shapes.emit()
                self._cancel_current_shape()
                return
        else:
            self._current = self._current.close()
            if _is_degenerate_draft(self._current):
                self.degenerate_shape_rejected.emit()
                self._cancel_current_shape()
                return
            new_shapes = [_draft_to_shape(self._current)]
        self.shapes.extend(new_shapes)
        self.backup_shapes()
        self._reset_after_shape_creation()

    def _build_new_shapes_from_ai_inference(self) -> list[Shape]:
        assert self._current is not None
        if self.create_mode == "ai_points_to_shape":
            return self._shapes_from_ai_points(
                points=self._current.points,
                point_labels=self._current.point_labels,
            )
        if self.create_mode == "ai_box_to_shape":
            # point_labels: 2=box corner, 3=opposite box corner (SAM convention)
            return self._shapes_from_ai_points(
                points=_normalize_bbox_points(bbox_points=self._current.points),
                point_labels=[2, 3],
            )
        raise AssertionError(f"unreachable: {self.create_mode}")

    def _reset_after_shape_creation(self) -> None:
        self._current = None
        self.new_shape.emit()
        self.update()

    def _cancel_current_shape(self) -> None:
        self._current = None
        self.drawing_polygon.emit(False)
        self.update()

    # Required by QScrollArea: it queries these to compute the
    # scrollable viewport whenever adjustSize() is called.
    def _compute_canvas_size(self) -> QtCore.QSize:
        if self.pixmap.isNull():
            return super().minimumSizeHint()
        scaled_w = int(self.pixmap.width() * self.scale)
        scaled_h = int(self.pixmap.height() * self.scale)
        viewport = self._scroll_viewport()
        if viewport is None:
            return QtCore.QSize(scaled_w, scaled_h)
        slack_w = _compute_overscroll_slack(scaled=scaled_w, viewport=viewport.width())
        slack_h = _compute_overscroll_slack(scaled=scaled_h, viewport=viewport.height())
        return QtCore.QSize(scaled_w + slack_w, scaled_h + slack_h)

    def sizeHint(self) -> QtCore.QSize:
        return self._compute_canvas_size()

    def minimumSizeHint(self) -> QtCore.QSize:
        return self._compute_canvas_size()

    def wheelEvent(self, a0: QtGui.QWheelEvent) -> None:
        mods: Qt.KeyboardModifier = a0.modifiers()
        delta: QPoint = a0.angleDelta()
        if mods == Qt.KeyboardModifier.ControlModifier:
            # with Ctrl/Command key
            # zoom
            self.zoom_request.emit(delta.y(), a0.position())
        elif mods == Qt.KeyboardModifier.ShiftModifier and delta.x() == 0:
            # Shift+wheel scrolls horizontally. macOS swaps the axis for us,
            # but Linux/Windows deliver the delta on y and expect the app to
            # remap it.
            self.scroll_request.emit(delta.y(), Qt.Orientation.Horizontal)
        else:
            # scroll
            self.scroll_request.emit(delta.x(), Qt.Orientation.Horizontal)
            self.scroll_request.emit(delta.y(), Qt.Orientation.Vertical)
        a0.accept()

    def _move_by_keyboard(self, offset: QPointF) -> None:
        if not self.selected_shapes:
            return
        self._drag_shapes(shapes=self.selected_shapes, cursor=self._prev_point + offset)
        self.update()
        self._is_moving_shape = True

    def keyPressEvent(self, a0: QtGui.QKeyEvent) -> None:
        modifiers = a0.modifiers()
        key = a0.key()
        if self.mode == _CanvasMode.CREATE:
            if key == Qt.Key.Key_Escape and self._current is not None:
                self._cancel_current_shape()
            elif (
                key in (Qt.Key.Key_Return, Qt.Key.Key_Space) and self._can_close_shape()
            ):
                self._finalize()
            elif modifiers == Qt.KeyboardModifier.AltModifier:
                self._snapping = False
        elif self.mode == _CanvasMode.EDIT:
            if key == Qt.Key.Key_Up:
                self._move_by_keyboard(QPointF(0.0, -MOVE_SPEED))
            elif key == Qt.Key.Key_Down:
                self._move_by_keyboard(QPointF(0.0, MOVE_SPEED))
            elif key == Qt.Key.Key_Left:
                self._move_by_keyboard(QPointF(-MOVE_SPEED, 0.0))
            elif key == Qt.Key.Key_Right:
                self._move_by_keyboard(QPointF(MOVE_SPEED, 0.0))
            elif a0.matches(QtGui.QKeySequence.StandardKey.SelectAll):
                self.select_shapes(shapes=self.shapes[:])
        self._update_status()

    def keyReleaseEvent(self, a0: QtGui.QKeyEvent) -> None:
        modifiers = a0.modifiers()
        if self.mode == _CanvasMode.CREATE:
            if not modifiers:
                self._snapping = True
        elif self.mode == _CanvasMode.EDIT:
            if (
                self._is_moving_shape
                and self.selected_shapes
                and self.selected_shapes[0] in self.shapes
            ):
                index = self.shapes.index(self.selected_shapes[0])
                if not np.array_equal(
                    self.shape_backups[-1][index].points, self.shapes[index].points
                ):
                    self.backup_shapes()
                    self.shape_moved.emit()

                self._is_moving_shape = False

    def set_last_label(self, text: str, flags: dict[str, bool]) -> list[Shape]:
        if not text:
            raise ValueError("text must not be empty")
        shapes = []
        for shape in reversed(self.shapes):
            if shape.label is not None:
                break
            shapes.append(shape)
        shapes.reverse()
        for shape in shapes:
            shape.label = text
            shape.flags = flags
        self.shape_backups.pop()
        self.backup_shapes()
        return shapes

    def undo_last_line(self) -> None:
        assert self.shapes
        if self.create_mode in _AI_CREATE_MODES:
            # Remove all unlabeled shapes at the tail (added by AI in one shot)
            while self.shapes and self.shapes[-1].label is None:
                self.shapes.pop()
            self._cancel_current_shape()
            return
        self._current = _shape_to_draft(self.shapes.pop()).open()
        if self.create_mode in POLYLINE_SHAPE_TYPES:
            self._line = dataclasses.replace(
                self._line,
                points=(self._current.points[-1], self._current.points[0]),
            )
        elif self.create_mode in (
            "rectangle",
            "line",
            "circle",
            "ai_box_to_shape",
        ):
            self._current = dataclasses.replace(
                self._current,
                points=self._current.points[0:1],
                point_labels=self._current.point_labels[0:1],
            )
        elif self.create_mode == "point":
            self._current = None
        else:
            assert self.create_mode == "oriented_rectangle"
        self.drawing_polygon.emit(True)

    def undo_last_point(self) -> None:
        current = self._current
        if current is None or current.closed:
            return
        if self.create_mode == "oriented_rectangle" and len(current.points) == 4:
            self._unlock_oriented_rectangle_first_edge(current=current)
            self.update()
            return
        current = current.pop_point()
        self._current = current
        if len(current.points) > 0:
            self._line = dataclasses.replace(
                self._line, points=(current.points[-1],) + self._line.points[1:]
            )
            self.update()
        else:
            self._cancel_current_shape()

    def _reset_interaction_state(self) -> None:
        self._current = None
        self.hovered_shape = None
        self._hovered_vertex = None
        self._hovered_edge = None
        self._hovered_rotation = None
        self._clear_highlight_state()

    def load_pixmap(self, pixmap: QtGui.QPixmap, clear_shapes: bool = True) -> None:
        pixmap_arr = _utils.img_qt_to_arr(img_qt=pixmap.toImage())
        self.pixmap = pixmap
        self._pixmap_hash = hash(pixmap_arr.tobytes())
        # A new image is a fresh inference context that should surface its own
        # first failure rather than staying muted by the prior image's latch.
        self._ai_inference_failed = False
        if clear_shapes:
            self.shapes = []
        self.update()

    def load_shapes(self, shapes: list[Shape], replace: bool = True) -> None:
        self.shapes = list(shapes) if replace else self.shapes + list(shapes)
        self.backup_shapes()
        self._reset_interaction_state()
        self.update()

    def set_shape_visible(self, shape: Shape, value: bool) -> None:
        if shape.visible == value:
            return
        shape.visible = value
        self.update()

    def _apply_cursor(self, role: CursorRole) -> None:
        if role == self._cursor:
            return
        shape = _canvas_interaction.cursor_shape_for(role=role)
        # Push on first apply; swap the top of the stack we already own afterwards.
        if self._cursor == CursorRole.DEFAULT:
            QtWidgets.QApplication.setOverrideCursor(shape)
        else:
            QtWidgets.QApplication.changeOverrideCursor(shape)
        self._cursor = role

    def _release_cursor(self) -> None:
        if self._cursor == CursorRole.DEFAULT:
            return
        self._cursor = CursorRole.DEFAULT
        QtWidgets.QApplication.restoreOverrideCursor()

    def reset_state(self) -> None:
        self._release_cursor()
        self.pixmap = QtGui.QPixmap()
        self._pixmap_hash = None
        self.shapes = []
        self.shape_backups = collections.deque(maxlen=self._num_backups)
        self._is_moving_shape = False
        self.selected_shapes = []
        self._selected_shapes_copy = []
        self._current = None
        self._highlight = None
        self._rotation_highlight = None
        self.hovered_shape = None
        self._last_hovered_shape = None
        self._hovered_vertex = None
        self._last_hovered_vertex = None
        self._hovered_edge = None
        self._last_hovered_edge = None
        self._hovered_rotation = None
        self.update()


def _is_degenerate_draft(draft: _DraftShape) -> bool:
    points = draft.points
    shape_type = draft.shape_type
    if shape_type == "polygon":
        return len({(p.x(), p.y()) for p in points}) < 3
    if shape_type == "linestrip":
        return len({(p.x(), p.y()) for p in points}) < 2
    if shape_type == "rectangle":
        return (
            len(points) != 2
            or points[0].x() == points[1].x()
            or points[0].y() == points[1].y()
        )
    if shape_type in ("circle", "line"):
        return len(points) != 2 or points[0] == points[1]
    if shape_type == "oriented_rectangle":
        return len(points) != 4 or points[0] == points[1] or points[1] == points[2]
    return False


def _normalize_bbox_points(bbox_points: Sequence[QPointF]) -> list[QPointF]:
    if len(bbox_points) != 2:
        raise ValueError(f"Expected 2 points for bbox, got {len(bbox_points)}")

    p1, p2 = bbox_points
    xmin = min(p1.x(), p2.x())
    ymin = min(p1.y(), p2.y())
    xmax = max(p1.x(), p2.x())
    ymax = max(p1.y(), p2.y())
    return [QPointF(xmin, ymin), QPointF(xmax, ymax)]


def _snap_cursor_pos_for_square(pos: QPointF, opposite_vertex: QPointF) -> QPointF:
    pos_from_opposite: QPointF = pos - opposite_vertex
    square_size: float = min(abs(pos_from_opposite.x()), abs(pos_from_opposite.y()))
    return opposite_vertex + QPointF(
        np.sign(pos_from_opposite.x()) * square_size,
        np.sign(pos_from_opposite.y()) * square_size,
    )


def _compute_overscroll_slack(*, scaled: int, viewport: int) -> int:
    # Floor (viewport // 8) keeps middle-drag pan responsive at slight
    # overflow; without it, scroll range equals the overflow and a
    # 2-px-overflowing image feels locked under the cursor. The floor
    # reintroduces a viewport/16 image shift at the threshold, 4x smaller
    # than the original viewport/4 jump. Cap (viewport // 2) lets each
    # image edge be panned to the viewport center but no further.
    if scaled <= viewport:
        return 0
    return max(viewport // 8, min(viewport // 2, scaled - viewport))


def _compute_intersection_edges_image(
    p1: QPointF, p2: QPointF, image_size: QtCore.QSize
) -> QPointF:
    width = image_size.width()
    height = image_size.height()

    start_x = np.clip(p1.x(), 0.0, width)
    start_y = np.clip(p1.y(), 0.0, height)
    delta_x = p2.x() - start_x
    delta_y = p2.y() - start_y

    # Liang-Barsky line clipping.
    boundary_pairs = (
        ("x", start_x, -delta_x),
        ("x", width - start_x, delta_x),
        ("y", start_y, -delta_y),
        ("y", height - start_y, delta_y),
    )
    t_exit = 1.0
    exit_axis = "x"
    for axis, numerator, denominator in boundary_pairs:
        if denominator > 0.0:
            t = numerator / denominator
            if t < t_exit:
                t_exit = t
                exit_axis = axis

    if t_exit > 0.0:
        return QPointF(start_x + t_exit * delta_x, start_y + t_exit * delta_y)

    # t_exit == 0: start is on a boundary and p2 is exterior. Slide along the
    # edge the segment actually exits through. At a corner start sits on both an
    # x and a y boundary, so the exiting axis, not start's position, picks it.
    if exit_axis == "x":
        return QPointF(start_x, np.clip(p2.y(), 0.0, height))
    return QPointF(np.clip(p2.x(), 0.0, width), start_y)


def _should_reselect_on_right_press(
    selected_shapes: list[Shape], hovered_shape: Shape | None
) -> bool:
    if not selected_shapes:
        return True
    if hovered_shape is None:
        return False
    return hovered_shape not in selected_shapes


def _pick_pending_moved_shape(
    is_moving_shape: bool, hovered_shape: Shape | None, shapes: list[Shape]
) -> Shape | None:
    if not is_moving_shape:
        return None
    if hovered_shape is None:
        return None
    if hovered_shape not in shapes:
        return None
    return hovered_shape


def _opposite_corner_in_parallelogram(
    *, opposite_to: QPointF, neighbor1: QPointF, neighbor2: QPointF
) -> QPointF:
    return neighbor1 + neighbor2 - opposite_to


def _project_oriented_rectangle_corners(
    *, anchor: QPointF, edge_axis: QPointF, moving: QPointF
) -> tuple[QPointF, QPointF]:
    perp = _utils.project_point_on_perpendicular_line(
        point=moving, line_start=edge_axis, line_end=anchor
    )
    para = _opposite_corner_in_parallelogram(
        opposite_to=perp, neighbor1=anchor, neighbor2=moving
    )
    return perp, para


def _is_out_of_image(point: QPointF, image_size: QtCore.QSize) -> bool:
    return (
        point.x() < 0
        or point.y() < 0
        or point.x() > image_size.width()
        or point.y() > image_size.height()
    )


def _reproject_oriented_rectangle_corners(
    *,
    corners: tuple[QPointF, ...],
    vertex_index: int,
    pos: QPointF,
    image_size: QtCore.QSize,
    allow_out_of_bounds: bool,
) -> tuple[QPointF, ...]:
    """Given a 4-corner oriented rectangle and a dragged corner, return the new
    corner positions: the dragged corner and its two neighbors move so the shape
    stays a parallelogram, clipped to the image unless out-of-bounds points are
    allowed; the opposite anchor is fixed."""
    anchor = corners[(vertex_index - 2) % 4]
    edge_axis = corners[(vertex_index - 1) % 4]
    moving = pos
    adjacent_perp, adjacent_para = _project_oriented_rectangle_corners(
        anchor=anchor, edge_axis=edge_axis, moving=moving
    )

    if not allow_out_of_bounds:
        if _is_out_of_image(moving, image_size):
            edge_a = _compute_intersection_edges_image(
                p1=adjacent_perp, p2=moving, image_size=image_size
            )
            edge_b = _compute_intersection_edges_image(
                p1=adjacent_para, p2=moving, image_size=image_size
            )
            moving = _utils.project_point_on_line(
                point=moving, line_start=edge_a, line_end=edge_b
            )
            adjacent_perp, adjacent_para = _project_oriented_rectangle_corners(
                anchor=anchor, edge_axis=adjacent_para, moving=moving
            )

        if _is_out_of_image(adjacent_perp, image_size):
            adjacent_perp = _compute_intersection_edges_image(
                p1=anchor, p2=adjacent_perp, image_size=image_size
            )
            moving = _opposite_corner_in_parallelogram(
                opposite_to=anchor, neighbor1=adjacent_perp, neighbor2=adjacent_para
            )

        if _is_out_of_image(adjacent_para, image_size):
            adjacent_para = _compute_intersection_edges_image(
                p1=anchor, p2=adjacent_para, image_size=image_size
            )
            moving = _opposite_corner_in_parallelogram(
                opposite_to=anchor, neighbor1=adjacent_perp, neighbor2=adjacent_para
            )

    new_corners = list(corners)
    new_corners[vertex_index] = moving
    new_corners[(vertex_index + 1) % 4] = adjacent_perp
    new_corners[(vertex_index - 1) % 4] = adjacent_para
    return tuple(new_corners)
