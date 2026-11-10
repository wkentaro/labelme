from __future__ import annotations

import collections
import copy
import dataclasses
import enum
import functools
import typing
from collections.abc import Callable
from collections.abc import Sequence
from typing import Any
from typing import Final
from typing import Literal
from typing import cast
from typing import override

import numpy as np
from loguru import logger
from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets
from PySide6.QtCore import QPoint
from PySide6.QtCore import QPointF
from PySide6.QtCore import QRectF
from PySide6.QtCore import Qt

from .. import _ai_models
from .. import _automation
from .. import _config
from .. import _shape
from .. import _utils
from .._shape import CIRCLE_POINT_COUNT
from .._shape import MIN_LINESTRIP_POINT_COUNT
from .._shape import MIN_POLYGON_POINT_COUNT
from .._shape import ORIENTED_RECTANGLE_POINT_COUNT
from .._shape import POLYLINE_SHAPE_TYPES
from .._shape import RECTANGLE_POINT_COUNT
from .._shape import Shape
from .._shape import ShapeType
from . import _canvas_interaction
from ._canvas_interaction import CursorRole
from ._canvas_interaction import HitKind
from ._hint_chip import RETURN_GLYPH
from ._hint_chip import HintItem
from ._hint_chip import paint_hint_chip
from ._hint_chip import place_hint_chip
from ._shape_render import NEGATIVE_RGB
from ._shape_render import Palette
from ._shape_render import ShapeRenderContext
from ._shape_render import VertexHighlight
from ._shape_render import bounds as _shape_bounds
from ._shape_render import intersects_rect
from ._shape_render import render_shape

_DEFAULT_SHAPE_RGB: Final[tuple[int, int, int]] = (0, 255, 0)
_DEFAULT_PALETTE: Final[Palette] = Palette.from_rgb(rgb=_DEFAULT_SHAPE_RGB)
# The shipped config's draft colours, so a canvas the app hasn't configured
# (as in tests) draws drafts the way users see them.
_DEFAULT_DRAFT_PALETTE: Final[Palette] = Palette.from_shape_config(
    shape=_config.load_config(config_file=None, config_overrides={})["shape"]
)
_NEGATIVE_PALETTE: Final[Palette] = Palette.from_rgb(rgb=NEGATIVE_RGB)


def _drawn_corners(*, shape: Shape) -> np.ndarray:
    # Where the shape is drawn, not its raw points: a circle's points are its
    # center and a point on its rim.
    rect = _shape_bounds(shape=shape)
    return np.array([[rect.left(), rect.top()], [rect.right(), rect.bottom()]])


def _bounding_corners(*, points: list[np.ndarray]) -> tuple[QPointF, QPointF]:
    stacked = np.concatenate(points)
    return QPointF(*stacked.min(axis=0)), QPointF(*stacked.max(axis=0))


def _paint_box_mark(
    painter: QtGui.QPainter, center: QPointF, /, *, color: QtGui.QColor
) -> None:
    # A small prompt box, dashed like the ones on the canvas.
    pen = QtGui.QPen(color, 1.5)
    pen.setDashPattern([2.0, 1.5])
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRect(QRectF(center.x() - 6.5, center.y() - 5.0, 13.0, 10.0))


@dataclasses.dataclass
class _DragAnchor:
    rel_tl: QPointF
    bounds: QRectF
    origin: QPointF
    last_cursor: QPointF
    sources: dict[Shape, np.ndarray]
    limits: tuple[QtCore.QSize, bool]
    requested_cursor: tuple[float, float] | None = None

    def is_current(self, *, shapes: list[Shape], cursor: QPointF) -> bool:
        if self.sources.keys() != set(shapes):
            return False
        if (cursor.x(), cursor.y()) != (self.last_cursor.x(), self.last_cursor.y()):
            return False
        offset = self.last_cursor - self.origin
        # Bounds alone miss interior vertex edits and replacement geometry.
        return all(
            np.array_equal(shape.points, source + (offset.x(), offset.y()))
            for shape, source in self.sources.items()
        )

    def place(self, *, cursor: QPointF) -> None:
        offset = cursor - self.origin
        for shape, source in self.sources.items():
            points = source + (offset.x(), offset.y())
            if not np.array_equal(shape.points, points):
                shape.points = points
        self.last_cursor = QPointF(cursor)


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
        self, *, point: QPointF, label: int = 1, autoclose: bool = False
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


def _draft_to_shape(*, draft: _DraftShape) -> Shape:
    return Shape(
        shape_type=draft.shape_type,
        points=np.array([[p.x(), p.y()] for p in draft.points], dtype=np.float64),
        point_labels=np.array(draft.point_labels, dtype=np.int_),
        closed=draft.closed,
    )


def _shape_to_draft(*, shape: Shape) -> _DraftShape:
    return _DraftShape(
        shape_type=shape.shape_type,
        points=tuple(QPointF(*point) for point in shape.points),
        point_labels=tuple(int(label) for label in shape.point_labels),
        closed=shape.closed,
    )


MOVE_SPEED: Final[float] = 5.0

_ARROW_KEY_TO_DIRECTION: Final[dict[Qt.Key, QPointF]] = {
    Qt.Key.Key_Up: QPointF(0.0, -1.0),
    Qt.Key.Key_Down: QPointF(0.0, 1.0),
    Qt.Key.Key_Left: QPointF(-1.0, 0.0),
    Qt.Key.Key_Right: QPointF(1.0, 0.0),
}

_CreateMode = Literal[
    "polygon",
    "rectangle",
    "oriented_rectangle",
    "circle",
    "line",
    "point",
    "linestrip",
    "ai_segment",
    "ai_find_all",
]


@dataclasses.dataclass(frozen=True, eq=False)
class _AiJob:
    """An AI Assist request in flight, with what its result applies to."""

    pixmap_key: int
    prompt_kind: _automation.AiPromptKind
    points: np.ndarray
    point_labels: np.ndarray
    image_size: tuple[int, int] | None
    channel: Literal["preview", "result", "finalize"]
    # The draft a finalize commits, or the inputs a preview or result shows.
    draft: _DraftShape | None = None
    preview_key: object = None
    # The AI-Find All query sent with an example box; it labels the results.
    query: str = ""


_AI_PROGRESS_RADIUS: Final = 12


_AI_CREATE_MODES: Final[tuple[_CreateMode, ...]] = ("ai_segment", "ai_find_all")
# AI-Segment prompt labels: 0, 1 = negative, positive point; 2, 3 = box corners.
_AI_BOX_LABELS: Final = (2, 3)


_CREATE_MODE_TO_SHAPE_TYPE: Final[dict[_CreateMode, ShapeType]] = {
    "polygon": "polygon",
    "rectangle": "rectangle",
    "oriented_rectangle": "oriented_rectangle",
    "circle": "circle",
    "line": "line",
    "point": "point",
    "linestrip": "linestrip",
    "ai_segment": "points",
    "ai_find_all": "rectangle",
}


class _CanvasMode(enum.Enum):
    CREATE = enum.auto()
    EDIT = enum.auto()


class Canvas(QtWidgets.QWidget):
    _epsilon: float
    _double_click: Literal["close"] | None
    _num_backups: int
    _allow_out_of_bounds_points: bool
    _crosshair: dict[str, bool]
    _ai_preview_timer: QtCore.QTimer
    _line: _DraftShape
    _scale: float
    _osam_worker: _automation.OsamWorker | None
    _ai_preview_job: _AiJob | None
    _ai_result_job: _AiJob | None
    _ai_finalize_job: _AiJob | None
    _ai_progress_clock: QtCore.QElapsedTimer
    _ai_progress_timer: QtCore.QTimer
    _ai_inference_failed: bool
    _snapping: bool
    _hovered_shape_is_selected: bool
    _painter: QtGui.QPainter
    _dirty_rect: QtCore.QRect
    _fill_drawing: bool
    _show_labels: bool
    _view_offset: QPointF
    _ai_prompt_hint_due: bool

    ensure_ai_model_ready: Callable[[str], bool]
    # Read on use: the AI-Find All picker can change mid-draft or on download.
    get_ai_find_all_model_name: Callable[[], str]
    # (score, IoU) thresholds of AI-Find All, also read on use.
    get_ai_find_all_thresholds: Callable[[], tuple[float, float]]
    # The AI-Find All query, which an example box detects together with.
    get_ai_find_all_query: Callable[[], str]

    pixmap: QtGui.QPixmap
    _pixmap_rgb: tuple[np.ndarray, str] | None
    _cursor: CursorRole
    shapes: list[Shape]
    shape_context_menu: QtWidgets.QMenu
    canvas_context_menu: QtWidgets.QMenu
    context_menu_origin: QtCore.QPoint | None
    _right_click_shape: Shape | None
    shape_backups: collections.deque[list[Shape]]
    _is_moving_shape: bool
    _is_pointer_held: bool
    selected_shapes: list[Shape]
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
    # The AI-Find All query that found the new Shapes; it prefills their label
    # dialog. Empty for every other tool.
    new_shape = QtCore.Signal()
    inference_produced_no_shapes = QtCore.Signal()
    inference_failed = QtCore.Signal(str)
    example_box_unsupported = QtCore.Signal()
    # (draft Shapes, propose for a label, query): the app labels the batch and
    # adds what propose returns for that label.
    ai_find_all_draft_committed = QtCore.Signal(list, object, str)
    degenerate_shape_rejected = QtCore.Signal()
    selection_changed = QtCore.Signal(list)
    shape_double_clicked = QtCore.Signal()
    shape_moved = QtCore.Signal()
    # Emitted when is_busy or is_drawing may have changed.
    busy_changed = QtCore.Signal()
    vertex_selected = QtCore.Signal(bool)
    edge_selected = QtCore.Signal(bool)
    mouse_moved = QtCore.Signal(QPointF)
    status_updated = QtCore.Signal(str)

    mode: _CanvasMode = _CanvasMode.EDIT

    _create_mode: _CreateMode = "polygon"

    # Until the first prompt after switching to a tool, an AI tool says how
    # to give one.
    _ai_prompt_hint_due = False

    _fill_drawing = False

    _show_labels = False

    _prev_point: QPointF
    _prev_move_point: QPointF
    _drag_anchor: _DragAnchor | None
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
    _ai_suppress_existing_shape_matches: bool
    _ai_existing_shape_highlights: list[Shape]
    # What Enter adds: the result of the placed prompts, edged in white.
    _ai_segment_result: list[Shape]
    _ai_segment_result_key: tuple[object, ...] | None
    # What a click at the cursor would give: a mask, filled with no edge;
    # None while there is no cursor input, where an empty list is an empty
    # prediction.
    _ai_segment_preview: list[Shape] | None
    _ai_segment_preview_key: tuple[object, ...] | None
    # The AI-Segment press until its release, as (image pos, widget pos,
    # modifiers); moving past the drag distance draws a box, not a point.
    _ai_segment_press: tuple[QPointF, QPointF, Qt.KeyboardModifier] | None
    _ai_segment_dragging: bool
    # AI-Find All example boxes (labels 2, 3) and counter-examples (4, 5), and
    # the draft results they produced, not yet in shapes.
    _ai_find_all_points: np.ndarray
    _ai_find_all_point_labels: np.ndarray
    _ai_find_all_draft: list[Shape]
    # A batch waiting for its label, drawn like a draft under the dialog.
    _ai_find_all_pending: list[Shape]
    _ai_find_all_query: str
    # Proposes the draft's run again, with the settings it was shown with.
    _ai_find_all_run: (
        tuple[Callable[..., _automation.AiAssistProposal], _automation.AiOutputFormat]
        | None
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        self._epsilon = kwargs.pop("epsilon", 10.0)
        self._double_click = kwargs.pop("double_click", "close")
        if self._double_click not in [None, "close"]:
            raise ValueError(
                f"Unexpected value for double_click event: {self._double_click}"
            )
        self._num_backups = kwargs.pop("num_backups", 10)
        self._allow_out_of_bounds_points = kwargs.pop(
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
                "ai_segment": True,
                "ai_find_all": True,
            },
        )
        super().__init__(*args, **kwargs)

        self._ai_preview_timer = QtCore.QTimer(self)
        self._ai_preview_timer.setSingleShot(True)
        self._ai_preview_timer.timeout.connect(self._refresh_ai_segment_preview)
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
        self._rotation_center = np.zeros(2)
        self._rotation_initial_angle = 0.0
        self._rotation_original_points = np.empty((0, 2))
        self._scale = 1.0
        self._ai_assist_session = _automation.AiAssistSession()
        self.get_ai_find_all_model_name = lambda: ""
        self.get_ai_find_all_thresholds = lambda: (0.0, 0.5)
        self.get_ai_find_all_query = lambda: ""
        self._osam_worker = None
        self._ai_preview_job = None
        self._ai_result_job = None
        self._ai_finalize_job = None
        self._ai_progress_clock = QtCore.QElapsedTimer()
        self._ai_progress_timer = QtCore.QTimer(self)
        self._ai_progress_timer.setInterval(16)
        self._ai_progress_timer.timeout.connect(self._advance_ai_progress)
        self._clear_ai_find_all_draft()
        self._ai_find_all_pending = []
        self.ensure_ai_model_ready = lambda _model_name: False
        self._ai_inference_failed = False
        self._ai_suppress_existing_shape_matches = False
        self._ai_existing_shape_highlights = []
        self._snapping = True
        self._hovered_shape_is_selected = False
        self._painter = QtGui.QPainter()
        self._dirty_rect = QtCore.QRect()
        self._pan_anchor = None
        self._color_resolver: Callable[[str], tuple[int, int, int]] | None = None
        self._point_size: int = 8
        self._point_type: Literal["square", "round"] = "round"
        self._draft_palette = _DEFAULT_DRAFT_PALETTE
        self._palette_cache = {}
        self.shape_context_menu = QtWidgets.QMenu()
        self.canvas_context_menu = QtWidgets.QMenu()
        self.context_menu_origin = None
        self._right_click_shape = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.WheelFocus)

    @property
    def context_menu(self) -> QtWidgets.QMenu:
        return self.shape_context_menu

    def set_fill_drawing(self, *, value: bool) -> None:
        self._fill_drawing = value

    def set_show_labels(self, *, value: bool) -> None:
        self._show_labels = value

    def set_allow_out_of_bounds_points(self, *, value: bool) -> None:
        self._allow_out_of_bounds_points = value
        self.update()

    def pan_view(self, *, step: QPointF, constrain_to_center: bool = True) -> None:
        viewport = self._scroll_viewport()
        if viewport is None:
            return
        target = self._view_offset + step
        if constrain_to_center:
            # A focal zoom can leave the image away from the center. Manual
            # panning may bring it back but must not move it farther away.
            x_limit = max(
                min(self.pixmap.width() * self.scale, viewport.width()) / 2,
                abs(self._view_offset.x()),
            )
            y_limit = max(
                min(self.pixmap.height() * self.scale, viewport.height()) / 2,
                abs(self._view_offset.y()),
            )
            target = QPointF(
                max(-x_limit, min(x_limit, target.x())),
                max(-y_limit, min(y_limit, target.y())),
            )
        self._view_offset = target
        self.update()

    def reset_view_offset(self) -> None:
        self._view_offset = QPointF()
        self.update()

    def get_view_offset(self) -> QPointF:
        return QPointF(self._view_offset)

    def get_selected_shapes_bounds(self) -> QtCore.QRectF | None:
        if not self.selected_shapes:
            return None
        return _compute_shapes_bounds(shapes=self.selected_shapes)

    def set_color_resolver(
        self, *, resolver: Callable[[str], tuple[int, int, int]]
    ) -> None:
        self._color_resolver = resolver

    def set_point_size(self, *, point_size: int) -> None:
        self._point_size = point_size

    def _resolve_palette(self, *, label: str | None) -> Palette:
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

    def set_draft_palette(self, *, palette: Palette) -> None:
        self._draft_palette = palette

    def _highlight_vertex(self, *, index: int, mode: Literal["move", "near"]) -> None:
        self._highlight = VertexHighlight(index=index, mode=mode)
        self._rotation_highlight = None

    def _highlight_rotation_point(
        self, *, index: int, mode: Literal["move", "near"]
    ) -> None:
        self._rotation_highlight = VertexHighlight(index=index, mode=mode)
        self._highlight = None

    def _clear_highlight_state(self) -> None:
        self._highlight = None
        self._rotation_highlight = None

    def _render_context(self, *, shape: Shape, highlighted: bool) -> ShapeRenderContext:
        selected = shape in self.selected_shapes
        return ShapeRenderContext(
            scale=self.scale,
            palette=self._resolve_palette(label=shape.label),
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
    def scale(self) -> float:
        return self._scale

    @scale.setter
    def scale(self, value: float, /) -> None:
        self._scale = value
        # Callers read the scroll range right after assigning, so resize
        # synchronously instead of waiting for a layout pass.
        self.adjustSize()
        self.update()

    @property
    def is_drawing(self) -> bool:
        return self._current is not None

    @property
    def is_busy(self) -> bool:
        # A draft or a pending AI result, either of which Undo, Select or
        # Delete would abandon or rewrite.
        return self.is_drawing or self.is_ai_finalizing

    @property
    def is_interacting(self) -> bool:
        # From press to release, a pointer edit holds a selection, a vertex and
        # an Undo snapshot that a Shape change would reset or split. An
        # AI-Find All draft would commit on top of Shapes added under it.
        return (
            self.is_drawing
            or self._is_moving_shape
            or self._is_pointer_held
            or self.has_ai_find_all_draft
        )

    @property
    def create_mode(self) -> _CreateMode:
        return self._create_mode

    @create_mode.setter
    def create_mode(self, value: str, /) -> None:
        if not self._set_create_mode(value=value):
            return
        self._update_status(extra_messages=None)

    def _set_create_mode(self, *, value: str) -> bool:
        if value not in typing.get_args(_CreateMode):
            raise ValueError(f"Unsupported create_mode: {value}")
        new_mode = cast(_CreateMode, value)
        if new_mode == self._create_mode:
            return False
        old_mode = self._create_mode
        # Update the mode before reconciling so any signals fired from a cancel
        # observe the new mode rather than the one being left behind.
        self._create_mode = new_mode
        self._clear_ai_existing_shape_highlights()
        self._clear_ai_find_all_draft()
        self._reconcile_partial_shape_on_mode_switch(
            old_mode=old_mode, new_mode=new_mode
        )
        return True

    def _reconcile_partial_shape_on_mode_switch(
        self, *, old_mode: _CreateMode, new_mode: _CreateMode
    ) -> None:
        # Point mode finalizes on click, while AI modes carry per-point labels;
        # their seed points cannot start another shape type.
        SEED_INCOMPATIBLE_CREATE_MODES: Final[tuple[_CreateMode, ...]] = (
            "point",
            "ai_segment",
            "ai_find_all",
        )

        if self._current is None:
            return
        if not (
            len(self._current.points) == 1
            and old_mode not in SEED_INCOMPATIBLE_CREATE_MODES
            and new_mode not in SEED_INCOMPATIBLE_CREATE_MODES
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
            point=seed_point, label=seed_label
        )
        self._line = dataclasses.replace(self._line, shape_type=new_mode)
        self.update()

    def get_ai_model_name(self) -> str:
        return self._ai_assist_session.model_name

    def set_ai_model_name(self, *, model_name: str) -> None:
        if self._ai_assist_session.model_name == model_name:
            return
        self._ai_assist_session.model_name = model_name
        self._clear_ai_existing_shape_highlights()

    def _clear_ai_find_all_draft(self) -> None:
        job = self._ai_finalize_job
        if job is not None and job.prompt_kind == "example_box":
            # A pending run adds to the draft being cleared; drop it and its box.
            self._ai_finalize_job = None
            if self._current is job.draft:
                self._current = None
            self.busy_changed.emit()
        self._ai_find_all_points = np.zeros((0, 2))
        self._ai_find_all_point_labels = np.zeros((0,), dtype=np.int_)
        self._ai_find_all_draft = []
        self._ai_find_all_query = ""
        self._ai_find_all_run = None

    @property
    def has_ai_find_all_draft(self) -> bool:
        return len(self._ai_find_all_point_labels) > 0

    def _commit_ai_find_all_draft(self) -> None:
        shapes, query, run = (
            self._ai_find_all_draft,
            self._ai_find_all_query,
            self._ai_find_all_run,
        )
        if not shapes or run is None:
            self._discard_ai_find_all_draft()
            return
        # The draft stays on screen under the label dialog.
        self.ai_find_all_draft_committed.emit(
            shapes, functools.partial(self._propose_ai_find_all_batch, *run), query
        )
        self._discard_ai_find_all_draft()  # Adding Shapes already dropped it.

    def _propose_ai_find_all_batch(
        self,
        propose: Callable[..., _automation.AiAssistProposal],
        output_format: _automation.AiOutputFormat,
        label: str,
        /,
    ) -> list[Shape]:
        # Shapes with the batch's label and Output cover objects before
        # candidates suppress each other, so a covered one never hides a new one.
        shapes = propose(
            existing_shapes=[
                shape
                for shape in self.shapes
                if shape.label == label and shape.shape_type == output_format
            ]
        ).new_shapes
        _automation.assign_available_group_ids(
            shapes=shapes, existing_shapes=self.shapes
        )
        return shapes

    def set_ai_find_all_pending(self, *, shapes: list[Shape]) -> None:
        self._ai_find_all_pending = shapes
        self.update()

    def _discard_ai_find_all_draft(self) -> None:
        if not self.has_ai_find_all_draft:
            return
        self._clear_ai_find_all_draft()
        self._set_ai_existing_shape_highlights(shapes=[])
        self._update_status(extra_messages=None)

    def _refuses_example_box(self) -> bool:
        # Prompt Compatibility: refuse before any download or inference. With
        # no model chosen, the readiness check opens the Models window.
        model_name = self.get_ai_find_all_model_name()
        if (
            self.create_mode != "ai_find_all"
            or not model_name
            or _ai_models.accepts_example_boxes(model_name=model_name)
        ):
            return False
        self.example_box_unsupported.emit()
        return True

    def _get_mode_ai_model_name(self) -> str:
        if self.create_mode == "ai_find_all":
            return self.get_ai_find_all_model_name()
        return self._ai_assist_session.model_name

    def set_ai_output_format(
        self, *, output_format: _automation.AiOutputFormat
    ) -> None:
        if self._ai_assist_session.output_format == output_format:
            return
        self._ai_assist_session.output_format = output_format
        self._clear_ai_existing_shape_highlights()

    def set_ai_polygon_detail(self, *, detail: int) -> None:
        if self._ai_assist_session.polygon_detail == detail:
            return
        self._ai_assist_session.polygon_detail = detail
        self._clear_ai_existing_shape_highlights()

    def set_ai_existing_shape_suppression(self, *, enabled: bool) -> None:
        if self._ai_suppress_existing_shape_matches == enabled:
            return
        self._ai_suppress_existing_shape_matches = enabled
        self._clear_ai_existing_shape_highlights()

    def set_osam_worker(self, *, worker: _automation.OsamWorker) -> None:
        self._osam_worker = worker
        worker.finished.connect(self._on_ai_job_finished)
        worker.failed.connect(self._on_ai_job_failed)

    @property
    def ai_find_all_job(self) -> _AiJob | None:
        # The AI-Find All example-box run in flight; None when there is none.
        job = self._ai_finalize_job
        return job if job is not None and job.prompt_kind == "example_box" else None

    @property
    def is_ai_finalizing(self) -> bool:
        # Derived from the draft, so whatever drops the draft also unblocks
        # input; the job alone outlives a draft that Undo or a reset cleared.
        job = self._ai_finalize_job
        return job is not None and job.draft is self._current

    def ai_image(self) -> tuple[np.ndarray, str]:
        # The id names the image to the AI worker, which caches its embedding.
        if self._pixmap_rgb is None:
            image: np.ndarray = _utils.img_qt_to_rgb_arr(img_qt=self.pixmap.toImage())
            self._pixmap_rgb = (image, str(hash((image.shape, image.tobytes()))))
        return self._pixmap_rgb

    def _submit_ai_job(
        self,
        *,
        channel: Literal["preview", "result", "finalize"],
        prompt_kind: _automation.AiPromptKind,
        points: Sequence[QPointF],
        point_labels: Sequence[int],
        draft: _DraftShape | None = None,
        preview_key: object = None,
    ) -> None:
        assert self._osam_worker is not None
        image, image_id = self.ai_image()
        job = _AiJob(
            channel=channel,
            pixmap_key=self.pixmap.cacheKey(),
            prompt_kind=prompt_kind,
            points=np.array([[p.x(), p.y()] for p in points]),
            point_labels=np.array(point_labels),
            image_size=(
                None
                if self._allow_out_of_bounds_points
                else (image.shape[1], image.shape[0])
            ),
            draft=draft,
            preview_key=preview_key,
            query=self.get_ai_find_all_query() if prompt_kind == "example_box" else "",
        )
        # Only placed prompts ring: a preview is a guess that the next one
        # replaces. A result that replaces one still running keeps the clock,
        # so quick clicks on a slow model keep ringing.
        if channel == "finalize" or (
            channel == "result" and not self._ai_progress_timer.isActive()
        ):
            self._ai_progress_clock.start()
            self._ai_progress_timer.start()
        # Recorded first: the worker may fail the job before submit returns.
        if channel == "preview":
            self._ai_preview_job = job
        elif channel == "result":
            self._ai_result_job = job
        else:
            self._ai_finalize_job = job
            # A pending result blocks edit actions in the app; a failure
            # inside submit below emits again after this.
            self.busy_changed.emit()
        self._osam_worker.submit(
            channel=channel,
            job=job,
            request=_automation.InferenceRequest(
                model_name=self._get_mode_ai_model_name(),
                image_id=image_id,
                image=image,
                points=job.points,
                point_labels=job.point_labels,
                # A box with text finds every match; "visual" is SAM3's word
                # for "like the example" when there is no query.
                texts=(
                    [job.query or "visual"] if prompt_kind == "example_box" else None
                ),
            ),
        )

    def _ai_pending_job(self) -> _AiJob | None:
        # The run the user is waiting on: a finalize, else the result of the
        # placed prompts. Its key alone is not enough: the key only refreshes
        # while AI-Segment paints, so a tool switch would leave it current.
        if self.is_ai_finalizing:
            return self._ai_finalize_job
        job = self._ai_result_job
        if (
            job is None
            or self.mode != _CanvasMode.CREATE
            or self.create_mode != "ai_segment"
            or not self._is_current_ai_segment_job(job=job)
        ):
            return None
        return job

    def _is_current_ai_segment_job(self, *, job: _AiJob) -> bool:
        key = (
            self._ai_segment_result_key
            if job.channel == "result"
            else self._ai_segment_preview_key
        )
        return job.preview_key == key

    def _ai_progress_center(self) -> QPointF | None:
        # Where the ring for a run still going past the delay sits, in widget
        # pixels, at the last prompt placed: a box's release corner. A prompt
        # that answers sooner shows no ring, so fast runs never flicker one on
        # and off.
        DELAY_MS: Final = 400
        job = self._ai_pending_job()
        if job is None or self._ai_progress_clock.elapsed() < DELAY_MS:
            return None
        if self._current is None or not self._current.points:
            # An AI-Find All draft rerun: the job's last point.
            point = QPointF(*job.points[-1])
        else:
            point = self._current.points[-1]
        return self.transform_image_point_to_widget(point=point)

    def _ai_progress_rect(self) -> QtCore.QRect | None:
        if (center := self._ai_progress_center()) is None:
            return None
        margin = _AI_PROGRESS_RADIUS + 4
        return (
            QRectF(center, center)
            .adjusted(-margin, -margin, margin, margin)
            .toAlignedRect()
        )

    def _advance_ai_progress(self) -> None:
        if self._ai_pending_job() is None:
            self._ai_progress_timer.stop()
            return
        if (rect := self._ai_progress_rect()) is not None:
            self.update(rect)

    def _ai_proposer(
        self, *, job: _AiJob, annotations: list[Any]
    ) -> Callable[..., _automation.AiAssistProposal]:
        # Takes existing_shapes; the settings are fixed as they are now.
        thresholds = (
            self.get_ai_find_all_thresholds()
            if job.prompt_kind == "example_box"
            # AI-Segment proposals ignore the AI-Find All thresholds.
            else (0.0, 0.5)
        )
        session = copy.copy(self._ai_assist_session)
        if job.channel == "preview":
            # The guess only shows which object a click picks, so it skips
            # polygonizing; the result shows the shape Enter adds.
            session.output_format = "mask"
        return functools.partial(
            session.propose_shapes,
            score_threshold=thresholds[0],
            iou_threshold=thresholds[1],
            annotations=annotations,
            prompt_kind=job.prompt_kind,
            points=job.points,
            point_labels=job.point_labels,
            image_size=job.image_size,
        )

    def _propose_ai_shapes(
        self, *, job: _AiJob, annotations: list[Any]
    ) -> _automation.AiAssistProposal:
        proposal = self._ai_proposer(job=job, annotations=annotations)(
            # AI-Find All skips covered objects once its batch has a label.
            existing_shapes=(
                self.shapes
                if self._ai_suppress_existing_shape_matches
                and job.prompt_kind != "example_box"
                else []
            ),
        )
        _automation.assign_available_group_ids(
            shapes=proposal.new_shapes,
            existing_shapes=self.shapes,
        )
        return proposal

    def _take_ai_job(self, *, job: object) -> _AiJob | None:
        # Frees the slot the job held; returns it only if its result applies.
        if not isinstance(job, _AiJob):
            return None
        if job is self._ai_preview_job:
            self._ai_preview_job = None
        elif job is self._ai_result_job:
            self._ai_result_job = None
        elif job is self._ai_finalize_job:
            self._ai_finalize_job = None
            if self._current is not job.draft:
                return None
            if self.pixmap.cacheKey() == job.pixmap_key:
                return job
            # The pixmap changed under the draft, as a brightness change does;
            # the draft stays sent and blocks the next click, so drop it.
            self._cancel_current_shape()
            return None
        else:
            return None
        return job if self._is_current_ai_segment_job(job=job) else None

    def _on_ai_job_finished(self, job: object, annotations: object, /) -> None:
        ai_job = self._take_ai_job(job=job)
        if ai_job is None:
            return
        try:
            proposal = self._propose_ai_shapes(
                job=ai_job, annotations=cast(list, annotations)
            )
        except Exception as e:
            logger.opt(exception=e).error("AI inference failed")
            self._apply_ai_result(
                job=ai_job, proposal=None, error=f"{type(e).__name__}: {e}"
            )
        else:
            self._apply_ai_result(job=ai_job, proposal=proposal, error=None)
            if ai_job.prompt_kind == "example_box":
                self._ai_find_all_run = (
                    self._ai_proposer(job=ai_job, annotations=cast(list, annotations)),
                    self._ai_assist_session.output_format,
                )

    def _on_ai_job_failed(self, job: object, message: str, /) -> None:
        ai_job = self._take_ai_job(job=job)
        if ai_job is None:
            return
        logger.error("AI inference failed: {}", message)
        self._apply_ai_result(job=ai_job, proposal=None, error=message)

    def _apply_ai_result(
        self,
        *,
        job: _AiJob,
        proposal: _automation.AiAssistProposal | None,
        error: str | None,
    ) -> None:
        if job.channel == "finalize":
            self._finish_ai_finalize(job=job, proposal=proposal, error=error)
        else:
            self._show_ai_segment_proposal(job=job, proposal=proposal, error=error)

    def _report_inference_failure(self, *, error: str) -> None:
        self._ai_inference_failed = True
        self.inference_failed.emit(error)

    def backup_shapes(self) -> None:
        self.shape_backups.append([s.copy() for s in self.shapes])
        # The draft was suppressed against the Shapes before this change.
        self._discard_ai_find_all_draft()

    @property
    def can_restore_shape(self) -> bool:
        MIN_SHAPE_BACKUPS_FOR_UNDO: Final = 2

        return len(self.shape_backups) >= MIN_SHAPE_BACKUPS_FOR_UNDO

    def restore_last_shape(self) -> None:
        if not self.can_restore_shape:
            return
        # Label rebuilding completes [..., A, B] -> [...] -> [..., A].
        self.shape_backups.pop()  # discard current state
        self.shapes = self.shape_backups.pop()
        self._discard_ai_find_all_draft()
        self.selected_shapes.clear()
        self._drag_anchor = None
        self.update()

    @override
    def enterEvent(self, _a0: QtCore.QEvent, /) -> None:
        self._apply_cursor(role=self._cursor)
        self._update_status(extra_messages=None)

    @override
    def leaveEvent(self, _a0: QtCore.QEvent, /) -> None:
        self._set_highlight(
            hovered_shape=None,
            hovered_edge=None,
            hovered_vertex=None,
            hovered_rotation=None,
        )
        self._release_cursor()
        self._update_status(extra_messages=None)

    @override
    def focusOutEvent(self, _a0: QtGui.QFocusEvent, /) -> None:
        self._drag_anchor = None
        self._release_cursor()
        self._update_status(extra_messages=None)

    def set_editing(
        self, *, value: bool = True, create_mode: str | None = None
    ) -> None:
        if create_mode is not None:
            self._set_create_mode(value=create_mode)
        new_mode = _CanvasMode.EDIT if value else _CanvasMode.CREATE
        # Any tool pick re-arms it, so re-clicking the active tool shows it again.
        self._ai_prompt_hint_due = not value
        self.update()  # Also clears the crosshair on leaving CREATE.
        if new_mode is not self.mode:
            self._clear_ai_existing_shape_highlights()
            self._clear_ai_find_all_draft()
        self.mode = new_mode
        if self.mode == _CanvasMode.CREATE:
            self._set_highlight(
                hovered_shape=None,
                hovered_edge=None,
                hovered_vertex=None,
                hovered_rotation=None,
            )
            self.deselect_shape()
        self._update_status(extra_messages=None)

    def _set_highlight(
        self,
        *,
        hovered_shape: Shape | None,
        hovered_edge: int | None,
        hovered_vertex: int | None,
        hovered_rotation: int | None,
    ) -> None:
        previous_shape: Shape | None = self.hovered_shape
        if previous_shape is not None:
            self._clear_highlight_state()
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
        if previous_shape is not None or hovered_shape is not None:
            self.update()

    def _is_vertex_selected(self) -> bool:
        return self._hovered_vertex is not None

    def _is_edge_selected(self) -> bool:
        return self._hovered_edge is not None

    def _is_rotation_point_selected(self) -> bool:
        return self._hovered_rotation is not None

    def _update_status(self, *, extra_messages: list[str] | None) -> None:
        messages: list[str] = []
        if self.mode == _CanvasMode.CREATE:
            messages.append(self._get_create_mode_name())
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

    def _get_create_mode_name(self) -> str:
        # Reuse the draw actions' names and their translations from MainWindow.
        translate = QtCore.QCoreApplication.translate
        match self.create_mode:
            case "polygon":
                return translate("MainWindow", "Polygon")
            case "rectangle":
                return translate("MainWindow", "Rectangle")
            case "oriented_rectangle":
                return translate("MainWindow", "Oriented Rectangle")
            case "circle":
                return translate("MainWindow", "Circle")
            case "line":
                return translate("MainWindow", "Line")
            case "point":
                return translate("MainWindow", "Point")
            case "linestrip":
                return translate("MainWindow", "LineStrip")
            case "ai_segment":
                return translate("MainWindow", "AI-Segment")
            case "ai_find_all":
                return translate("MainWindow", "AI-Find All")

    def _get_create_mode_message(self) -> str:
        assert self.mode == _CanvasMode.CREATE
        is_new: bool = self._current is None
        if self.create_mode == "ai_segment":
            return self.tr(
                "Click points to include, hold %s and click to exclude, or drag a"
                " box. Hold %s and click to finish."
            ) % (
                _utils.modifier_text(modifiers=Qt.KeyboardModifier.ShiftModifier),
                _utils.modifier_text(modifiers=Qt.KeyboardModifier.ControlModifier),
            )
        if self.create_mode == "ai_find_all":
            if is_new and self.has_ai_find_all_draft:
                return self.tr(
                    "Enter adds the results, Esc discards them."
                    " Hold %s and draw a box to exclude objects like it."
                ) % _utils.modifier_text(modifiers=Qt.KeyboardModifier.ShiftModifier)
            if is_new:
                return self.tr(
                    "Type what to find in AI-Find All, or click the first corner"
                    " of a box around one example"
                )
            assert self._current is not None
            if self._current.point_labels[0] == 0:
                return self.tr(
                    "Click the opposite corner to exclude objects like this one"
                )
            return self.tr(
                "Click the opposite corner to find every object like this one"
            )
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
                    "Click the next point, or hold %s and click to finish the LineStrip"
                ) % _utils.modifier_text(modifiers=Qt.KeyboardModifier.ControlModifier)
        if self.create_mode == "circle":
            if is_new:
                return self.tr("Click center point for circle")
            else:
                return self.tr("Click point on circumference for circle")
        if self.create_mode == "rectangle":
            if is_new:
                return self.tr("Click first corner for rectangle")
            else:
                return self.tr("Choose the other corner. Hold Shift for a square.")
        if self.create_mode == "oriented_rectangle":
            if is_new:
                return self.tr("Click first corner for oriented rectangle")
            assert self._current is not None
            if len(self._current.points) == 1:
                return self.tr("Click second corner to set orientation")
            return self.tr("Click third corner to close oriented rectangle")
        return self.tr("Click to add point")

    @override
    def mouseMoveEvent(self, a0: QtGui.QMouseEvent, /) -> None:
        try:
            pos = self.transform_widget_point_to_image(point=a0.position())
        except AttributeError:
            return
        self.mouse_moved.emit(pos)
        if self.is_ai_finalizing:
            return
        self._prev_move_point = pos
        self._dispatch_pointer_move(pos=pos, event=a0)

    def _dispatch_pointer_move(self, *, pos: QPointF, event: QtGui.QMouseEvent) -> None:
        if self._pan_anchor is not None:
            self._advance_pan(event=event)
            return
        if self.mode == _CanvasMode.CREATE:
            self._track_drawing_cursor(pos=pos, event=event)
            return
        buttons = event.buttons()
        if buttons & Qt.MouseButton.RightButton:
            # Freeze the hover state while the right button is down so the
            # context menu opened on release targets the pressed shape.
            return
        if buttons & Qt.MouseButton.LeftButton:
            self._continue_left_button_drag(pos=pos, event=event)
            return
        self._refresh_hover_state(pos=pos)

    def _advance_pan(self, *, event: QtGui.QMouseEvent) -> None:
        assert self._pan_anchor is not None
        # Use screen coordinates so the anchor does not drift when our own
        # pan emit shifts the canvas widget under the scroll area — a
        # widget-local frame would oscillate and cause juggling.
        cursor: QPointF = QPointF(self.mapToGlobal(event.position().toPoint()))
        step: QPointF = cursor - self._pan_anchor
        self._pan_anchor = cursor
        self.pan_request.emit(QPoint(int(step.x()), int(step.y())))

    def _track_drawing_cursor(self, *, pos: QPointF, event: QtGui.QMouseEvent) -> None:
        if self.create_mode == "ai_segment":
            self._track_ai_segment_cursor(pos=pos, event=event)
            return
        desired_line_shape_type = _CREATE_MODE_TO_SHAPE_TYPE[self.create_mode]
        if self._line.shape_type != desired_line_shape_type:
            self._line = dataclasses.replace(
                self._line, shape_type=desired_line_shape_type
            )
        self._apply_cursor(role=CursorRole.DRAW)
        if self._current is None:
            self.update()
            self._update_status(extra_messages=None)
            return
        is_shift_pressed = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        pos = self._project_drawing_pos_into_image(pos=pos)
        self._update_drawing_line(pos=pos, is_shift_pressed=is_shift_pressed)
        assert len(self._line.points) == len(self._line.point_labels)
        self.update()
        self._update_status(extra_messages=None)

    def _track_ai_segment_cursor(
        self, *, pos: QPointF, event: QtGui.QMouseEvent
    ) -> None:
        self._apply_cursor(role=CursorRole.DRAW)
        if not event.buttons() & Qt.MouseButton.LeftButton:
            # The release went elsewhere, e.g. while a finalize blocked input.
            self._ai_segment_press = None
            self._ai_segment_dragging = False
        if self._ai_segment_press is None:
            if self._should_constrain_to_pixmap(point=pos):
                pos = _clamp_into_image(point=pos, image_size=self.pixmap.size())
            self._line = _ai_segment_point(pos=pos, modifiers=event.modifiers())
        else:
            self._drag_ai_segment(pos=pos, widget_pos=event.position())
        self.update()
        self._update_status(extra_messages=None)

    def _drag_ai_segment(self, *, pos: QPointF, widget_pos: QPointF) -> None:
        press = self._ai_segment_press
        assert press is not None
        if not self._ai_segment_dragging:
            self._ai_segment_dragging = (
                widget_pos - press[1]
            ).manhattanLength() >= QtWidgets.QApplication.startDragDistance()
        if not self._ai_segment_dragging:
            return
        if self._should_constrain_to_pixmap(point=pos):
            pos = _clamp_into_image(point=pos, image_size=self.pixmap.size())
        self._line = _DraftShape(
            shape_type="points", points=(press[0], pos), point_labels=_AI_BOX_LABELS
        )

    def _project_drawing_pos_into_image(self, *, pos: QPointF) -> QPointF:
        current = self._current
        assert current is not None
        if (
            self.create_mode == "oriented_rectangle"
            and len(current.points) == ORIENTED_RECTANGLE_POINT_COUNT
        ):
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
        if self._should_constrain_to_pixmap(point=pos):
            return _compute_intersection_edges_image(
                p1=current.points[-1], p2=pos, image_size=self.pixmap.size()
            )
        if not self._cursor_should_snap_to_polygon_origin(pos=pos):
            return pos
        self._apply_cursor(role=CursorRole.HANDLE)
        self._highlight_vertex(index=0, mode="near")
        return current.points[0]

    def _cursor_should_snap_to_polygon_origin(self, *, pos: QPointF) -> bool:
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

    def _refresh_hover_state(self, *, pos: QPointF) -> None:
        status_messages: list[str] = []
        self._highlight_hover_shape(pos=pos, status_messages=status_messages)
        self.vertex_selected.emit(self._hovered_vertex is not None)
        self.edge_selected.emit(self._hovered_edge is not None)
        self._update_status(extra_messages=status_messages)

    def _update_drawing_line(self, *, pos: QPointF, is_shift_pressed: bool) -> QPointF:
        current = self._current
        assert current is not None
        mode = self.create_mode
        if mode in POLYLINE_SHAPE_TYPES:
            self._line = dataclasses.replace(
                self._line, points=(current.points[-1], pos), point_labels=(1, 1)
            )
        elif mode in ("rectangle", "ai_find_all"):
            # In AI-Find All, Shift marks a counter-example instead of a square.
            if is_shift_pressed and mode != "ai_find_all":
                pos = _snap_cursor_pos_for_square(
                    pos=pos, opposite_vertex=current.points[0]
                )
                self._prev_move_point = pos
            label = current.point_labels[0] if mode == "ai_find_all" else 1
            self._line = dataclasses.replace(
                self._line,
                points=(current.points[0], pos),
                point_labels=(label, label),
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

    def _continue_left_button_drag(
        self, *, pos: QPointF, event: QtGui.QMouseEvent
    ) -> None:
        is_shift_pressed = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if self.hovered_shape is not None and self.hovered_shape.locked:
            # Hovering already hides a locked shape's handles; never drag one.
            self._drag_selected_shapes(pos=pos)
            return
        if self._is_vertex_selected():
            self._drag_hovered_vertex(pos=pos, is_shift_pressed=is_shift_pressed)
            return
        if self._is_rotation_point_selected():
            self._drag_hovered_rotation_point(pos=pos)
            return
        self._drag_selected_shapes(pos=pos)

    def _drag_hovered_vertex(self, *, pos: QPointF, is_shift_pressed: bool) -> None:
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

    def _drag_hovered_rotation_point(self, *, pos: QPointF) -> None:
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

    def _movable_selected_shapes(self) -> list[Shape]:
        return [shape for shape in self.selected_shapes if not shape.locked]

    def _drag_selected_shapes(self, *, pos: QPointF) -> None:
        shapes = self._movable_selected_shapes()
        if not shapes:
            return
        self._apply_cursor(role=CursorRole.MOVE)
        self._drag_shapes(shapes=shapes, cursor=pos, constrain_cursor=True)
        self.update()
        self._is_moving_shape = True

    def _highlight_hover_shape(
        self, *, pos: QPointF, status_messages: list[str]
    ) -> None:
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
            self._set_highlight(
                hovered_shape=None,
                hovered_edge=None,
                hovered_vertex=None,
                hovered_rotation=None,
            )
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
            self._apply_cursor(role=CursorRole.HANDLE)
            status_messages.append(self.tr("Click & drag to move point"))
            if target.shape.can_remove_point():
                status_messages.append(
                    self.tr("Hold %s and click to delete the point")
                    % _utils.modifier_text(
                        modifiers=Qt.KeyboardModifier.AltModifier
                        | Qt.KeyboardModifier.ShiftModifier
                    )
                )
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
            self._apply_cursor(role=CursorRole.HANDLE)
            status_messages.append(self.tr("Click & drag to rotate the shape"))
            return

        if target.kind is HitKind.EDGE:
            assert target.index is not None
            self._set_highlight(
                hovered_shape=target.shape,
                hovered_edge=target.index,
                hovered_vertex=None,
                hovered_rotation=None,
            )
            self._apply_cursor(role=CursorRole.HANDLE)
            status_messages.append(
                self.tr("Hold %s and click to add a point on the edge")
                % _utils.modifier_text(modifiers=Qt.KeyboardModifier.AltModifier)
            )
            return

        if target.kind is HitKind.BODY:
            self._set_highlight(
                hovered_shape=target.shape,
                hovered_edge=None,
                hovered_vertex=None,
                hovered_rotation=None,
            )
            if target.shape.locked:
                status_messages.append(self.tr("Shape is locked"))
                self._release_cursor()
                return
            status_messages.append(self.tr("Click & drag to move shape"))
            self._apply_cursor(role=CursorRole.GRAB)
            return

        typing.assert_never(target.kind)

    def add_point_to_edge(self) -> None:
        shape = self._last_hovered_shape
        index = self._last_hovered_edge
        point = self._prev_move_point
        if shape is None or index is None or point is None or shape.locked:
            return
        shape.insert_point(i=index, point=(point.x(), point.y()))
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
        if (
            shape is None
            or index is None
            or shape.locked
            or not shape.can_remove_point()
        ):
            return False
        shape.remove_point(i=index)
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

    @override
    def mousePressEvent(self, a0: QtGui.QMouseEvent, /) -> None:
        self._is_pointer_held = a0.buttons() != Qt.MouseButton.NoButton
        if self.is_ai_finalizing:
            return
        pos: QPointF = self.transform_widget_point_to_image(point=a0.position())
        self._dispatch_pointer_press(pos=pos, event=a0)
        self._update_status(extra_messages=None)

    def _dispatch_pointer_press(
        self, *, pos: QPointF, event: QtGui.QMouseEvent
    ) -> None:
        self._clear_ai_existing_shape_highlights()
        button = event.button()
        if button == Qt.MouseButton.LeftButton:
            self._press_left(pos=pos, event=event)
            return
        if button == Qt.MouseButton.RightButton and self.mode == _CanvasMode.EDIT:
            self._press_right(pos=pos)
            return
        if button == Qt.MouseButton.MiddleButton and (
            self._is_image_overflowing_viewport() or not self._view_offset.isNull()
        ):
            self._begin_pan(event=event)

    def _press_left(self, *, pos: QPointF, event: QtGui.QMouseEvent) -> None:
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
        *,
        pos: QPointF,
        event: QtGui.QMouseEvent,
        is_shift_pressed: bool,
    ) -> None:
        if self._current is None and self._should_constrain_to_pixmap(point=pos):
            return
        self._ai_prompt_hint_due = False
        if self.create_mode == "ai_segment":
            self._press_ai_segment(pos=pos, event=event)
            return
        if self._current is not None:
            self._extend_current_shape(current=self._current, event=event)
            return
        self._start_new_shape(pos=pos, is_shift_pressed=is_shift_pressed)

    def _extend_current_shape(
        self, *, current: _DraftShape, event: QtGui.QMouseEvent
    ) -> None:
        mode = self.create_mode
        if mode in ("polygon", "linestrip"):
            self._commit_preview_vertex(current=current, event=event)
        elif mode == "oriented_rectangle":
            if len(current.points) == ORIENTED_RECTANGLE_POINT_COUNT:
                self._finalize()
            else:
                assert len(current.points) == 1
                self._lock_oriented_rectangle_first_edge(current=current)
        else:
            assert mode in ("rectangle", "circle", "line", "ai_find_all")
            assert len(current.points) == 1
            self._current = dataclasses.replace(current, points=self._line.points)
            self._finalize()

    def _commit_preview_vertex(
        self, *, current: _DraftShape, event: QtGui.QMouseEvent
    ) -> None:
        # The preview segment runs from the last committed vertex to the cursor.
        # A click promotes its cursor end into the draft, and the next preview
        # segment collapses onto that vertex until the cursor moves again.
        vertex = self._line.points[1]
        label = self._line.point_labels[1]
        current = current.add_point(
            point=vertex, label=label, autoclose=self.create_mode == "polygon"
        )
        self._current = current
        if current.closed or self._is_final_open_path_click(event=event):
            self._finalize()
            return
        self._line = dataclasses.replace(
            self._line, points=(vertex, vertex), point_labels=(label, label)
        )

    def _press_ai_segment(self, *, pos: QPointF, event: QtGui.QMouseEvent) -> None:
        if self._should_constrain_to_pixmap(point=pos):
            return
        if self._current is None and not self.ensure_ai_model_ready(
            self._get_mode_ai_model_name()
        ):
            return
        modifiers = event.modifiers()
        self._ai_segment_press = (pos, event.position(), modifiers)
        self._ai_segment_dragging = False
        # A release before the drag distance places this point.
        self._line = _ai_segment_point(pos=pos, modifiers=modifiers)

    def _release_ai_segment(self, *, event: QtGui.QMouseEvent) -> None:
        press = self._ai_segment_press
        if press is None:
            return
        # The release can land past the last move event.
        self._drag_ai_segment(
            pos=self.transform_widget_point_to_image(point=event.position()),
            widget_pos=event.position(),
        )
        self._ai_segment_press = None
        self._ai_segment_dragging = False
        draft = _with_ai_segment_input(
            draft=self._current or _DraftShape(shape_type="points"), line=self._line
        )
        self._line = _DraftShape(shape_type="points")
        if draft is None:  # A box with no area.
            self.update()
            return
        self._current = draft
        self.busy_changed.emit()
        if press[2] & Qt.KeyboardModifier.ControlModifier:
            self._finalize()
            return
        self.update()

    def _release_ai_find_all(self, *, event: QtGui.QMouseEvent) -> None:
        current = self._current
        if current is None:
            return
        pos = self.transform_widget_point_to_image(point=event.position())
        # The release can land past the last move event.
        self._track_drawing_cursor(pos=pos, event=event)
        # Measure the pointer, not the corner clamped into the image.
        dragged = (pos - current.points[0]) * self.scale
        if dragged.manhattanLength() < QtWidgets.QApplication.startDragDistance():
            return  # A click: the next click places the opposite corner.
        self._extend_current_shape(current=current, event=event)

    def _is_final_open_path_click(self, *, event: QtGui.QMouseEvent) -> bool:
        # A polygon ends by returning to its first vertex; the modes with no
        # natural end let Ctrl mark the last click instead.
        if self.create_mode == "polygon":
            return False
        return bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)

    def _lock_oriented_rectangle_first_edge(self, *, current: _DraftShape) -> None:
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

    def _unlock_oriented_rectangle_first_edge(self, *, current: _DraftShape) -> None:
        anchor = current.points[0]
        self._current = dataclasses.replace(
            current, points=(anchor,), point_labels=(current.point_labels[0],)
        )
        self._line = dataclasses.replace(self._line, points=(anchor, anchor))

    def _start_new_shape(self, *, pos: QPointF, is_shift_pressed: bool) -> None:
        mode = self.create_mode
        if mode == "ai_find_all":
            if self._refuses_example_box():
                return
            if not self.ensure_ai_model_ready(self._get_mode_ai_model_name()):
                return

        self._current = _DraftShape(
            shape_type=_CREATE_MODE_TO_SHAPE_TYPE[mode]
        ).add_point(point=pos, label=0 if is_shift_pressed else 1)

        if mode == "point":
            self._finalize()
            return
        self._line = dataclasses.replace(
            self._line,
            points=(pos, pos),
            point_labels=(
                (0, 0) if mode == "ai_find_all" and is_shift_pressed else (1, 1)
            ),
        )
        self.busy_changed.emit()
        self.update()

    def _press_left_while_editing(
        self, *, pos: QPointF, event: QtGui.QMouseEvent
    ) -> None:
        modifiers = event.modifiers()
        if self._maybe_modify_polygon_topology(modifiers=modifiers):
            # remove_selected_point already repainted; just consume the press.
            return
        if self._is_rotation_point_selected():
            self._capture_rotation_anchors()
        self._select_shape_point(
            point=pos,
            multiple_selection_mode=modifiers == Qt.KeyboardModifier.ControlModifier,
        )
        self._prev_point = pos
        self.update()

    def _maybe_modify_polygon_topology(self, *, modifiers: Qt.KeyboardModifier) -> bool:
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

    def _press_right(self, *, pos: QPointF) -> None:
        shape = self._find_pointed_shape(point=pos)
        if shape is None:
            self._right_click_shape = None
        else:
            if shape not in self.selected_shapes:
                self.select_shapes(shapes=[shape])
            self._right_click_shape = shape
        self._prev_point = pos

    def _begin_pan(self, *, event: QtGui.QMouseEvent) -> None:
        self._apply_cursor(role=CursorRole.GRAB)
        self._pan_anchor = QPointF(self.mapToGlobal(event.position().toPoint()))

    @override
    def mouseReleaseEvent(self, a0: QtGui.QMouseEvent, /) -> None:
        self._is_pointer_held = a0.buttons() != Qt.MouseButton.NoButton
        if self.is_ai_finalizing:
            return
        self._dispatch_pointer_release(event=a0)
        self._commit_pending_shape_move()
        self._drag_anchor = None
        self._update_status(extra_messages=None)

    def _dispatch_pointer_release(self, *, event: QtGui.QMouseEvent) -> None:
        button = event.button()
        if button == Qt.MouseButton.RightButton:
            self._release_right(event=event)
            return
        if button == Qt.MouseButton.LeftButton:
            if self.mode == _CanvasMode.CREATE:
                if self.create_mode == "ai_segment":
                    self._release_ai_segment(event=event)
                elif self.create_mode == "ai_find_all":
                    self._release_ai_find_all(event=event)
            self._release_left()
            return
        if button == Qt.MouseButton.MiddleButton:
            self._finish_pan()

    def _release_right(self, *, event: QtGui.QMouseEvent) -> None:
        self._release_cursor()
        self.context_menu_origin = self.mapToGlobal(event.position().toPoint())
        pos: QPointF = self.transform_widget_point_to_image(point=event.position())
        shape = self._right_click_shape or self._find_pointed_shape(point=pos)
        self._right_click_shape = None
        menu = (
            self.shape_context_menu
            if (shape is not None and self.mode == _CanvasMode.EDIT)
            else self.canvas_context_menu
        )
        try:
            menu.exec(self.context_menu_origin)  # ty: ignore[invalid-argument-type]
        finally:
            self.context_menu_origin = None

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
        scroll_area = self._find_scroll_area()
        return scroll_area.viewport() if scroll_area is not None else None

    def _find_scroll_area(self) -> QtWidgets.QAbstractScrollArea | None:
        # Parentage can include viewport chrome, so do not assume the direct
        # parent owns scrolling.
        node: QtWidgets.QWidget | None = self.parentWidget()
        while node is not None:
            if isinstance(node, QtWidgets.QAbstractScrollArea):
                return node
            node = node.parentWidget()
        return None

    def _commit_pending_shape_move(self) -> None:
        if not self._is_moving_shape:
            return
        self._is_moving_shape = False
        # Compare every shape: the hovered shape can differ from the dragged
        # one, e.g. a point shape inside a box leaves the box hovered (#2844).
        backup = self.shape_backups[-1]
        if len(backup) != len(self.shapes) or any(
            not np.array_equal(before.points, after.points)
            for before, after in zip(backup, self.shapes)
        ):
            self.backup_shapes()
            self.shape_moved.emit()

    def _can_close_shape(self) -> bool:
        if self.mode != _CanvasMode.CREATE:
            return False
        if self._current is None:
            return False
        if self.create_mode == "oriented_rectangle":
            # Points 2 and 3 are seeded as duplicates of points 1 and 0 after
            # the first edge is locked; mouse movement reprojects them. Treat
            # the shape as closeable only once the third corner has moved.
            return (
                len(self._current.points) == ORIENTED_RECTANGLE_POINT_COUNT
                and self._current.points[2] != self._current.points[1]
            )
        minimum_points = {
            "ai_segment": 0,
            "linestrip": MIN_LINESTRIP_POINT_COUNT,
        }.get(self.create_mode, MIN_POLYGON_POINT_COUNT)
        return len(self._current.points) >= minimum_points

    @override
    def mouseDoubleClickEvent(self, a0: QtGui.QMouseEvent, /) -> None:
        if self.is_ai_finalizing:
            return
        if self.mode == _CanvasMode.CREATE:
            if self._double_click == "close" and self._can_close_shape():
                self._finalize()
            return
        if a0.button() != Qt.MouseButton.LeftButton:
            return
        pos: QPointF = self.transform_widget_point_to_image(point=a0.position())
        shape = self._find_pointed_shape(point=pos)
        if shape is None:
            return
        self.select_shapes(shapes=[shape])
        # The first click may have armed deselect-on-release for this shape.
        self._hovered_shape_is_selected = False
        self.shape_double_clicked.emit()

    def select_shapes(self, *, shapes: list[Shape]) -> None:
        self.selected_shapes = shapes
        self.selection_changed.emit(shapes)
        self.update()

    def select_neighbor_shape(self, *, key: Qt.Key) -> None:
        # Picks the nearest visible shape within the 90-degree cone opening in
        # the arrow key's direction, and leaves the selection as it is when
        # none lies there. With nothing selected, the shape closest to the
        # image's top-left corner is selected instead.
        candidates = [
            shape
            for shape in self.shapes
            if shape.visible and shape not in self.selected_shapes
        ]
        if not self.selected_shapes:
            if candidates:
                self.select_shapes(
                    shapes=[
                        min(
                            candidates,
                            key=lambda s: _shape_bounds(shape=s)
                            .center()
                            .manhattanLength(),
                        )
                    ]
                )
            return
        origin = _compute_shapes_bounds(shapes=self.selected_shapes).center()
        vector = _ARROW_KEY_TO_DIRECTION[key]
        scored: list[tuple[float, Shape]] = []
        for shape in candidates:
            delta = _shape_bounds(shape=shape).center() - origin
            along = delta.x() * vector.x() + delta.y() * vector.y()
            sideways = abs(delta.x() * vector.y() - delta.y() * vector.x())
            # Only the 90-degree cone counts as "that way", and sideways drift
            # costs double so a same-row neighbor beats a nearer diagonal one.
            if 0 < along and sideways <= along:
                scored.append((along + 2 * sideways, shape))
        if scored:
            self.select_shapes(shapes=[min(scored, key=lambda t: t[0])[1]])

    def _select_shape_point(
        self, *, point: QPointF, multiple_selection_mode: bool
    ) -> None:
        if self._hovered_vertex is not None:
            assert self.hovered_shape is not None
            self._highlight_vertex(index=self._hovered_vertex, mode="move")
            if self.deselect_shape():
                self.update()
            return

        clicked_shape = self._find_pointed_shape(point=point)
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
        self._record_drag_anchor(shapes=self._movable_selected_shapes(), click=point)

    def _find_pointed_shape(self, *, point: QPointF) -> Shape | None:
        # A hovered vertex or rotation handle acts on its own shape, so it wins
        # over a body lying under it.
        if self._hovered_vertex is not None or self._hovered_rotation is not None:
            return self.hovered_shape
        return _canvas_interaction.find_shape_at(
            shapes=self.shapes,
            point=np.array([point.x(), point.y()]),
            scale=self.scale,
            point_size=self._point_size,
            epsilon=self._epsilon,
        )

    def _record_drag_anchor(self, *, shapes: list[Shape], click: QPointF) -> None:
        if not shapes:
            self._drag_anchor = None
            return
        bounds = _compute_shapes_bounds(shapes=shapes)
        sources = {shape: shape.points.copy() for shape in shapes}
        for source in sources.values():
            source.setflags(write=False)
        self._drag_anchor = _DragAnchor(
            rel_tl=bounds.topLeft() - click,
            bounds=bounds,
            origin=QPointF(click),
            last_cursor=QPointF(click),
            sources=sources,
            limits=(self.pixmap.size(), self._allow_out_of_bounds_points),
        )

    def _bounded_move_vertex(
        self,
        *,
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

        if self._should_constrain_to_pixmap(point=pos):
            pos = _compute_intersection_edges_image(
                p1=QPointF(*shape.points[vertex_index]),
                p2=pos,
                image_size=self.pixmap.size(),
            )

        if is_shift_pressed and shape.shape_type == "rectangle":
            pos = _snap_cursor_pos_for_square(
                pos=pos, opposite_vertex=QPointF(*shape.points[1 - vertex_index])
            )

        shape.move_vertex(i=vertex_index, pos=(pos.x(), pos.y()))

    def _bounded_move_oriented_rectangle_vertex(
        self, *, shape: Shape, vertex_index: int, pos: QPointF
    ) -> None:
        assert len(shape.points) == ORIENTED_RECTANGLE_POINT_COUNT
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

    def _drag_shapes(
        self, *, shapes: list[Shape], cursor: QPointF, constrain_cursor: bool
    ) -> None:
        if constrain_cursor and self._should_constrain_to_pixmap(point=cursor):
            return

        current_bounds = _compute_shapes_bounds(shapes=shapes)
        if (
            self._drag_anchor is None
            or self._drag_anchor.limits
            != (self.pixmap.size(), self._allow_out_of_bounds_points)
            or not self._drag_anchor.is_current(shapes=shapes, cursor=self._prev_point)
        ):
            self._record_drag_anchor(shapes=shapes, click=self._prev_point)
        anchor = self._drag_anchor
        assert anchor is not None
        # Re-clamping an identical request can introduce a rounding-only move.
        if anchor.requested_cursor == (cursor.x(), cursor.y()):
            return
        rel_tl, bounds = anchor.rel_tl, anchor.bounds

        target = cursor + rel_tl
        if not self._allow_out_of_bounds_points:
            pw = float(self.pixmap.width())
            ph = float(self.pixmap.height())
            min_x = min(0.0, pw - bounds.width(), current_bounds.left())
            max_x = max(0.0, pw - bounds.width(), current_bounds.left())
            min_y = min(0.0, ph - bounds.height(), current_bounds.top())
            max_y = max(0.0, ph - bounds.height(), current_bounds.top())
            target.setX(min(max(target.x(), min_x), max_x))
            target.setY(min(max(target.y(), min_y), max_y))

        self._prev_point = target - rel_tl
        anchor.place(cursor=self._prev_point)
        anchor.requested_cursor = (cursor.x(), cursor.y())

    def deselect_shape(self) -> bool:
        if not self.selected_shapes:
            return False
        self.selection_changed.emit([])
        self._hovered_shape_is_selected = False
        return True

    def _forget_hover(self, *, shapes: list[Shape]) -> None:
        # A removed or hidden Shape must not stay a hover or edit target.
        if self.hovered_shape in shapes:
            self._set_highlight(
                hovered_shape=None,
                hovered_edge=None,
                hovered_vertex=None,
                hovered_rotation=None,
            )
        if self._last_hovered_shape in shapes:
            self._last_hovered_shape = None
            self._last_hovered_vertex = None
            self._last_hovered_edge = None

    def delete_selected(self) -> list[Shape]:
        removed = self._movable_selected_shapes()
        if not removed:
            return []
        self.shapes = [s for s in self.shapes if s not in removed]
        self._forget_hover(shapes=removed)
        self.backup_shapes()
        self.selected_shapes = [s for s in self.selected_shapes if s.locked]
        self._set_ai_existing_shape_highlights(shapes=[])
        self.update()
        return removed

    def delete_shape(self, *, shape: Shape) -> None:
        if shape in self.selected_shapes:
            self.selected_shapes.remove(shape)
        self.shapes = [s for s in self.shapes if s is not shape]
        self._forget_hover(shapes=[shape])
        self.backup_shapes()
        self._set_ai_existing_shape_highlights(shapes=[])
        self.update()

    @override
    def paintEvent(self, a0: QtGui.QPaintEvent, /) -> None:
        if self.pixmap.isNull():
            super().paintEvent(a0)
            return
        # The ring repaints only its own rect each frame; culling shapes
        # outside the dirty rect keeps that cheap on a busy image.
        self._dirty_rect = a0.rect()
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

    def _setup_world_transform(self, *, painter: QtGui.QPainter) -> None:
        for hint in (
            QtGui.QPainter.RenderHint.Antialiasing,
            QtGui.QPainter.RenderHint.SmoothPixmapTransform,
        ):
            painter.setRenderHint(hint)
        painter.translate(self._compute_image_origin_offset(area=None) * self.scale)

    def _render_layers(self) -> tuple[Callable[[QtGui.QPainter], None], ...]:
        # Order is z-order, back-to-front.
        return (
            self._draw_pixmap_layer,
            self._draw_crosshair_layer,
            self._draw_committed_shapes_layer,
            self._draw_active_shape_layer,
            self._draw_preview_overlay_layer,
            self._draw_ai_find_all_layer,
            self._draw_ai_existing_match_layer,
            self._draw_ai_progress_layer,
            self._draw_ai_hint_layer,
        )

    def _draw_ai_progress_layer(self, painter: QtGui.QPainter, /) -> None:
        if (center := self._ai_progress_center()) is None:
            return
        # A white arc on a dark translucent track reads on light and dark
        # images alike, whatever the system accent color; one calm linear
        # turn a second, like a native spinner.
        radius = _AI_PROGRESS_RADIUS
        painter.save()
        painter.resetTransform()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QtGui.QPen(QtGui.QColor(0, 0, 0, 140), 5))
        painter.drawEllipse(center, radius, radius)
        arc = QtGui.QPen(QtGui.QColor(255, 255, 255), 3)
        arc.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(arc)
        TURN_MS: Final = 1000
        turn = self._ai_progress_clock.elapsed() % TURN_MS
        painter.drawArc(
            QRectF(center, center).adjusted(-radius, -radius, radius, radius),
            -turn * 360 * 16 // TURN_MS,
            90 * 16,
        )
        painter.restore()

    def _draw_ai_hint_layer(self, painter: QtGui.QPainter, /) -> None:
        if (hint := self._ai_suggestion_hint()) is not None:
            (top_left, bottom_right), rows = hint
            anchor = QRectF(
                self.transform_image_point_to_widget(point=top_left),
                self.transform_image_point_to_widget(point=bottom_right),
            )
        elif (prompt_rows := self._ai_prompt_hint()) is not None:
            rows, anchor = prompt_rows, None
        else:
            return
        bounds = QRectF(self.visibleRegion().boundingRect() or self.rect())
        if anchor is None:
            # No prompt to sit by yet: an empty anchor on the view's bottom
            # edge, so the chip flips above it to the bottom center.
            anchor = QRectF(bounds.center().x(), bounds.bottom(), 0, 0)
        font = self.font()
        rect, lines = place_hint_chip(
            rows=rows, font=font, anchor=anchor, bounds=bounds
        )
        if not rect.toAlignedRect().intersects(self._dirty_rect):
            return  # A ring frame elsewhere.
        painter.save()
        painter.resetTransform()
        paint_hint_chip(painter=painter, lines=lines, font=font, rect=rect)
        painter.restore()

    @override
    def moveEvent(self, event: QtGui.QMoveEvent, /) -> None:
        # Scrolling moves the canvas and repaints only the exposed strip, but
        # the hint is placed within the visible part, so it moves too.
        super().moveEvent(event)
        if self._ai_suggestion_hint() or self._ai_prompt_hint():
            self.update()

    def _ai_prompt_hint(self) -> list[list[HintItem]] | None:
        if not self._ai_prompt_hint_due or self.mode != _CanvasMode.CREATE:
            return None
        box = functools.partial(_paint_box_mark, color=self._draft_palette.line)
        if self.create_mode == "ai_segment":
            return [
                [*self._ai_click_items(), HintItem(self.tr("Drag a box"), mark=box)]
            ]
        if self.create_mode == "ai_find_all":
            return [[HintItem(self.tr("Drag around one example"), mark=box)]]
        return None

    def _ai_suggestion_hint(
        self,
    ) -> tuple[tuple[QPointF, QPointF], list[list[HintItem]]] | None:
        # A suggestion waiting for Enter or Esc: the image corners of the box
        # around it and its prompts, and the chip rows that name the keys.
        if self.mode != _CanvasMode.CREATE or self.is_ai_finalizing:
            return None
        discard = HintItem(self.tr("Discard"), key="Esc")
        if self.create_mode == "ai_segment":
            current = self._current
            if (
                current is None
                or not self._ai_segment_result
                or (self._ai_segment_dragging)
            ):
                return None
            points = [_drawn_corners(shape=s) for s in self._ai_segment_result]
            points.append(np.array([[p.x(), p.y()] for p in current.points]))
            return _bounding_corners(points=points), [
                [HintItem(self.tr("Add"), key=RETURN_GLYPH), discard],
                self._ai_click_items(),
            ]
        if self.create_mode == "ai_find_all":
            if (
                not self.has_ai_find_all_draft
                or self._current is not None
                or self._ai_find_all_pending  # The label dialog is open.
            ):
                return None
            draft = self._ai_find_all_draft
            first = [discard]
            if draft:
                add = self.tr("Add %d") % len(draft)
                first.insert(0, HintItem(add, key=RETURN_GLYPH))
            points = [_drawn_corners(shape=s) for s in draft]
            points.append(self._ai_find_all_points)
            return _bounding_corners(points=points), [
                first,
                [
                    HintItem(
                        self.tr("Drag to exclude"),
                        key=_utils.modifier_text(
                            modifiers=Qt.KeyboardModifier.ShiftModifier
                        ),
                        mark=functools.partial(
                            _paint_box_mark, color=_NEGATIVE_PALETTE.line
                        ),
                    )
                ],
            ]
        return None

    def _ai_click_items(self) -> list[HintItem]:
        return [
            HintItem(self.tr("Click to include"), mark=self._paint_point_mark),
            HintItem(
                self.tr("Click to exclude"),
                key=_utils.modifier_text(modifiers=Qt.KeyboardModifier.ShiftModifier),
                mark=functools.partial(self._paint_point_mark, label=0),
            ),
        ]

    def _paint_point_mark(
        self, painter: QtGui.QPainter, center: QPointF, /, *, label: int = 1
    ) -> None:
        # The prompt point itself, as the canvas draws it at any zoom.
        point = Shape(
            shape_type="points",
            points=np.array([[center.x(), center.y()]]),
            point_labels=np.array([label]),
        )
        context = dataclasses.replace(
            self._draft_render_context(
                selected=False, fill=False, highlight=None, rotation_highlight=None
            ),
            scale=1.0,
        )
        render_shape(painter=painter, shape=point, context=context)

    def _draw_pixmap_layer(self, painter: QtGui.QPainter, /) -> None:
        target = QtCore.QRectF(
            0.0,
            0.0,
            self.pixmap.width() * self.scale,
            self.pixmap.height() * self.scale,
        )
        painter.drawPixmap(target, self.pixmap, QtCore.QRectF(self.pixmap.rect()))

    def _draw_crosshair_layer(self, painter: QtGui.QPainter, /) -> None:
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
            offset = self._compute_image_origin_offset(area=None) * self.scale
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

    def _should_draw_crosshair(self, *, cursor: QPointF | None) -> bool:
        if self.mode != _CanvasMode.CREATE:
            return False
        if not self._crosshair[self._create_mode]:
            return False
        if cursor is None:
            return False
        return not self._should_constrain_to_pixmap(point=cursor)

    def _draw_committed_shapes_layer(self, painter: QtGui.QPainter, /) -> None:
        # Zoomed in, the scroll area shows a small part of the canvas, and a
        # partial repaint a smaller one still; skip the shapes outside it. An
        # unshown canvas (offscreen render) has no visible region, so it
        # paints everything.
        visible = self.visibleRegion().boundingRect() & self._dirty_rect
        visible_rect = (
            None
            if visible.isEmpty()
            else painter.transform().inverted()[0].mapRect(QRectF(visible))
        )
        for shape in self.shapes:
            if not shape.visible:
                continue
            context = self._render_context(
                shape=shape, highlighted=shape is self.hovered_shape
            )
            if visible_rect is not None and not intersects_rect(
                painter=painter, shape=shape, context=context, rect=visible_rect
            ):
                continue
            render_shape(painter=painter, shape=shape, context=context)

    def _draw_active_shape_layer(self, painter: QtGui.QPainter, /) -> None:
        if self.create_mode == "ai_segment":
            self._draw_ai_segment_drafts(painter=painter)
            return
        if self._current is None:
            return
        assert len(self._line.points) == len(self._line.point_labels)
        self._render_draft(painter=painter, draft=self._current, highlighted=True)
        self._render_draft(painter=painter, draft=self._line, highlighted=False)

    def _draw_ai_segment_drafts(self, *, painter: QtGui.QPainter) -> None:
        # The box being dragged hides the one it replaces.
        if self._current is not None:
            current = self._current
            if self._ai_segment_dragging:
                current = _without_ai_segment_box(draft=current)
            for draft in _split_ai_segment_draft(draft=current):
                self._render_draft(painter=painter, draft=draft, highlighted=True)
        if self._current is not None or self._ai_segment_dragging:
            for draft in _split_ai_segment_draft(draft=self._line):
                self._render_draft(painter=painter, draft=draft, highlighted=False)

    def _draw_preview_overlay_layer(self, painter: QtGui.QPainter, /) -> None:
        if self.create_mode == "ai_segment":
            self._draw_ai_segment_proposals(painter=painter)
            return
        previews = self._build_preview_shapes()
        if not previews:
            return
        context = self._draft_render_context(
            selected=self._fill_drawing,
            fill=self._fill_drawing,
            highlight=None,
            rotation_highlight=None,
        )
        for preview in previews:
            render_shape(painter=painter, shape=preview, context=context)

    def _draw_ai_find_all_layer(self, painter: QtGui.QPainter, /) -> None:
        if not (self._ai_find_all_pending or self.has_ai_find_all_draft):
            return
        context = self._draft_render_context(
            selected=False, fill=True, highlight=None, rotation_highlight=None
        )
        # Results waiting for Enter take the selected style, a white edge, as
        # an AI-Segment result does. The example boxes are prompts, so
        # they stay dashed guides, red for a counter-example.
        # An example-box batch is also its draft, so it is drawn once.
        result_context = dataclasses.replace(context, selected=True)
        for shape in self._ai_find_all_pending or self._ai_find_all_draft:
            render_shape(painter=painter, shape=shape, context=result_context)
        if not self.has_ai_find_all_draft:
            return
        corners = self._ai_find_all_points.reshape(-1, 2, 2)
        labels = self._ai_find_all_point_labels.reshape(-1, 2)[:, 0]
        for (p1, p2), label in zip(corners, labels, strict=True):
            is_counter = label == 4  # noqa: PLR2004 -- SAM negative box corner
            example = Shape(shape_type="rectangle", points=np.array([p1, p2]))
            palette = _NEGATIVE_PALETTE if is_counter else context.palette
            render_shape(
                painter=painter,
                shape=example,
                context=dataclasses.replace(
                    context,
                    palette=palette,
                    fill=False,
                    line_style=Qt.PenStyle.DashLine,
                ),
            )
            if is_counter:
                # A "−" inside the top-left corner marks a counter-example.
                x, y = p1 * self.scale + 10.0
                painter.setPen(QtGui.QPen(palette.line, 3.0))
                painter.drawLine(QPointF(x, y), QPointF(x + 12.0, y))

    def _draw_ai_existing_match_layer(self, painter: QtGui.QPainter, /) -> None:
        AI_EXISTING_MATCH_PALETTE: Final[Palette] = Palette(
            line=QtGui.QColor(255, 170, 0),
            fill=QtGui.QColor(255, 170, 0, 64),
            select_line=QtGui.QColor(255, 170, 0),
            select_fill=QtGui.QColor(255, 170, 0, 64),
            vertex_fill=QtGui.QColor(255, 170, 0),
            hvertex_fill=QtGui.QColor(255, 255, 255),
        )
        context = ShapeRenderContext(
            scale=self.scale,
            palette=AI_EXISTING_MATCH_PALETTE,
            point_size=self._point_size,
            point_type=self._point_type,
            selected=False,
            fill=True,
            highlight=None,
            rotation_highlight=None,
            line_style=Qt.PenStyle.DashLine,
        )
        for shape in self._ai_existing_shape_highlights:
            render_shape(painter=painter, shape=shape, context=context)

    def _render_draft(
        self, *, painter: QtGui.QPainter, draft: _DraftShape, highlighted: bool
    ) -> None:
        shape = _draft_to_shape(draft=draft)
        context = self._draft_render_context(
            selected=False,
            fill=False,
            highlight=self._highlight if highlighted else None,
            rotation_highlight=self._rotation_highlight if highlighted else None,
        )
        if self.create_mode in _AI_CREATE_MODES and draft.shape_type == "rectangle":
            # A prompt box never becomes a shape, so it is a dashed guide.
            context = dataclasses.replace(context, line_style=Qt.PenStyle.DashLine)
        if self.create_mode == "ai_find_all" and draft.point_labels[:1] == (0,):
            context = dataclasses.replace(context, palette=_NEGATIVE_PALETTE)
        render_shape(painter=painter, shape=shape, context=context)

    def _draw_ai_segment_proposals(self, *, painter: QtGui.QPainter) -> None:
        # Defer inference until painting ends; unchanged inputs stop the loop.
        self._ai_preview_timer.start(0)
        if self._current is None and not self._ai_segment_dragging:
            return
        # Both layers take the selected style: its fill is the draft's colour,
        # where the plain draft fill is a dark tint.
        selected = self._draft_render_context(
            selected=True, fill=True, highlight=None, rotation_highlight=None
        )
        # The guess at the cursor is what a click there gives, including the
        # area it would drop, so it is a bare mask fill.
        guess_context = dataclasses.replace(selected, outline=False)
        for shape in self._ai_segment_preview or []:
            render_shape(painter=painter, shape=shape, context=guess_context)
        # What Enter adds has a white edge and its vertices, as AI-Find All
        # results waiting for Enter do. It fills only while there is no guess.
        fill = self._ai_segment_preview is None
        context = dataclasses.replace(selected, fill=fill, fill_mask=fill)
        for shape in self._ai_segment_result:
            render_shape(painter=painter, shape=shape, context=context)

    def _build_preview_shapes(self) -> list[Shape]:
        if self._current is None:
            return []
        if self.create_mode == "polygon":
            return [self._build_polygon_preview(current=self._current)]
        return []

    def _build_polygon_preview(self, *, current: _DraftShape) -> Shape:
        # The cursor closes the shape, so previewing a fill needs one fewer point.
        MIN_POINTS_FOR_FILL_PREVIEW: Final = 2

        preview = current
        if self._fill_drawing and len(preview.points) >= MIN_POINTS_FOR_FILL_PREVIEW:
            preview = preview.add_point(point=self._line.points[1], autoclose=True)
        return _draft_to_shape(draft=preview)

    def _refresh_ai_segment_preview(self) -> None:
        if self.is_ai_finalizing:
            return  # the draft is frozen until its result lands
        current = self._current
        if self.create_mode != "ai_segment" or (
            current is None and not self._ai_segment_dragging
        ):
            self._ai_segment_result = []
            self._ai_segment_result_key = None
            self._ai_segment_preview = None
            self._ai_segment_preview_key = None
            return
        settings = (
            self._ai_assist_session.model_name,
            self._ai_suppress_existing_shape_matches,
            self._allow_out_of_bounds_points,
            self.pixmap.cacheKey(),
            tuple(self.shapes),
        )
        # The guess is always a mask (see _ai_proposer), so only the result
        # depends on the output format and polygon detail.
        result_key = (
            current,
            self._ai_assist_session.output_format,
            self._ai_assist_session.polygon_detail,
            *settings,
        )
        if result_key != self._ai_segment_result_key:
            self._ai_segment_result_key = result_key
            if current is None or not current.points:
                self._ai_segment_result = []
                self._set_ai_existing_shape_highlights(shapes=[])
                self.update()
            else:
                self._submit_ai_job(
                    channel="result",
                    **_ai_segment_prompt(draft=current),
                    preview_key=result_key,
                )
        key = (current, self._line, *settings)
        if key == self._ai_segment_preview_key:
            return
        self._ai_segment_preview_key = key
        base = current or _DraftShape(shape_type="points")
        preview = _with_ai_segment_input(draft=base, line=self._line)
        # No input at the cursor, or a box with no area: nothing to guess.
        if preview is None or preview == base:
            if self._ai_preview_job is not None:
                # A guess still queued would delay the result of a new click.
                assert self._osam_worker is not None
                self._osam_worker.cancel(channel="preview")
                self._ai_preview_job = None
            self._ai_segment_preview = None
            self.update()
            return
        self._submit_ai_job(
            channel="preview",
            **_ai_segment_prompt(draft=preview),
            preview_key=key,
        )

    def _show_ai_segment_proposal(
        self,
        *,
        job: _AiJob,
        proposal: _automation.AiAssistProposal | None,
        error: str | None,
    ) -> None:
        shapes = [] if proposal is None else proposal.new_shapes
        if job.channel == "result":
            self._ai_segment_result = shapes
            # Enter adds the result, so its matches are the ones to flag.
            self._set_ai_existing_shape_highlights(
                shapes=[] if proposal is None else proposal.matching_existing_shapes
            )
        else:
            self._ai_segment_preview = shapes
        if proposal is None:
            # Repeated failed prompts report once; a success re-arms the report.
            if not self._ai_inference_failed:
                assert error is not None
                self._report_inference_failure(error=error)
        else:
            self._ai_inference_failed = False
        self.update()

    def transform_widget_point_to_image(self, *, point: QPointF) -> QPointF:
        origin = self._compute_image_origin_offset(area=None)
        return point / self.scale - origin

    def transform_image_point_to_widget(
        self, *, point: QPointF, area: QtCore.QSize | None = None
    ) -> QPointF:
        return (point + self._compute_image_origin_offset(area=area)) * self.scale

    def _compute_image_origin_offset(self, *, area: QtCore.QSize | None) -> QPointF:
        if area is None:
            area = super().size()
        scaled_w = self.pixmap.width() * self.scale
        scaled_h = self.pixmap.height() * self.scale
        slack_w = max(area.width() - scaled_w, 0.0)
        slack_h = max(area.height() - scaled_h, 0.0)
        return (QPointF(slack_w, slack_h) / 2.0 + self._view_offset) / self.scale

    def is_out_of_pixmap(self, *, p: QPointF) -> bool:
        return _is_out_of_image(point=p, image_size=self.pixmap.size())

    def _should_constrain_to_pixmap(self, *, point: QPointF) -> bool:
        return not self._allow_out_of_bounds_points and self.is_out_of_pixmap(p=point)

    def _finalize(self) -> None:
        assert self._current is not None
        if self.create_mode in _AI_CREATE_MODES:
            # The model may have changed since the first corner.
            if self._refuses_example_box():
                self._cancel_current_shape()
                return
            # Input waits until the result lands, so the draft stays as sent.
            draft = self._current
            if self.create_mode == "ai_find_all":
                self._submit_ai_find_all(
                    box=_normalize_bbox_points(bbox_points=draft.points),
                    # 2, 3 = example box corners; 4, 5 = counter-example corners
                    box_labels=[2, 3] if draft.point_labels[0] == 1 else [4, 5],
                    draft=draft,
                )
                return
            assert self.create_mode == "ai_segment"
            self._submit_ai_job(
                channel="finalize", **_ai_segment_prompt(draft=draft), draft=draft
            )
            return
        self._current = self._current.close()
        if _is_degenerate_draft(draft=self._current):
            self.degenerate_shape_rejected.emit()
            self._cancel_current_shape()
            return
        self._commit_new_shapes(new_shapes=[_draft_to_shape(draft=self._current)])

    def _submit_ai_find_all(
        self,
        *,
        box: Sequence[QPointF],
        box_labels: Sequence[int],
        draft: _DraftShape | None,
    ) -> None:
        # Every example so far goes with the new box, so the draft reflects all.
        self._submit_ai_job(
            channel="finalize",
            prompt_kind="example_box",
            points=[*(QPointF(x, y) for x, y in self._ai_find_all_points), *box],
            point_labels=[*self._ai_find_all_point_labels.tolist(), *box_labels],
            draft=draft,
        )

    def rerun_ai_find_all_draft(self) -> None:
        # Run with a draft shown refines it with the current query.
        if self._current is not None or self.is_ai_finalizing:
            return
        if self._refuses_example_box():
            return
        if not self.ensure_ai_model_ready(self._get_mode_ai_model_name()):
            return
        self._submit_ai_find_all(box=[], box_labels=[], draft=None)

    def _finish_ai_finalize(
        self,
        *,
        job: _AiJob,
        proposal: _automation.AiAssistProposal | None,
        error: str | None,
    ) -> None:
        if proposal is None:
            assert error is not None
            self._report_inference_failure(error=error)
            self._cancel_current_shape()
            return
        self._ai_inference_failed = False
        if job.prompt_kind == "example_box":
            # Each example replaces the draft; Enter commits it, Esc discards it.
            self._ai_find_all_points = job.points
            self._ai_find_all_point_labels = job.point_labels
            self._ai_find_all_draft = proposal.new_shapes
            self._ai_find_all_query = job.query
            if not proposal.new_shapes and not proposal.matching_existing_shapes:
                self.inference_produced_no_shapes.emit()
            self._cancel_current_shape()
            self._set_ai_existing_shape_highlights(
                shapes=proposal.matching_existing_shapes
            )
            self._update_status(extra_messages=None)
            return
        if proposal.new_shapes:
            self._set_ai_existing_shape_highlights(
                shapes=proposal.matching_existing_shapes
            )
            self._commit_new_shapes(new_shapes=proposal.new_shapes)
            return
        if not proposal.matching_existing_shapes:
            self.inference_produced_no_shapes.emit()
        self._cancel_current_shape()
        self._set_ai_existing_shape_highlights(shapes=proposal.matching_existing_shapes)

    def _commit_new_shapes(self, *, new_shapes: list[Shape]) -> None:
        self.shapes.extend(new_shapes)
        self.backup_shapes()
        self._reset_after_shape_creation()

    def _reset_after_shape_creation(self) -> None:
        self._current = None
        # new_shape's handler blocks on the modal label dialog, so paint the
        # committed shape synchronously first. Some modes, including point and
        # AI-Segment, can finalize without a matching preview on screen.
        self.repaint()
        self.new_shape.emit()
        self.update()

    def _cancel_current_shape(self) -> None:
        self._current = None
        self._ai_segment_press = None
        self._ai_segment_dragging = False
        self._ai_finalize_job = None
        self._set_ai_existing_shape_highlights(shapes=[])
        self.busy_changed.emit()
        self.update()

    def _set_ai_existing_shape_highlights(self, *, shapes: list[Shape]) -> None:
        self._ai_existing_shape_highlights = shapes[:]

    def _clear_ai_existing_shape_highlights(self) -> None:
        if self._ai_existing_shape_highlights:
            self._set_ai_existing_shape_highlights(shapes=[])
        self.update()

    def _compute_canvas_size(self) -> QtCore.QSize:
        if self.pixmap.isNull():
            return super().minimumSizeHint()
        scaled = self._compute_scaled_pixmap_size()
        available = self.compute_settled_viewport_size()
        if available is None:
            return scaled
        return scaled.expandedTo(available)

    def _compute_scaled_pixmap_size(self) -> QtCore.QSize:
        return QtCore.QSize(
            int(self.pixmap.width() * self.scale),
            int(self.pixmap.height() * self.scale),
        )

    def compute_settled_viewport_size(self) -> QtCore.QSize | None:
        # The scroll area shows or hides its scrollbars after the next layout
        # pass, so the live viewport size lags a scale change until then.
        # Return the size it settles at for the current scale.
        if self.pixmap.isNull():
            return None
        scroll_area = self._find_scroll_area()
        if scroll_area is None:
            return None
        scaled = self._compute_scaled_pixmap_size()
        scaled_w, scaled_h = scaled.width(), scaled.height()

        viewport_size = scroll_area.maximumViewportSize()
        h_bar_height = scroll_area.horizontalScrollBar().sizeHint().height()
        v_bar_width = scroll_area.verticalScrollBar().sizeHint().width()
        needs_h_bar = scaled_w > viewport_size.width()
        needs_v_bar = scaled_h > viewport_size.height()
        if needs_v_bar:
            needs_h_bar = scaled_w > viewport_size.width() - v_bar_width
        if needs_h_bar:
            needs_v_bar = scaled_h > viewport_size.height() - h_bar_height

        available_w = viewport_size.width() - (v_bar_width if needs_v_bar else 0)
        available_h = viewport_size.height() - (h_bar_height if needs_h_bar else 0)
        return QtCore.QSize(available_w, available_h)

    def sizeHint(self) -> QtCore.QSize:
        return self._compute_canvas_size()

    def minimumSizeHint(self) -> QtCore.QSize:
        return self._compute_canvas_size()

    @override
    def wheelEvent(self, a0: QtGui.QWheelEvent, /) -> None:
        self._clear_ai_existing_shape_highlights()
        mods: Qt.KeyboardModifier = a0.modifiers()
        delta: QPoint = a0.angleDelta()
        if delta.isNull():
            a0.accept()
            return
        if mods == Qt.KeyboardModifier.ControlModifier:
            # with Ctrl/Command key
            # zoom
            if delta.y() != 0:
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

    def _move_by_keyboard(self, *, offset: QPointF) -> None:
        shapes = self._movable_selected_shapes()
        if not shapes:
            return
        self._drag_shapes(
            shapes=shapes,
            cursor=self._prev_point + offset,
            constrain_cursor=False,
        )
        self.update()
        self._is_moving_shape = True

    @override
    def keyPressEvent(self, a0: QtGui.QKeyEvent, /) -> None:
        self._clear_ai_existing_shape_highlights()
        modifiers = a0.modifiers()
        key = a0.key()
        if self.mode == _CanvasMode.CREATE:
            if key == Qt.Key.Key_Escape and (
                self._current is not None or self._ai_segment_press is not None
            ):
                self._cancel_current_shape()
            elif key == Qt.Key.Key_Escape and self.has_ai_find_all_draft:
                self._discard_ai_find_all_draft()  # Also drops a pending re-run.
            elif self.is_ai_finalizing:
                pass
            elif (
                key in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and self._current is None
                and self.has_ai_find_all_draft
            ):
                self._commit_ai_find_all_draft()
            elif (
                key in (Qt.Key.Key_Return, Qt.Key.Key_Space) and self._can_close_shape()
            ):
                self._finalize()
            elif modifiers == Qt.KeyboardModifier.AltModifier:
                self._snapping = False
        elif self.mode == _CanvasMode.EDIT:
            direction = _ARROW_KEY_TO_DIRECTION.get(Qt.Key(key))
            if direction is not None:
                self._move_by_keyboard(offset=direction * MOVE_SPEED)
            elif a0.matches(QtGui.QKeySequence.StandardKey.SelectAll):
                self.select_shapes(shapes=self.shapes[:])
        self._update_status(extra_messages=None)

    @override
    def keyReleaseEvent(self, a0: QtGui.QKeyEvent, /) -> None:
        modifiers = a0.modifiers()
        if self.mode == _CanvasMode.CREATE:
            if not modifiers:
                self._snapping = True
        elif self.mode == _CanvasMode.EDIT:
            if self._is_moving_shape and self._movable_selected_shapes():
                self._commit_pending_shape_move()
                self._drag_anchor = None

    def set_last_label(self, *, text: str, flags: dict[str, bool]) -> list[Shape]:
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
        return shapes

    def undo_last_line(self) -> None:
        if self.create_mode in _AI_CREATE_MODES:
            # Remove all unlabeled shapes at the tail (added by AI in one shot)
            while self.shapes and self.shapes[-1].label is None:
                self.shapes.pop()
            self._cancel_current_shape()
            return
        self._current = _shape_to_draft(shape=self.shapes.pop()).open()
        if self.create_mode in POLYLINE_SHAPE_TYPES:
            self._line = dataclasses.replace(
                self._line,
                points=(self._current.points[-1], self._current.points[0]),
                point_labels=(
                    self._current.point_labels[-1],
                    self._current.point_labels[0],
                ),
            )
        elif self.create_mode in (
            "rectangle",
            "line",
            "circle",
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
        self.busy_changed.emit()

    def undo_last_point(self) -> None:
        current = self._current
        # The draft stays as sent while its AI Shape is pending; the Undo Last
        # Point action reaches here without passing the input guards.
        if current is None or current.closed or self.is_ai_finalizing:
            return
        if (
            self.create_mode == "oriented_rectangle"
            and len(current.points) == ORIENTED_RECTANGLE_POINT_COUNT
        ):
            self._unlock_oriented_rectangle_first_edge(current=current)
            self.update()
            return
        if self.create_mode == "ai_segment":
            self._current = (
                _without_ai_segment_box(draft=current)
                if current.point_labels[-1] == _AI_BOX_LABELS[1]
                else current.pop_point()
            )
            if not self._current.points:
                self._cancel_current_shape()
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
        self._drag_anchor = None
        was_drawing = self.is_drawing
        self._current = None
        if was_drawing:
            self.busy_changed.emit()
        self.hovered_shape = None
        self._hovered_vertex = None
        self._hovered_edge = None
        self._hovered_rotation = None
        self._clear_highlight_state()
        self._set_ai_existing_shape_highlights(shapes=[])

    def load_pixmap(self, *, pixmap: QtGui.QPixmap, clear_shapes: bool = True) -> None:
        self.pixmap = pixmap
        self._drag_anchor = None
        self._pixmap_rgb = None
        # A new image is a fresh inference context that should surface its own
        # first failure rather than staying muted by the prior image's latch.
        self._ai_inference_failed = False
        self._set_ai_existing_shape_highlights(shapes=[])
        self._clear_ai_find_all_draft()
        if clear_shapes:
            self.shapes = []
        self.update()

    def load_shapes(self, *, shapes: list[Shape], replace: bool = True) -> None:
        self.shapes = list(shapes) if replace else self.shapes + list(shapes)
        self.backup_shapes()
        self._reset_interaction_state()
        self.update()

    def set_shape_visible(self, *, shape: Shape, value: bool) -> None:
        if shape.visible == value:
            return
        shape.visible = value
        if not value:
            self._forget_hover(shapes=[shape])
        self.update()

    def _apply_cursor(self, *, role: CursorRole) -> None:
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
        self._ai_preview_timer.stop()
        self._ai_preview_job = None
        self._ai_result_job = None
        self._ai_finalize_job = None
        self._ai_segment_result = []
        self._ai_segment_result_key = None
        self._ai_segment_preview = None
        self._ai_segment_preview_key = None
        self._ai_segment_press = None
        self._ai_segment_dragging = False
        self._clear_ai_find_all_draft()
        self._release_cursor()
        self.pixmap = QtGui.QPixmap()
        self._pixmap_rgb = None
        self._drag_anchor = None
        self.shapes = []
        self.shape_backups = collections.deque(maxlen=self._num_backups)
        self._is_moving_shape = False
        self._is_pointer_held = False
        self.selected_shapes = []
        self._current = None
        self._view_offset = QPointF()
        self._highlight = None
        self._rotation_highlight = None
        self._set_ai_existing_shape_highlights(shapes=[])
        self.hovered_shape = None
        self._last_hovered_shape = None
        self._hovered_vertex = None
        self._last_hovered_vertex = None
        self._hovered_edge = None
        self._last_hovered_edge = None
        self._hovered_rotation = None
        # The draft and any pending AI job are gone with the old image.
        self.busy_changed.emit()
        self.update()


def _is_degenerate_draft(*, draft: _DraftShape) -> bool:
    points = draft.points
    shape_type = draft.shape_type
    if shape_type == "polygon":
        return len({(p.x(), p.y()) for p in points}) < MIN_POLYGON_POINT_COUNT
    if shape_type == "linestrip":
        return len({(p.x(), p.y()) for p in points}) < MIN_LINESTRIP_POINT_COUNT
    if shape_type == "rectangle":
        return (
            len(points) != RECTANGLE_POINT_COUNT
            or points[0].x() == points[1].x()
            or points[0].y() == points[1].y()
        )
    if shape_type in ("circle", "line"):
        return len(points) != CIRCLE_POINT_COUNT or points[0] == points[1]
    if shape_type == "oriented_rectangle":
        return (
            len(points) != ORIENTED_RECTANGLE_POINT_COUNT
            or points[0] == points[1]
            or points[1] == points[2]
        )
    return False


def _ai_segment_point(*, pos: QPointF, modifiers: Qt.KeyboardModifier) -> _DraftShape:
    # Shift marks a negative point.
    is_negative = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
    return _DraftShape(
        shape_type="points", points=(pos,), point_labels=(0 if is_negative else 1,)
    )


def _without_ai_segment_box(*, draft: _DraftShape) -> _DraftShape:
    kept = [
        (point, label)
        for point, label in zip(draft.points, draft.point_labels, strict=True)
        if label not in _AI_BOX_LABELS
    ]
    return dataclasses.replace(
        draft,
        points=tuple(point for point, _ in kept),
        point_labels=tuple(label for _, label in kept),
    )


def _with_ai_segment_input(
    *, draft: _DraftShape, line: _DraftShape
) -> _DraftShape | None:
    # line holds no input, one point, or two box corners that replace the
    # draft's box; None for a box with no area.
    if not line.points:
        return draft
    if line.point_labels != _AI_BOX_LABELS:
        return draft.add_point(point=line.points[0], label=line.point_labels[0])
    first, second = line.points
    if first.x() == second.x() or first.y() == second.y():
        return None
    # A new box replaces the old one; the draft keeps input order for undo.
    draft = _without_ai_segment_box(draft=draft)
    return dataclasses.replace(
        draft,
        points=(*draft.points, first, second),
        point_labels=(*draft.point_labels, *_AI_BOX_LABELS),
    )


def _ai_segment_box(*, draft: _DraftShape) -> tuple[QPointF, ...]:
    return tuple(
        point
        for point, label in zip(draft.points, draft.point_labels, strict=True)
        if label in _AI_BOX_LABELS
    )


def _split_ai_segment_draft(*, draft: _DraftShape) -> list[_DraftShape]:
    # Points draw as markers and the box as a rectangle.
    drafts = []
    points = _without_ai_segment_box(draft=draft)
    if points.points:
        drafts.append(points)
    corners = _ai_segment_box(draft=draft)
    if corners:
        drafts.append(
            _DraftShape(
                shape_type="rectangle",
                points=corners,
                point_labels=(1,) * len(corners),
                closed=True,
            )
        )
    return drafts


def _ai_segment_prompt(*, draft: _DraftShape) -> dict[str, Any]:
    points = _without_ai_segment_box(draft=draft)
    corners = _ai_segment_box(draft=draft)
    box = _normalize_bbox_points(bbox_points=corners) if corners else []
    return dict(
        prompt_kind="points" if points.points else "box",
        points=[*points.points, *box],
        point_labels=[*points.point_labels, *_AI_BOX_LABELS[: len(box)]],
    )


def _clamp_into_image(*, point: QPointF, image_size: QtCore.QSize) -> QPointF:
    return QPointF(
        min(max(point.x(), 0.0), image_size.width() - 1.0),
        min(max(point.y(), 0.0), image_size.height() - 1.0),
    )


def _normalize_bbox_points(*, bbox_points: Sequence[QPointF]) -> list[QPointF]:
    if len(bbox_points) != RECTANGLE_POINT_COUNT:
        raise ValueError(f"Expected 2 points for bbox, got {len(bbox_points)}")

    p1, p2 = bbox_points
    xmin = min(p1.x(), p2.x())
    ymin = min(p1.y(), p2.y())
    xmax = max(p1.x(), p2.x())
    ymax = max(p1.y(), p2.y())
    return [QPointF(xmin, ymin), QPointF(xmax, ymax)]


def _snap_cursor_pos_for_square(*, pos: QPointF, opposite_vertex: QPointF) -> QPointF:
    offset = pos - opposite_vertex
    square = QtCore.QSizeF(1, 1).scaled(
        abs(offset.x()), abs(offset.y()), Qt.AspectRatioMode.KeepAspectRatio
    )
    return opposite_vertex + QPointF(
        -square.width() if offset.x() < 0 else square.width(),
        -square.height() if offset.y() < 0 else square.height(),
    )


def _compute_intersection_edges_image(
    *, p1: QPointF, p2: QPointF, image_size: QtCore.QSize
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
        if denominator <= 0.0:
            continue
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
    *, selected_shapes: list[Shape], hovered_shape: Shape | None
) -> bool:
    if not selected_shapes:
        return True
    if hovered_shape is None:
        return False
    return hovered_shape not in selected_shapes


def _opposite_corner_in_parallelogram(
    *, opposite_to: QPointF, neighbor1: QPointF, neighbor2: QPointF
) -> QPointF:
    return neighbor1 + neighbor2 - opposite_to


def _compute_shapes_bounds(*, shapes: list[Shape]) -> QRectF:
    assert shapes
    bounds = _shape_bounds(shape=shapes[0])
    for shape in shapes[1:]:
        rect = _shape_bounds(shape=shape)
        # Qt's rectangle union discards null rects, excluding point shapes.
        bounds.setCoords(
            min(bounds.left(), rect.left()),
            min(bounds.top(), rect.top()),
            max(bounds.right(), rect.right()),
            max(bounds.bottom(), rect.bottom()),
        )
    return bounds


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


def _is_out_of_image(*, point: QPointF, image_size: QtCore.QSize) -> bool:
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
    # The dragged corner and its two neighbors move so the shape stays a
    # parallelogram, clipped to the image unless out-of-bounds points are
    # allowed; the opposite anchor is fixed.
    anchor = corners[(vertex_index - 2) % 4]
    edge_axis = corners[(vertex_index - 1) % 4]
    moving = pos
    adjacent_perp, adjacent_para = _project_oriented_rectangle_corners(
        anchor=anchor, edge_axis=edge_axis, moving=moving
    )

    if not allow_out_of_bounds:
        if _is_out_of_image(point=moving, image_size=image_size):
            edge_a = _compute_intersection_edges_image(
                p1=adjacent_perp, p2=moving, image_size=image_size
            )
            edge_b = _compute_intersection_edges_image(
                p1=adjacent_para, p2=moving, image_size=image_size
            )
            if edge_a == edge_b:
                moving = QPointF(
                    np.clip(moving.x(), 0.0, image_size.width()),
                    np.clip(moving.y(), 0.0, image_size.height()),
                )
            else:
                moving = _utils.project_point_on_line(
                    point=moving, line_start=edge_a, line_end=edge_b
                )
            adjacent_perp, adjacent_para = _project_oriented_rectangle_corners(
                anchor=anchor, edge_axis=adjacent_para, moving=moving
            )

        if _is_out_of_image(point=adjacent_perp, image_size=image_size):
            adjacent_perp = _compute_intersection_edges_image(
                p1=anchor, p2=adjacent_perp, image_size=image_size
            )
            moving = _opposite_corner_in_parallelogram(
                opposite_to=anchor, neighbor1=adjacent_perp, neighbor2=adjacent_para
            )

        if _is_out_of_image(point=adjacent_para, image_size=image_size):
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
