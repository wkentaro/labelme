from __future__ import annotations

import contextlib
import copy
import enum
import functools
import html
import operator
import os
import platform
import re
import subprocess
import time
import typing
import unicodedata
import webbrowser
from collections.abc import Callable
from pathlib import Path
from typing import Final
from typing import Literal
from typing import NamedTuple
from typing import TypeAlias
from typing import cast

import natsort
import numpy as np
from loguru import logger
from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from labelme import __appname__
from labelme import __version__

from . import _ai_models
from . import _automation
from . import _config
from . import _utils
from ._image_prefetcher import ImagePrefetcher
from ._label_file import LABEL_FILE_SUFFIX
from ._label_file import RASTER_MAX_SIDE
from ._label_file import Annotation
from ._label_file import ImageNotFoundError
from ._label_file import ImageTooLargeError
from ._label_file import LabelFileError
from ._label_file import LabelFileReadError
from ._label_file import is_label_file_path
from ._label_file import read_image_file
from ._label_file import read_label_file
from ._label_file import read_label_file_image_path
from ._label_flags import apply_default_flags
from ._model_manager import ModelManager
from ._save_request import SaveRequest
from ._save_request import write_save_request
from ._save_writer import SaveWriter
from ._shape import Shape
from ._shape import ShapeDict
from ._shape import ShapeType
from ._shape import can_merge_shapes
from ._shape import merge_masks
from ._shape_clipboard import ShapeClipboard
from ._shape_color import resolve_shape_color
from ._utils import ImageDecodeRequirement
from ._utils import get_image_decode_requirement
from ._widgets import LABEL_COLOR_ROLE
from ._widgets import AiAssistedAnnotationWidget
from ._widgets import AiTextToAnnotationWidget
from ._widgets import AnnotationFolderFooter
from ._widgets import BrightnessContrastDialog
from ._widgets import Canvas
from ._widgets import EmptyStateWidget
from ._widgets import LabelDialog
from ._widgets import LabelDialogEntry
from ._widgets import LabelDialogField
from ._widgets import LabelListWidget
from ._widgets import LabelListWidgetItem
from ._widgets import ModelsDialog
from ._widgets import Palette
from ._widgets import SettingsDialog
from ._widgets import StatusStats
from ._widgets import ToolBar
from ._widgets import UniqueLabelQListWidget
from ._widgets import ZoomWidget
from ._widgets import format_shape_label
from ._widgets import license_link
from ._widgets import license_notice


class _ZoomMode(enum.Enum):
    FIT_WINDOW = enum.auto()
    FIT_SELECTION = enum.auto()
    MANUAL_ZOOM = enum.auto()


_TextToAnnotationCreateMode: TypeAlias = Literal["polygon", "rectangle"]
_AI_CREATE_MODES: Final[tuple[str, ...]] = (
    "ai_points_to_shape",
    "ai_box_to_shape",
)

# Keys of the Window State store, shared by the restore, reset, and close paths.
WINDOW_SIZE_KEY: Final[str] = "window/size"
WINDOW_POSITION_KEY: Final[str] = "window/position"
WINDOW_LAYOUT_KEY: Final[str] = "window/state"
# Maps each absolute opened folder to its absolute Annotation Folder.
ANNOTATION_FOLDERS_KEY: Final[str] = "annotationFolders"


class _StatusBarWidgets(NamedTuple):
    message: QtWidgets.QLabel
    stats: StatusStats
    save: QtWidgets.QLabel
    retry: QtWidgets.QToolButton


class _CanvasWidgets(NamedTuple):
    canvas: Canvas
    empty_state: EmptyStateWidget
    scroll_area: QtWidgets.QScrollArea
    surface: QtWidgets.QStackedWidget
    zoom_widget: ZoomWidget
    scroll_bars: dict[Qt.Orientation, QtWidgets.QScrollBar]


class _ViewportState(NamedTuple):
    zoom_mode: _ZoomMode
    zoom_value: float
    scroll_values: dict[Qt.Orientation, int]
    view_offset: QtCore.QPointF


class _DockWidgets(NamedTuple):
    flag_dock: QtWidgets.QDockWidget
    flag_list: QtWidgets.QListWidget
    shape_dock: QtWidgets.QDockWidget
    label_list: LabelListWidget
    label_dock: QtWidgets.QDockWidget
    unique_label_list: UniqueLabelQListWidget
    file_dock: QtWidgets.QDockWidget
    annotation_folder_footer: AnnotationFolderFooter
    file_search: QtWidgets.QLineEdit
    file_search_error: QtWidgets.QLabel
    file_list: QtWidgets.QListWidget


class _Actions(NamedTuple):
    about: QtGui.QAction
    save: QtGui.QAction
    save_as: QtGui.QAction
    save_auto: QtGui.QAction
    save_with_image_data: QtGui.QAction
    change_output_dir: QtGui.QAction
    open: QtGui.QAction
    close: QtGui.QAction
    delete_file: QtGui.QAction
    toggle_keep_prev_mode: QtGui.QAction
    toggle_keep_prev_brightness_contrast: QtGui.QAction
    delete: QtGui.QAction
    edit: QtGui.QAction
    copy: QtGui.QAction
    paste: QtGui.QAction
    duplicate: QtGui.QAction
    merge: QtGui.QAction
    lock: QtGui.QAction
    undo_last_point: QtGui.QAction
    undo: QtGui.QAction
    add_point_to_edge: QtGui.QAction
    remove_point: QtGui.QAction
    create_mode: QtGui.QAction
    edit_mode: QtGui.QAction
    create_rectangle_mode: QtGui.QAction
    create_oriented_rectangle_mode: QtGui.QAction
    create_circle_mode: QtGui.QAction
    create_line_mode: QtGui.QAction
    create_point_mode: QtGui.QAction
    create_line_strip_mode: QtGui.QAction
    create_ai_points_to_shape_mode: QtGui.QAction
    create_ai_box_to_shape_mode: QtGui.QAction
    open_next_img: QtGui.QAction
    open_prev_img: QtGui.QAction
    keep_prev_zoom: QtGui.QAction
    fit_window: QtGui.QAction
    fit_selection: QtGui.QAction
    brightness_contrast: QtGui.QAction
    zoom_in: QtGui.QAction
    zoom_out: QtGui.QAction
    zoom_org: QtGui.QAction
    reset_layout: QtGui.QAction
    fill_drawing: QtGui.QAction
    hide_all: QtGui.QAction
    show_all: QtGui.QAction
    toggle_all: QtGui.QAction
    open_dir: QtGui.QAction
    zoom_widget_action: QtWidgets.QWidgetAction
    draw: list[tuple[str, QtGui.QAction]]
    image: QtGui.QActionGroup
    context_menu: tuple[QtGui.QAction, ...]
    edit_menu: tuple[QtGui.QAction, ...]


class _Menus(NamedTuple):
    file: QtWidgets.QMenu
    edit: QtWidgets.QMenu
    view: QtWidgets.QMenu
    help: QtWidgets.QMenu
    label_list: QtWidgets.QMenu


def _default_window_geometry(
    available: QtCore.QRect, /, *, toolbar_width: int
) -> QtCore.QRect:
    # A first window wide enough for the whole labeled toolbar, shrunk to fit a
    # smaller screen and centered on it.
    size = QtCore.QSize(max(1280, toolbar_width), 800)
    geometry = QtCore.QRect(QtCore.QPoint(), size.boundedTo(available.size()))
    geometry.moveCenter(available.center())
    return geometry


def _try_load_config(
    *, config_file: Path | None, config_overrides: dict
) -> dict | None:
    try:
        return _config.load_config(
            config_file=config_file, config_overrides=config_overrides
        )
    except Exception:
        return None


class MainWindow(QtWidgets.QMainWindow):
    _config_file: Path | None
    _config: dict
    _config_overrides: dict

    _text_osam_session: _automation.OsamSession | None = None
    _is_changed: bool = False
    _shape_clipboard: ShapeClipboard
    _zoom_mode: _ZoomMode
    _is_canvas_pointer_active: bool = False
    _is_fit_selection_deferred: bool = False
    _fit_selection_timer: QtCore.QTimer
    _prev_opened_dir: str | None
    _canvas_widgets: _CanvasWidgets
    _status_bar: _StatusBarWidgets
    _status_mouse_pos: QtCore.QPointF | None
    _zoom_mode_label: QtWidgets.QLabel
    _zoom_mode_captions: dict[_ZoomMode, str]
    _docks: _DockWidgets
    _actions: _Actions
    _persistent_actions: dict[tuple[str, ...], QtGui.QAction]
    _menus: _Menus
    _label_dialog: LabelDialog
    _settings_dialog: SettingsDialog | None = None
    _models_dialog: ModelsDialog | None = None
    _shape_color_preview: dict | None
    _ai_annotation: AiAssistedAnnotationWidget
    _ai_text: AiTextToAnnotationWidget

    _output_dir_value: Path | None = None
    _image: QtGui.QImage
    _annotation: Annotation | None
    _label_file_path: str | None
    _failed_save_path: str | None
    _image_path: str | None
    _file_list_image_path: str | None
    _loaded_image_paths: list[str]
    _file_list_root_prefix: str | None
    _file_search_pattern: re.Pattern[str]
    _prev_image_path: str | None
    _viewport_states: dict[str, _ViewportState]
    _brightness_contrast_values: dict[str, tuple[int | None, int | None]]
    _default_state: QtCore.QByteArray

    def __init__(
        self,
        *,
        config_file: Path | None = None,
        config_overrides: dict | None = None,
        file_or_dir: str | None = None,
        output_dir: str | None = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle(__appname__)

        self._config_file, self._config = self._load_config(
            config_file=config_file, config_overrides=config_overrides
        )
        self._config_overrides = config_overrides or {}
        self._shape_color_preview = None

        self._shape_clipboard = ShapeClipboard(parent=self)

        self._label_dialog = self._make_label_dialog(label_history=None)

        self._prev_opened_dir = None
        self._label_list_menu_origin: QtCore.QPoint | None = None
        self._status_mouse_pos = None
        self._docks = self._setup_dock_widgets()

        self.setAcceptDrops(True)
        self._canvas_widgets = self._setup_canvas()

        self._actions = self._setup_actions()
        self._canvas_widgets.empty_state.bind_open_actions(
            open_file=self._actions.open, open_folder=self._actions.open_dir
        )
        self._sync_zoom_mode_actions()
        self._persistent_actions = {
            ("auto_save",): self._actions.save_auto,
            ("with_image_data",): self._actions.save_with_image_data,
            ("keep_prev",): self._actions.toggle_keep_prev_mode,
            ("keep_prev_scale",): self._actions.keep_prev_zoom,
            (
                "keep_prev_brightness_contrast",
            ): self._actions.toggle_keep_prev_brightness_contrast,
            ("canvas", "fill_drawing"): self._actions.fill_drawing,
        }
        self._connect_persistent_actions()
        self._shape_clipboard.availability_changed.connect(
            self._actions.paste.setEnabled
        )
        self._menus = self._setup_menus()

        self._ai_annotation = AiAssistedAnnotationWidget(
            default_model=self._config["ai"]["default"] or "",
            polygon_detail=self._config["mask_polygonization"]["detail"],
            on_model_changed=self._on_ai_model_changed,
            on_output_format_changed=self._canvas_widgets.canvas.set_ai_output_format,
            on_polygon_detail_changed=self._on_ai_polygon_detail_changed,
            parent=self,
        )
        self._canvas_widgets.canvas.set_ai_model_name(
            model_name=self._ai_annotation.current_model_id
        )
        self._canvas_widgets.canvas.set_ai_output_format(
            self._ai_annotation.output_format
        )
        self._canvas_widgets.canvas.set_ai_polygon_detail(
            detail=self._config["mask_polygonization"]["detail"]
        )
        self._ai_annotation.setEnabled(False)
        self._ai_buttons_highlighted = False

        self._ai_text = AiTextToAnnotationWidget(
            on_submit=self._submit_ai_prompt, parent=self
        )
        self._ai_text.set_model_name(model_name=self._config["ai"]["text_model"] or "")
        self._ai_text.model_changed.connect(
            lambda model_name: self._apply_setting_change(
                ("ai", "text_model"), model_name
            )
        )
        self._ai_text.setEnabled(False)

        self._setup_toolbars()

        self._status_bar = self._setup_status_bar()
        self._save_revision = 0
        self._auto_save_path: str | None = None
        self._save_writer = SaveWriter(parent=self)
        self._save_writer.finished.connect(self._on_save_finished)
        self._image_prefetcher = ImagePrefetcher()
        self._model_manager = ModelManager(parent=self)
        self._model_manager.changed.connect(self._refresh_model_availability)
        self._canvas_widgets.canvas.ensure_ai_model_ready = self._ensure_ai_model_ready
        self._ai_annotation.manage_models_requested.connect(self._open_models)
        self._ai_text.manage_models_requested.connect(self._open_models)
        for widget in (self._ai_annotation, self._ai_text):
            widget.download_requested.connect(
                functools.partial(self._download_and_select, select=widget.select_model)
            )
        self._refresh_model_availability()

        self._setup_app_state(file_or_dir=file_or_dir, output_dir=output_dir)

        self._canvas_widgets.zoom_widget.valueChanged.connect(
            self._apply_zoom_to_canvas
        )
        self._canvas_widgets.scroll_area.installEventFilter(self)
        # Fitting between the clicks of a double-click would move the shape
        # out from under the second click, so wait out the interval.
        self._fit_selection_timer = QtCore.QTimer(self)
        self._fit_selection_timer.setSingleShot(True)
        self._fit_selection_timer.setInterval(
            QtGui.QGuiApplication.styleHints().mouseDoubleClickInterval()
        )
        self._fit_selection_timer.timeout.connect(self._apply_deferred_fit_selection)
        self._canvas_widgets.canvas.installEventFilter(self)

        self.populate_mode_actions()

        # colorSchemeChanged fires while setColorScheme is still running, before
        # the new palette is applied, so connect queued: _retheme runs on the next
        # event loop pass, against the live palette.
        QtGui.QGuiApplication.styleHints().colorSchemeChanged.connect(
            self._retheme, QtCore.Qt.ConnectionType.QueuedConnection
        )

    def _retheme(self) -> None:
        # Two things do not follow Qt's palette swap: cached QIcon pixmaps (keyed
        # by the old tint color) and stylesheet'd widgets (QStyleSheetStyle pins
        # their palette at polish time, leaving a palette(...) toolbar on the old
        # scheme).
        QtGui.QPixmapCache.clear()
        app = QtWidgets.QApplication.instance()
        if not isinstance(app, QtWidgets.QApplication):
            return
        for widget in app.allWidgets():
            sheet = widget.styleSheet()
            # Only stylesheets with palette(...) references go stale on a scheme
            # change; re-applying just those avoids re-polishing composite widgets
            # (combo boxes, spin boxes) whose re-polish can invalidate siblings.
            if sheet and "palette(" in sheet:
                widget.setStyleSheet(sheet)  # re-resolve palette refs; also repaints
            else:
                widget.update()
        # The AI-button highlight bakes palette colors into its stylesheet (no
        # palette() ref), so recompute it against the new palette.
        self._highlight_ai_buttons(self._ai_buttons_highlighted)

    def _setup_actions(self) -> _Actions:
        image_actions = QtGui.QActionGroup(self)
        image_actions.setExclusive(False)
        image_actions.setEnabled(False)
        image_action = functools.partial(_utils.new_action, image_actions)
        action = functools.partial(_utils.new_action, self)
        separator = functools.partial(_utils.new_separator, self)
        shortcuts = self._config["shortcuts"]
        ctrl = _utils.modifier_text(Qt.KeyboardModifier.ControlModifier)
        ctrl_shift = _utils.modifier_text(
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
        )

        # lupdate does not see tr() inside f-strings, so the About text is
        # translated before it is assembled.
        tagline = self.tr("Image Polygonal Annotation with Python")
        version = self.tr("Version: %s") % __version__
        author = self.tr("Author: %s") % "Kentaro Wada"
        homepage = self.tr("Homepage")
        documentation = self.tr("Documentation")
        troubleshooting = self.tr("Troubleshooting")
        about = action(
            text=self.tr("&About %s") % __appname__,
            icon="phosphor/info.svg",
            slot=functools.partial(
                QMessageBox.about,
                self,
                self.tr("About %s") % __appname__,
                f"""
<h3>{__appname__}</h3>
<p>{tagline}</p>
<p>{version}</p>
<p>{author}</p>
<p>
    <a href="https://labelme.io">{homepage}</a> |
    <a href="https://labelme.io/docs">{documentation}</a> |
    <a href="https://labelme.io/docs/troubleshoot">{troubleshooting}</a>
</p>
<p>
    <a href="https://github.com/wkentaro/labelme">GitHub</a> |
    <a href="https://x.com/labelmeai">Twitter/X</a>
</p>
""",
            ),
        )
        save = action(
            text=self.tr("&Save"),
            slot=lambda: self._save_label_file(save_as=False),
            shortcut=shortcuts["save"],
            icon="phosphor/floppy-disk.svg",
            tip=self.tr("Save the annotation file"),
            enabled=False,
        )
        save_as = image_action(
            text=self.tr("Save &As…"),
            slot=lambda: self._save_label_file(save_as=True),
            shortcut=shortcuts["save_as"],
            icon="phosphor/floppy-disk-back.svg",
            tip=self.tr("Save the annotation file under a new name"),
        )
        save_auto = action(
            text=self.tr("Save Au&tomatically"),
            tip=self.tr("Save automatically"),
            checkable=True,
            enabled=True,
        )
        save_auto.setChecked(self._config["auto_save"])
        save_with_image_data = action(
            text=self.tr("Embed Image in Annotation File"),
            tip=self.tr("Store a copy of the image inside the annotation file"),
            checkable=True,
            checked=self._config["with_image_data"],
        )
        change_output_dir = action(
            text=self.tr("Change Annotation &Folder…"),
            slot=self.prompt_output_dir,
            shortcut=shortcuts["save_to"],
            icon="phosphor/folders.svg",
            tip=self.tr("Choose where annotation files are read and saved"),
            # The choice is remembered per opened folder, so it needs one.
            enabled=False,
        )
        open_ = action(
            text=self.tr("&Open File…"),
            slot=self._open_file_with_dialog,
            shortcut=shortcuts["open"],
            icon="phosphor/file-image.svg",
            tip=self.tr("Open an image or annotation file"),
        )
        open_dir = action(
            text=self.tr("Open Folder…"),
            slot=self._open_dir_with_dialog,
            shortcut=shortcuts["open_dir"],
            icon="phosphor/folder-open.svg",
            tip=self.tr("Open a folder of images"),
        )
        close = image_action(
            text=self.tr("&Close"),
            slot=self.close_file,
            shortcut=shortcuts["close"],
            icon="phosphor/x-circle.svg",
            tip=self.tr("Close current file"),
        )
        delete_file = action(
            text=self.tr("&Delete Annotation File"),
            toolbar_text=self.tr("Delete File", "toolbar"),
            slot=self.delete_file,
            shortcut=shortcuts["delete_file"],
            icon="phosphor/file-x.svg",
            tip=self.tr("Delete the current annotation file"),
            enabled=False,
        )
        keep_prev_action = action(
            text=self.tr("Keep Previous Annotation"),
            shortcut=shortcuts["toggle_keep_prev_mode"],
            tip=self.tr('Toggle "keep previous annotation" mode'),
            checkable=True,
            checked=self._config["keep_prev"],
        )
        toggle_keep_prev_brightness_contrast = action(
            text=self.tr("Keep Previous Brightness/Contrast"),
            checkable=True,
            checked=self._config["keep_prev_brightness_contrast"],
        )
        delete = action(
            text=self.tr("Delete Shapes"),
            toolbar_text=self.tr("Delete", "toolbar"),
            slot=self.delete_selected_shapes,
            shortcut=shortcuts["delete_shape"],
            icon="phosphor/trash.svg",
            tip=self.tr("Delete the selected shapes"),
            enabled=False,
        )
        edit = action(
            text=self.tr("&Edit Label…"),
            slot=self._edit_label,
            shortcut=shortcuts["edit_label"],
            icon="phosphor/tag.svg",
            tip=self.tr("Modify the label of the selected shape"),
            enabled=False,
        )
        copy = action(
            text=self.tr("Copy to Clipboard"),
            slot=lambda: self._shape_clipboard.store(
                shapes=self._canvas_widgets.canvas.selected_shapes
            ),
            shortcut=shortcuts["copy_shape"],
            icon="phosphor/clipboard.svg",
            tip=self.tr("Place the selected shapes on the clipboard"),
            enabled=False,
        )
        paste = action(
            text=self.tr("Paste from Clipboard"),
            slot=lambda: self._insert_shapes(self._shape_clipboard.paste()),
            shortcut=shortcuts["paste_shape"],
            icon="phosphor/clipboard-text.svg",
            tip=self.tr("Insert the clipboard shapes into this image"),
            enabled=False,
        )
        duplicate = action(
            text=self.tr("Duplicate Shapes"),
            toolbar_text=self.tr("Duplicate", "toolbar"),
            slot=lambda: self._insert_shapes(
                [s.copy() for s in self._canvas_widgets.canvas.selected_shapes]
            ),
            shortcut=shortcuts["duplicate_shape"],
            icon="phosphor/copy.svg",
            tip=self.tr("Create a duplicate of the selected shapes"),
            enabled=False,
        )
        merge = action(
            text=self.tr("Merge Shapes"),
            slot=self._merge_selected_shapes,
            icon="phosphor/unite-duotone.svg",
            tip=self.tr("Merge the selected mask shapes into one"),
            enabled=False,
        )
        lock = action(
            text=self.tr("Lock Shapes"),
            slot=self._toggle_selected_shapes_lock,
            shortcut=shortcuts["lock_shape"],
            icon="phosphor/lock.svg",
            tip=self.tr("Lock the selected shapes against editing, or unlock them"),
            enabled=False,
        )
        undo_last_point = action(
            text=self.tr("Undo Last Point"),
            slot=self._canvas_widgets.canvas.undo_last_point,
            shortcut=shortcuts["undo_last_point"],
            icon="phosphor/backspace.svg",
            tip=self.tr("Undo last drawn point"),
            enabled=False,
        )
        undo = action(
            text=self.tr("Undo"),
            slot=self.undo_shape_edit,
            shortcut=shortcuts["undo"],
            icon="phosphor/arrow-u-up-left.svg",
            tip=self.tr("Undo last add and edit of shape"),
            enabled=False,
        )
        remove_point = action(
            text=self.tr("Delete Selected Point"),
            slot=self.remove_selected_point,
            shortcut=shortcuts["remove_selected_point"],
            icon="phosphor/minus-circle.svg",
            tip=self.tr("Delete the selected point from the polygon or LineStrip"),
            enabled=False,
        )
        add_point_to_edge = action(
            text=self.tr("Add Point to Edge"),
            slot=self._canvas_widgets.canvas.add_point_to_edge,
            icon="phosphor/plus-circle.svg",
            tip=self.tr("Insert a new point at the hovered polygon edge"),
            enabled=False,
        )
        create_mode = image_action(
            text=self.tr("Polygon"),
            slot=lambda: self._switch_canvas_mode(edit=False, create_mode="polygon"),
            shortcut=shortcuts["create_polygon"],
            icon="phosphor/polygon.svg",
            tip=self.tr("Start drawing polygons"),
        )
        edit_mode = image_action(
            text=self.tr("Edit Shapes"),
            toolbar_text=self.tr("Edit", "toolbar"),
            slot=lambda: self._switch_canvas_mode(edit=True, create_mode=None),
            shortcut=shortcuts["edit_shape"],
            icon="phosphor/note-pencil.svg",
            tip=self.tr("Move and edit the selected shapes"),
            enabled=False,
        )
        create_rectangle_mode = image_action(
            text=self.tr("Rectangle"),
            slot=lambda: self._switch_canvas_mode(edit=False, create_mode="rectangle"),
            shortcut=shortcuts["create_rectangle"],
            icon="phosphor/rectangle.svg",
            tip=self.tr("Start drawing rectangles"),
        )
        create_oriented_rectangle_mode = image_action(
            text=self.tr("Oriented Rectangle"),
            slot=lambda: self._switch_canvas_mode(
                edit=False, create_mode="oriented_rectangle"
            ),
            shortcut=shortcuts["create_oriented_rectangle"],
            icon="oriented_rectangle.svg",
            tip=self.tr("Start drawing oriented rectangles"),
        )
        create_circle_mode = image_action(
            text=self.tr("Circle"),
            slot=lambda: self._switch_canvas_mode(edit=False, create_mode="circle"),
            shortcut=shortcuts["create_circle"],
            icon="phosphor/circle.svg",
            tip=self.tr("Start drawing circles"),
        )
        create_line_mode = image_action(
            text=self.tr("Line"),
            slot=lambda: self._switch_canvas_mode(edit=False, create_mode="line"),
            shortcut=shortcuts["create_line"],
            icon="phosphor/line-segment.svg",
            tip=self.tr("Start drawing lines"),
        )
        create_point_mode = image_action(
            text=self.tr("Point"),
            slot=lambda: self._switch_canvas_mode(edit=False, create_mode="point"),
            shortcut=shortcuts["create_point"],
            icon="phosphor/circles-four.svg",
            tip=self.tr("Start drawing points"),
        )
        create_line_strip_mode = image_action(
            text=self.tr("LineStrip"),
            slot=lambda: self._switch_canvas_mode(edit=False, create_mode="linestrip"),
            shortcut=shortcuts["create_linestrip"],
            icon="phosphor/line-segments.svg",
            tip=self.tr(
                "Click to place LineStrip points; hold %s and click to place the"
                " last one."
            )
            % ctrl,
        )
        create_ai_points_to_shape_mode = image_action(
            text=self.tr("AI-Points"),
            slot=lambda: self._switch_canvas_mode(
                edit=False, create_mode="ai_points_to_shape"
            ),
            shortcut=None,
            icon="ai-points.svg",
            tip=self.tr(
                "Click points to segment the object; hold %s and click to finish."
            )
            % ctrl,
        )
        create_ai_box_to_shape_mode = image_action(
            text=self.tr("AI-Box"),
            slot=lambda: self._switch_canvas_mode(
                edit=False, create_mode="ai_box_to_shape"
            ),
            shortcut=None,
            icon="ai-box.svg",
            tip=self.tr("Draw a bounding box to segment object."),
        )
        open_next_img = action(
            text=self.tr("&Next Image"),
            toolbar_text=self.tr("Next", "toolbar"),
            slot=self._open_next_image,
            shortcut=shortcuts["open_next"],
            icon="phosphor/arrow-fat-right.svg",
            tip=self.tr("Open the next image (hold %s to copy the current Shapes)")
            % ctrl_shift,
            enabled=False,
        )
        open_prev_img = action(
            text=self.tr("&Previous Image"),
            toolbar_text=self.tr("Previous", "toolbar"),
            slot=self._open_prev_image,
            shortcut=shortcuts["open_prev"],
            icon="phosphor/arrow-fat-left.svg",
            tip=self.tr("Open the previous image (hold %s to copy the current Shapes)")
            % ctrl_shift,
            enabled=False,
        )
        keep_prev_zoom = action(
            text=self.tr("&Keep Previous Zoom"),
            checkable=True,
            checked=self._config["keep_prev_scale"],
        )
        fit_window = image_action(
            text=self.tr("Fit to &Window"),
            slot=self.set_fit_window_mode,
            shortcut=shortcuts["fit_window"],
            icon="phosphor/frame-corners.svg",
            tip=self.tr("Keep the whole image visible when the window is resized"),
            checkable=True,
        )
        fit_selection = image_action(
            text=self.tr("Fit to S&election"),
            slot=self.set_fit_selection_mode,
            shortcut=shortcuts["fit_selection"],
            icon="phosphor/scan.svg",
            tip=self.tr("Zoom to the selected shapes whenever the selection changes"),
            checkable=True,
        )
        brightness_contrast = image_action(
            text=self.tr("&Brightness/Contrast…"),
            slot=self.open_brightness_contrast_dialog,
            shortcut=None,
            icon="brightness-contrast.svg",
            tip=self.tr("Adjust brightness and contrast"),
        )
        zoom_in = image_action(
            text=self.tr("Zoom &In"),
            slot=lambda _: self._add_zoom(increment=1.1, pos=None),
            shortcut=shortcuts["zoom_in"],
            icon="phosphor/magnifying-glass-plus.svg",
            tip=self.tr("Make the image appear larger"),
        )
        zoom_out = image_action(
            text=self.tr("&Zoom Out"),
            slot=lambda _: self._add_zoom(increment=0.9, pos=None),
            shortcut=shortcuts["zoom_out"],
            icon="phosphor/magnifying-glass-minus.svg",
            tip=self.tr("Make the image appear smaller"),
        )
        zoom_org = image_action(
            text=self.tr("&Actual Size"),
            slot=self._set_zoom_to_original,
            shortcut=shortcuts["zoom_to_original"],
            icon="phosphor/image-square.svg",
            tip=self.tr("Show the image at 100%"),
        )
        reset_layout = action(
            text=self.tr("Reset Layout"),
            slot=self._reset_layout,
            icon="phosphor/layout-duotone.svg",
        )
        fill_drawing = action(
            text=self.tr("Fill Drawing Polygon"),
            tip=self.tr("Fill polygon while drawing"),
            checkable=True,
            enabled=True,
            checked=self._config["canvas"]["fill_drawing"],
        )
        self._canvas_widgets.canvas.set_fill_drawing(
            value=self._config["canvas"]["fill_drawing"]
        )
        hide_all = action(
            text=self.tr("&Hide Shapes"),
            slot=functools.partial(self.toggle_shape_visibility, value=False),
            shortcut=shortcuts["hide_all_shapes"],
            icon="phosphor/eye-slash.svg",
            tip=self.tr("Hide all shapes"),
        )
        show_all = action(
            text=self.tr("&Show Shapes"),
            slot=functools.partial(self.toggle_shape_visibility, value=True),
            shortcut=shortcuts["show_all_shapes"],
            icon="phosphor/eye.svg",
            tip=self.tr("Show all shapes"),
        )
        toggle_all = action(
            text=self.tr("&Toggle Shapes"),
            slot=functools.partial(self.toggle_shape_visibility, value=None),
            shortcut=shortcuts["toggle_all_shapes"],
            icon="phosphor/toggle-right.svg",
            tip=self.tr("Toggle all shapes"),
        )

        select_neighbor = self._canvas_widgets.canvas.select_neighbor_shape
        select_neighbor_actions = (
            action(
                text=self.tr("Select Shape Above"),
                slot=functools.partial(select_neighbor, key=Qt.Key.Key_Up),
                shortcut=shortcuts["select_shape_up"],
                icon="phosphor/arrow-up.svg",
                tip=self.tr("Select the nearest shape above the selection"),
            ),
            action(
                text=self.tr("Select Shape Below"),
                slot=functools.partial(select_neighbor, key=Qt.Key.Key_Down),
                shortcut=shortcuts["select_shape_down"],
                icon="phosphor/arrow-down.svg",
                tip=self.tr("Select the nearest shape below the selection"),
            ),
            action(
                text=self.tr("Select Shape to the Left"),
                slot=functools.partial(select_neighbor, key=Qt.Key.Key_Left),
                shortcut=shortcuts["select_shape_left"],
                icon="phosphor/arrow-left.svg",
                tip=self.tr("Select the nearest shape left of the selection"),
            ),
            action(
                text=self.tr("Select Shape to the Right"),
                slot=functools.partial(select_neighbor, key=Qt.Key.Key_Right),
                shortcut=shortcuts["select_shape_right"],
                icon="phosphor/arrow-right.svg",
                tip=self.tr("Select the nearest shape right of the selection"),
            ),
        )

        shapes_present_actions = QtGui.QActionGroup(self)
        shapes_present_actions.setExclusive(False)
        shapes_present_actions.addAction(hide_all)
        shapes_present_actions.addAction(show_all)
        shapes_present_actions.addAction(toggle_all)
        for select_action in select_neighbor_actions:
            shapes_present_actions.addAction(select_action)

        def update_shapes_present_actions() -> None:
            shapes_present_actions.setEnabled(not self.has_no_shapes())

        label_model = self._docks.label_list.model()
        label_model.rowsInserted.connect(update_shapes_present_actions)
        label_model.rowsRemoved.connect(update_shapes_present_actions)
        label_model.modelReset.connect(update_shapes_present_actions)
        update_shapes_present_actions()

        zoom_widget = self._canvas_widgets.zoom_widget
        # The fit modes sit beside the field as icon buttons; the pressed one is
        # the active mode.
        zoom_row = QtWidgets.QHBoxLayout()
        zoom_row.setSpacing(0)
        for fit_action in (fit_window, fit_selection):
            fit_button = QtWidgets.QToolButton()
            fit_button.setDefaultAction(fit_action)
            fit_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            zoom_row.addWidget(fit_button)
        zoom_row.addWidget(zoom_widget)
        # The caption names the active fit mode, so the toolbar shows the
        # sticky zoom state in words.
        self._zoom_mode_label = QtWidgets.QLabel()
        self._zoom_mode_captions = {
            _ZoomMode.FIT_WINDOW: self.tr("Fit to Window"),
            _ZoomMode.FIT_SELECTION: self.tr("Fit to Selection"),
            _ZoomMode.MANUAL_ZOOM: self.tr("Zoom"),
        }
        self._zoom_mode_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._zoom_mode_label.setBuddy(zoom_widget)
        zoom_box_layout = QtWidgets.QVBoxLayout()
        zoom_box_layout.addWidget(self._zoom_mode_label)
        zoom_box_layout.addLayout(zoom_row)
        zoom_widget_action = QtWidgets.QWidgetAction(image_actions)
        zoom_widget_action.setDefaultWidget(QtWidgets.QWidget())
        zoom_widget_action.defaultWidget().setLayout(zoom_box_layout)

        self._zoom_mode = _ZoomMode.FIT_WINDOW

        self._canvas_widgets.canvas.vertex_selected.connect(remove_point.setEnabled)
        self._canvas_widgets.canvas.edge_selected.connect(add_point_to_edge.setEnabled)

        draw = [
            ("polygon", create_mode),
            ("rectangle", create_rectangle_mode),
            ("oriented_rectangle", create_oriented_rectangle_mode),
            ("circle", create_circle_mode),
            ("point", create_point_mode),
            ("line", create_line_mode),
            ("linestrip", create_line_strip_mode),
            ("ai_points_to_shape", create_ai_points_to_shape_mode),
            ("ai_box_to_shape", create_ai_box_to_shape_mode),
        ]
        # Both menus follow the platform Edit-menu convention: history first,
        # then the clipboard group, then the actions that alter a shape.
        history = (undo, undo_last_point)
        clipboard = (copy, paste, duplicate)
        context_menu = (
            *[draw_action for _, draw_action in draw],
            edit_mode,
            separator(),
            *history,
            separator(),
            *clipboard,
            separator(),
            edit,
            delete,
            merge,
            lock,
            add_point_to_edge,
            remove_point,
        )
        edit_menu = (
            separator(),
            *history,
            separator(),
            *clipboard,
            separator(),
            edit,
            delete,
            merge,
            lock,
            remove_point,
            separator(),
            *select_neighbor_actions,
            separator(),
            keep_prev_action,
        )
        return _Actions(
            about=about,
            save=save,
            save_as=save_as,
            save_auto=save_auto,
            save_with_image_data=save_with_image_data,
            change_output_dir=change_output_dir,
            open=open_,
            close=close,
            delete_file=delete_file,
            toggle_keep_prev_mode=keep_prev_action,
            toggle_keep_prev_brightness_contrast=toggle_keep_prev_brightness_contrast,
            delete=delete,
            edit=edit,
            copy=copy,
            paste=paste,
            duplicate=duplicate,
            merge=merge,
            lock=lock,
            undo_last_point=undo_last_point,
            undo=undo,
            remove_point=remove_point,
            add_point_to_edge=add_point_to_edge,
            create_mode=create_mode,
            edit_mode=edit_mode,
            create_rectangle_mode=create_rectangle_mode,
            create_oriented_rectangle_mode=create_oriented_rectangle_mode,
            create_circle_mode=create_circle_mode,
            create_line_mode=create_line_mode,
            create_point_mode=create_point_mode,
            create_line_strip_mode=create_line_strip_mode,
            create_ai_points_to_shape_mode=create_ai_points_to_shape_mode,
            create_ai_box_to_shape_mode=create_ai_box_to_shape_mode,
            open_next_img=open_next_img,
            open_prev_img=open_prev_img,
            keep_prev_zoom=keep_prev_zoom,
            fit_window=fit_window,
            fit_selection=fit_selection,
            brightness_contrast=brightness_contrast,
            zoom_in=zoom_in,
            zoom_out=zoom_out,
            zoom_org=zoom_org,
            reset_layout=reset_layout,
            fill_drawing=fill_drawing,
            hide_all=hide_all,
            show_all=show_all,
            toggle_all=toggle_all,
            open_dir=open_dir,
            zoom_widget_action=zoom_widget_action,
            draw=draw,
            image=image_actions,
            context_menu=context_menu,
            edit_menu=edit_menu,
        )

    def _setup_menus(self) -> _Menus:
        action = functools.partial(_utils.new_action, self)
        separator = functools.partial(_utils.new_separator, self)
        shortcuts = self._config["shortcuts"]

        quit_ = action(
            text=self.tr("&Quit"),
            slot=self.close,
            shortcut=shortcuts["quit"],
            icon="phosphor/power.svg",
            tip=self.tr("Quit application"),
        )
        settings_editable = self._is_settings_editable
        open_config = action(
            text=self.tr("Settings…"),
            slot=self._open_settings,
            shortcut="Ctrl+," if platform.system() == "Darwin" else "Ctrl+Shift+,",
            icon="phosphor/gear-six.svg",
            tip=(
                self.tr("Edit settings")
                if settings_editable
                else self.tr("Settings are managed via --config for this session")
            ),
            enabled=True,
        )
        open_config.setMenuRole(QtGui.QAction.MenuRole.PreferencesRole)
        open_models = action(
            text=self.tr("AI Models…"),
            slot=self._open_models,
            icon="phosphor/cube.svg",
            tip=self.tr("Download or delete AI models"),
        )
        help_ = action(
            text=self.tr("&Tutorial"),
            slot=self.tutorial,
            icon="phosphor/question.svg",
            tip=self.tr("Show tutorial page"),
        )

        file_menu = self.menuBar().addMenu(self.tr("&File"))
        edit_menu = self.menuBar().addMenu(self.tr("&Edit"))
        view_menu = self.menuBar().addMenu(self.tr("&View"))
        help_menu = self.menuBar().addMenu(self.tr("&Help"))
        label_menu = QtWidgets.QMenu()
        label_menu.addActions(
            (self._actions.edit, self._actions.delete, self._actions.lock)
        )
        self._docks.label_list.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self._docks.label_list.customContextMenuRequested.connect(
            self.show_label_list_menu
        )

        file_menu.addActions(
            (
                self._actions.open,
                self._actions.open_next_img,
                self._actions.open_prev_img,
                self._actions.open_dir,
                self._actions.save,
                self._actions.save_as,
                self._actions.save_auto,
                self._actions.change_output_dir,
                self._actions.save_with_image_data,
                self._actions.close,
                self._actions.delete_file,
                separator(),
                open_config,
                open_models,
                separator(),
                quit_,
            )
        )
        help_menu.addActions((help_, self._actions.about))
        view_menu.addActions(
            (
                self._docks.flag_dock.toggleViewAction(),
                self._docks.label_dock.toggleViewAction(),
                self._docks.shape_dock.toggleViewAction(),
                self._docks.file_dock.toggleViewAction(),
                separator(),
                self._actions.reset_layout,
                separator(),
                self._actions.fill_drawing,
                separator(),
                self._actions.hide_all,
                self._actions.show_all,
                self._actions.toggle_all,
                separator(),
                self._actions.zoom_in,
                self._actions.zoom_out,
                self._actions.zoom_org,
                self._actions.keep_prev_zoom,
                separator(),
                self._actions.fit_window,
                self._actions.fit_selection,
                separator(),
                self._actions.brightness_contrast,
                self._actions.toggle_keep_prev_brightness_contrast,
                # macOS appends Enter Full Screen here; the separator keeps its
                # SF Symbol from indenting the icon-less items above it.
                separator(),
            )
        )

        self._canvas_widgets.canvas.context_menu.addActions(self._actions.context_menu)

        return _Menus(
            file=file_menu,
            edit=edit_menu,
            view=view_menu,
            help=help_menu,
            label_list=label_menu,
        )

    def _setup_toolbars(self) -> None:
        separator = functools.partial(_utils.new_separator, self)
        select_ai_model = QtWidgets.QWidgetAction(self)
        select_ai_model.setDefaultWidget(self._ai_annotation)

        ai_prompt_action = QtWidgets.QWidgetAction(self)
        ai_prompt_action.setDefaultWidget(self._ai_text)

        self.addToolBar(
            Qt.ToolBarArea.TopToolBarArea,
            ToolBar(
                name="Tools",
                title=self.tr("Tools"),
                overflow_label=self.tr("More tools"),
                actions=[
                    self._actions.open,
                    self._actions.open_dir,
                    self._actions.open_prev_img,
                    self._actions.open_next_img,
                    self._actions.save,
                    self._actions.delete_file,
                    separator(),
                    self._actions.edit_mode,
                    self._actions.duplicate,
                    self._actions.delete,
                    self._actions.undo,
                    self._actions.brightness_contrast,
                    separator(),
                    self._actions.zoom_widget_action,
                    separator(),
                    select_ai_model,
                    separator(),
                    ai_prompt_action,
                ],
                font_base=self.font(),
            ),
        )
        self.addToolBar(
            Qt.ToolBarArea.LeftToolBarArea,
            ToolBar(
                name="CreateShapeTools",
                title=self.tr("Shape Tools"),
                overflow_label=self.tr("More shape tools"),
                actions=[
                    *[
                        a
                        for mode, a in self._actions.draw
                        if not mode.startswith("ai_")
                    ],
                    separator(),
                    *[a for mode, a in self._actions.draw if mode.startswith("ai_")],
                ],
                orientation=Qt.Orientation.Vertical,
                button_style=Qt.ToolButtonStyle.ToolButtonTextUnderIcon,
                font_base=self.font(),
            ),
        )
        self._ai_annotation.hover_highlight_requested.connect(
            self._highlight_ai_buttons
        )

    def _setup_app_state(
        self,
        *,
        file_or_dir: str | None,
        output_dir: str | None,
    ) -> None:
        self._output_dir = Path(output_dir) if output_dir else None

        self._image = QtGui.QImage()
        self._annotation = None
        self._label_file_path = None
        self._failed_save_path = None
        self._image_path = None
        self._file_list_image_path = None
        self._loaded_image_paths = []
        # Annotated images the search box hides, found when the list is
        # rebuilt and kept current by saves and deletions; the visible ones
        # are counted from their check marks.
        self._hidden_annotated_paths: set[str] = set()
        self._file_list_root_prefix = None
        self._file_search_pattern = re.compile("")
        self._prev_image_path = None
        self._viewport_states = {}
        self._brightness_contrast_values = {}

        if self._config["file_search"]:
            self._docks.file_search.setText(self._config["file_search"])

        self._default_state = self.saveState()
        #
        # Restore the window geometry and dock layout (separate from the user
        # Config; this Qt store holds only window state).
        self._window_state = QtCore.QSettings("labelme", "labelme")
        #
        # Bump this when dock/toolbar layout changes to reset window state
        # for users upgrading from an older version.
        SETTINGS_VERSION: Final[int] = 1
        if self._window_state.value("settingsVersion", 0, type=int) != SETTINGS_VERSION:
            self._reset_layout()
            self._window_state.setValue("settingsVersion", SETTINGS_VERSION)
        #
        screen = QtGui.QGuiApplication.primaryScreen()
        default = _default_window_geometry(
            screen.availableGeometry(),
            toolbar_width=max(
                toolbar.sizeHint().width()
                for toolbar in self.findChildren(ToolBar)
                if toolbar.orientation() == Qt.Orientation.Horizontal
            ),
        )
        self.resize(
            cast(
                QtCore.QSize,
                self._window_state.value(WINDOW_SIZE_KEY, default.size()),
            )
        )
        self.move(
            cast(
                QtCore.QPoint,
                self._window_state.value(WINDOW_POSITION_KEY, default.topLeft()),
            )
        )
        self.restoreState(
            cast(
                QtCore.QByteArray,
                self._window_state.value(WINDOW_LAYOUT_KEY, QtCore.QByteArray()),
            )
        )
        # Recover window position when the saved screen is no longer connected.
        if not any(
            s.availableGeometry().intersects(self.frameGeometry())
            for s in QtWidgets.QApplication.screens()
        ) and (primary_screen := QtWidgets.QApplication.primaryScreen()):
            self.move(primary_screen.availableGeometry().topLeft())

        if not file_or_dir:
            return
        if self._output_dir is not None and not is_label_file_path(
            filename=file_or_dir
        ):
            # --output replaces the folder's remembered Annotation Folder, so
            # opening the folder restores it like any other choice. It must
            # exist, or the restore would skip it as missing.
            self._output_dir.mkdir(parents=True, exist_ok=True)
            self._remember_output_dir(
                opened_dir=file_or_dir
                if Path(file_or_dir).is_dir()
                else str(Path(file_or_dir).parent)
            )
        self._load_from_file_or_dir(file_or_dir=file_or_dir)

    def _setup_status_bar(self) -> _StatusBarWidgets:
        message = QtWidgets.QLabel(self.tr("%s started.") % __appname__)
        stats = StatusStats()
        self.statusBar().addWidget(message, 1)
        self.statusBar().addWidget(stats, 0)
        save = QtWidgets.QLabel()
        save.setTextFormat(Qt.TextFormat.PlainText)
        retry = QtWidgets.QToolButton()
        retry.setText(self.tr("Retry"))
        retry.clicked.connect(self._retry_save)
        retry.hide()
        self.statusBar().addPermanentWidget(save)
        self.statusBar().addPermanentWidget(retry)
        self.statusBar().show()
        return _StatusBarWidgets(message=message, stats=stats, save=save, retry=retry)

    def _setup_canvas(self) -> _CanvasWidgets:
        zoom_widget = ZoomWidget()

        canvas = Canvas(
            epsilon=self._config["epsilon"],
            double_click=self._config["canvas"]["double_click"],
            num_backups=self._config["canvas"]["num_backups"],
            crosshair=self._config["canvas"]["crosshair"],
            allow_out_of_bounds_points=self._config["canvas"][
                "allow_out_of_bounds_points"
            ],
        )
        canvas.set_point_size(point_size=self._config["shape"]["point_size"])
        canvas.set_show_labels(value=self._config["shape"]["show_labels"])
        canvas.set_ai_existing_shape_suppression(
            enabled=self._config["ai"]["suppress_existing_shape_matches"]
        )
        canvas.set_draft_palette(
            palette=Palette(
                line=QtGui.QColor(*self._config["shape"]["line_color"]),
                fill=QtGui.QColor(*self._config["shape"]["fill_color"]),
                select_line=QtGui.QColor(*self._config["shape"]["select_line_color"]),
                select_fill=QtGui.QColor(*self._config["shape"]["select_fill_color"]),
                vertex_fill=QtGui.QColor(*self._config["shape"]["vertex_fill_color"]),
                hvertex_fill=QtGui.QColor(*self._config["shape"]["hvertex_fill_color"]),
            )
        )
        canvas.set_color_resolver(
            resolver=lambda label: self._get_rgb_by_label(
                label=label, unique_label_list=self._docks.unique_label_list
            )
        )
        canvas.zoom_request.connect(self._zoom_requested)
        canvas.mouse_moved.connect(self._update_status_stats)
        canvas.status_updated.connect(
            lambda text: self._status_bar.message.setText(text)
        )

        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidget(canvas)
        scroll_area.setWidgetResizable(True)
        scroll_bars = {
            Qt.Orientation.Vertical: scroll_area.verticalScrollBar(),
            Qt.Orientation.Horizontal: scroll_area.horizontalScrollBar(),
        }
        canvas.scroll_request.connect(self._on_scroll_request)
        canvas.pan_request.connect(self._on_pan_request)

        canvas.new_shape.connect(self._on_new_shape)
        canvas.inference_produced_no_shapes.connect(
            self._on_inference_produced_no_shapes
        )
        # The preview path emits this from inside paintEvent (an active
        # QPainter); a queued connection defers the status-bar update until
        # after the paint cycle so it never mutates UI mid-paint.
        canvas.inference_failed.connect(
            self._on_inference_failed,
            Qt.ConnectionType.QueuedConnection,
        )
        canvas.degenerate_shape_rejected.connect(
            lambda: self.show_status_message(
                self.tr("Shape had no area; nothing created."), delay=5000
            )
        )
        canvas.shape_moved.connect(self.mark_dirty)
        canvas.selection_changed.connect(self._on_shape_selection_changed)
        canvas.shape_moved.connect(self._cancel_deferred_fit_selection)
        canvas.shape_double_clicked.connect(self._edit_label)
        canvas.drawing_polygon.connect(self._on_drawing_polygon_changed)

        empty_state = EmptyStateWidget()
        surface = QtWidgets.QStackedWidget()
        surface.addWidget(empty_state)
        surface.addWidget(scroll_area)
        surface.setCurrentWidget(empty_state)
        self.setCentralWidget(surface)

        return _CanvasWidgets(
            canvas=canvas,
            empty_state=empty_state,
            scroll_area=scroll_area,
            surface=surface,
            zoom_widget=zoom_widget,
            scroll_bars=scroll_bars,
        )

    def _setup_dock_widgets(self) -> _DockWidgets:
        flag_list = QtWidgets.QListWidget()
        flag = QtWidgets.QDockWidget(self.tr("Flags"), self)
        flag.setObjectName("Flags")
        self._load_flags(flags={}, widget=flag_list)
        flag.setWidget(flag_list)
        flag_list.itemChanged.connect(self.mark_dirty)

        label_list = LabelListWidget()
        label_list.item_selection_changed.connect(self._label_selection_changed)
        label_list.item_double_clicked.connect(self._edit_label)
        label_list.item_changed.connect(self._on_label_item_changed)
        label_list.item_dropped.connect(self._on_label_order_changed)
        shape = QtWidgets.QDockWidget(self.tr("Shape List"), self)
        shape.setObjectName("Labels")
        shape.setWidget(label_list)

        unique_label_list = UniqueLabelQListWidget()
        unique_label_list.setToolTip(
            self.tr(
                "Choose a label to start drawing with it. "
                "Press 'Esc' to clear the selection."
            )
        )
        if self._config["labels"]:
            for lbl in self._config["labels"]:
                unique_label_list.add_label_item(
                    label=lbl,
                    color=self._get_rgb_by_label(
                        label=lbl, unique_label_list=unique_label_list
                    ),
                )
        label = QtWidgets.QDockWidget(self.tr("Label List"), self)
        label.setObjectName("Label List")
        label.setWidget(unique_label_list)

        annotation_folder_footer = AnnotationFolderFooter(
            on_choose=self.prompt_output_dir, on_next_to_images=self._clear_output_dir
        )
        # Shown once a folder is open; see _refresh_file_list.
        annotation_folder_footer.hide()
        file_search = QtWidgets.QLineEdit()
        file_search.setPlaceholderText(self.tr("Search Filename"))
        file_search.textChanged.connect(self._on_file_search_changed)
        file_search_error = QtWidgets.QLabel(
            self.tr("Invalid regular expression. Previous search kept.")
        )
        file_search_error.setWordWrap(True)
        file_search_error.hide()
        file_list = QtWidgets.QListWidget()
        file_list.currentItemChanged.connect(self._load_selected_image)
        file_list_layout = QtWidgets.QVBoxLayout()
        file_list_layout.setContentsMargins(0, 0, 0, 0)
        file_list_layout.setSpacing(0)
        file_list_layout.addWidget(file_search)
        file_list_layout.addWidget(file_search_error)
        file_list_layout.addWidget(file_list)
        file_list_layout.addWidget(annotation_folder_footer)
        file = QtWidgets.QDockWidget(self.tr("Image List"), self)
        file.setObjectName("Files")
        file_list_container = QtWidgets.QWidget()
        file_list_container.setLayout(file_list_layout)
        file.setWidget(file_list_container)

        for config_key, dock_widget in [
            ("flag_dock", flag),
            ("label_dock", label),
            ("shape_dock", shape),
            ("file_dock", file),
        ]:
            features = QtWidgets.QDockWidget.DockWidgetFeature()
            if self._config[config_key]["closable"]:
                features = (
                    features
                    | QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetClosable
                )
            if self._config[config_key]["floatable"]:
                features = (
                    features
                    | QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetFloatable
                )
            if self._config[config_key]["movable"]:
                features = (
                    features | QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetMovable
                )
            dock_widget.setFeatures(features)
            if self._config[config_key]["show"] is False:
                dock_widget.setVisible(False)
            self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock_widget)

        return _DockWidgets(
            flag_dock=flag,
            flag_list=flag_list,
            shape_dock=shape,
            label_list=label_list,
            label_dock=label,
            unique_label_list=unique_label_list,
            file_dock=file,
            annotation_folder_footer=annotation_folder_footer,
            file_search=file_search,
            file_search_error=file_search_error,
            file_list=file_list,
        )

    def _load_config(
        self, *, config_file: Path | None, config_overrides: dict | None
    ) -> tuple[Path | None, dict]:
        overrides = config_overrides or {}
        try:
            return config_file, _config.load_config(
                config_file=config_file, config_overrides=overrides
            )
        except Exception as error:
            logger.warning("Failed to load config: {}", error)
            message = str(error)

        fallback = _try_load_config(config_file=None, config_overrides=overrides)
        # Command-line errors must never be repaired by deleting file settings,
        # so offer a reset only when the file fails on its own.
        can_reset = (
            fallback is not None
            and config_file is not None
            and _try_load_config(config_file=config_file, config_overrides={}) is None
        )
        if fallback is None:
            fallback = _config.load_config(config_file=None, config_overrides={})

        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Icon.Warning)
        msg_box.setWindowTitle(__appname__)
        msg_box.setTextFormat(Qt.TextFormat.PlainText)
        msg_box.setText(self.tr("Your settings couldn’t be loaded."))
        source = str(config_file) if config_file else self.tr("Command-line settings")
        msg_box.setInformativeText(
            self.tr(
                "You can use default settings for now. Resetting saves a backup "
                "of your configuration file first."
            )
            + f"\n\n{source}\n{message}"
        )
        keep_file = msg_box.addButton(
            self.tr("Continue with Defaults"), QMessageBox.ButtonRole.AcceptRole
        )
        reset_all = msg_box.addButton(
            self.tr("Back Up and Reset"), QMessageBox.ButtonRole.ResetRole
        )
        reset_all.setEnabled(can_reset)
        msg_box.setDefaultButton(keep_file)
        msg_box.setEscapeButton(keep_file)
        while True:
            msg_box.exec()
            if msg_box.clickedButton() is not reset_all:
                return None, fallback
            assert config_file is not None
            try:
                backup = _config.reset_config(config_file=config_file)
            except Exception as error:
                msg_box.setInformativeText(
                    self.tr("Could not reset the Config File.\n%s") % error
                )
                continue
            QMessageBox.information(
                self,
                self.tr("Back Up and Reset"),
                self.tr("Configuration backup saved to %s") % backup.resolve(),
            )
            return config_file, fallback

    # Support Functions

    def has_no_shapes(self) -> bool:
        return not len(self._docks.label_list)

    def populate_mode_actions(self) -> None:
        self._canvas_widgets.canvas.context_menu.clear()
        self._canvas_widgets.canvas.context_menu.addActions(self._actions.context_menu)
        self._menus.edit.clear()
        actions = (
            *[draw_action for _, draw_action in self._actions.draw],
            self._actions.edit_mode,
            *self._actions.edit_menu,
        )
        self._menus.edit.addActions(actions)

    def _get_window_title(self, *, dirty: bool) -> str:
        file_list = self._docks.file_list
        file_index = file_list.currentRow() if file_list.currentItem() else None
        return _format_window_title(
            image_path=self._image_path,
            file_index=file_index,
            file_count=file_list.count(),
            dirty=dirty,
        )

    def mark_dirty(self) -> None:
        self._save_revision += 1
        self._actions.undo.setEnabled(self._canvas_widgets.canvas.can_restore_shape)
        self._is_changed = True
        self._actions.save.setEnabled(True)
        self.setWindowTitle(self._get_window_title(dirty=True))
        if self._actions.save_auto.isChecked():
            assert self._image_path is not None
            self._queue_auto_save(
                label_path=self._auto_save_path
                or _resolve_label_path(
                    image_path=self._file_list_image_path or self._image_path,
                    output_dir=self._output_dir,
                    root_prefix=self._file_list_root_prefix,
                )
            )
        else:
            self._status_bar.save.setText(self.tr("Unsaved changes"))
            self._status_bar.retry.setVisible(self._failed_save_path is not None)

    def _queue_auto_save(self, *, label_path: str) -> None:
        try:
            request = self._capture_save_request(label_path=label_path)
        except (LabelFileError, OSError, ValueError) as error:
            self._show_save_failure(label_path=label_path, error=error)
            return
        self._status_bar.save.setText(self.tr("Saving…"))
        self._status_bar.save.setToolTip(label_path)
        self._status_bar.retry.hide()
        self._save_writer.submit(request=request, revision=self._save_revision)

    def _on_save_finished(
        self, request: SaveRequest, revision: int, error: BaseException | None, /
    ) -> None:
        # Older writes may finish after further edits; only the latest revision
        # can clear the dirty marker or replace its failure status.
        if revision != self._save_revision:
            return
        if error is not None:
            self._show_save_failure(label_path=request.filename, error=error)
            return
        self._record_saved_annotation(label_path=request.filename)

    def _wait_for_save(self) -> None:
        if not self._save_writer.is_busy:
            return
        dialog = QtWidgets.QProgressDialog(self.tr("Saving…"), "", 0, 0, self)
        dialog.setCancelButton(None)
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.setMinimumDuration(0)
        # Completion while the dialog opens must wait for its event loop.
        self._save_writer.idle.connect(
            dialog.accept, Qt.ConnectionType.QueuedConnection
        )
        try:
            # Dismissing the progress window cannot bypass the write barrier.
            while self._save_writer.is_busy:
                dialog.exec()
        finally:
            self._save_writer.idle.disconnect(dialog.accept)
            dialog.deleteLater()

    def mark_clean(self) -> None:
        canvas = self._canvas_widgets.canvas
        self._actions.undo.setEnabled(
            not canvas.is_drawing and canvas.can_restore_shape
        )
        self._is_changed = False
        self._actions.save.setEnabled(False)
        self.setWindowTitle(self._get_window_title(dirty=False))

    def show_status_message(self, message: str, /, *, delay: int = 500) -> None:
        self.statusBar().showMessage(message, delay)

    def _submit_ai_prompt(self, _: bool, /) -> None:  # noqa: FBT001 -- submit callback receives the Qt clicked flag
        create_mode = self._canvas_widgets.canvas.create_mode
        shape_type = _resolve_text_annotation_shape_type(
            create_mode=create_mode,
            ai_output_format=self._ai_annotation.output_format,
        )
        if shape_type is None:
            logger.warning("Unsupported create_mode={!r}", create_mode)
            return

        texts = self._ai_text.get_text_prompt().split(",")

        model_name: str = self._ai_text.get_model_name()
        if not self._ensure_ai_model_ready(model_name):
            return
        if (
            self._text_osam_session is None
            or self._text_osam_session.model_name != model_name
        ):
            self._text_osam_session = _automation.OsamSession(model_name=model_name)

        try:
            shapes = _automation.propose_shapes_from_texts(
                session=self._text_osam_session,
                image=_utils.img_qt_to_rgb_arr(self._image),
                image_id=str(hash(self._image_path)),
                texts=texts,
                shape_type=shape_type,
                existing_shapes=self._canvas_widgets.canvas.shapes,
                iou_threshold=self._ai_text.get_iou_threshold(),
                score_threshold=self._ai_text.get_score_threshold(),
                image_size=(
                    None
                    if self._config["canvas"]["allow_out_of_bounds_points"]
                    else (self._image.width(), self._image.height())
                ),
                polygon_detail=self._config["mask_polygonization"]["detail"],
            )
        except _automation.MaskOutputUnavailableError:
            QtWidgets.QMessageBox.warning(
                self,
                self.tr("Mask Output Unavailable"),
                self.tr(
                    "%s only detects bounding boxes and cannot create "
                    "'%s' Shapes.\n\n"
                    "Switch the AI Text Prompt model to 'SAM3 (smart)', "
                    "or set the output format to 'Rectangle'."
                )
                % (self._ai_text.get_model_display_name(), shape_type),
            )
            return
        except Exception as e:
            logger.opt(exception=e).error("AI text inference failed")
            self._on_inference_failed(f"{type(e).__name__}: {e}")
            return

        apply_default_flags(shapes=shapes, label_flags=self._config["label_flags"])
        self._commit_shapes([*self._canvas_widgets.canvas.shapes, *shapes])

    def reset_state(self) -> None:
        self._auto_save_path = None
        self._docks.label_list.clear()
        self._annotation = None
        self._image = QtGui.QImage()
        self._image_path = None
        self._file_list_image_path = None
        self._label_file_path = None
        self._failed_save_path = None
        self._status_bar.save.clear()
        self._status_bar.retry.hide()
        self._canvas_widgets.canvas.reset_state()

    # Callbacks

    def undo_shape_edit(self) -> None:
        self._canvas_widgets.canvas.restore_last_shape()
        self._commit_shapes(self._canvas_widgets.canvas.shapes)

    def tutorial(self) -> None:
        url = "https://github.com/labelmeai/labelme/tree/main/examples/tutorial"  # NOQA
        webbrowser.open(url)

    def _on_drawing_polygon_changed(self, drawing: bool, /) -> None:  # noqa: FBT001 -- Canvas.drawing_polygon slot
        self._actions.edit_mode.setEnabled(not drawing)
        self._actions.undo_last_point.setEnabled(drawing)
        self._actions.undo.setEnabled(
            not drawing and self._canvas_widgets.canvas.can_restore_shape
        )
        self._actions.delete.setEnabled(not drawing)
        self._actions.merge.setEnabled(
            not drawing
            and can_merge_shapes(self._canvas_widgets.canvas.selected_shapes)
        )

    def _switch_canvas_mode(self, *, edit: bool, create_mode: str | None) -> None:
        self._canvas_widgets.canvas.set_editing(value=edit, create_mode=create_mode)
        self._refresh_status_stats()
        if edit:
            for _, draw_action in self._actions.draw:
                draw_action.setEnabled(True)
        else:
            for draw_mode, draw_action in self._actions.draw:
                draw_action.setEnabled(create_mode != draw_mode)
        # Keep edit_mode disabled while a partial shape is alive so the user
        # can't abandon it mid-draw.
        self._actions.edit_mode.setEnabled(
            not edit and not self._canvas_widgets.canvas.is_drawing
        )
        self._ai_text.setEnabled(
            not edit
            and create_mode
            in (*typing.get_args(_TextToAnnotationCreateMode), *_AI_CREATE_MODES)
        )
        self._ai_annotation.setEnabled(not edit and create_mode in _AI_CREATE_MODES)

    def _highlight_ai_buttons(self, highlight: bool, /) -> None:  # noqa: FBT001 -- hover_highlight_requested slot
        self._ai_buttons_highlighted = highlight
        BG_ALPHA: Final = 60
        BORDER_ALPHA: Final = 120
        # alpha 0 (not highlighted) reads as transparent; HexArgb gives "#AARRGGBB",
        # which Qt stylesheets accept.
        bg = self.palette().color(QtGui.QPalette.ColorRole.Highlight)
        bg.setAlpha(BG_ALPHA if highlight else 0)
        border = QtGui.QColor(bg)
        border.setAlpha(BORDER_ALPHA if highlight else 0)
        style = (
            "QToolButton:!checked:!pressed {"
            f" background-color: {bg.name(QtGui.QColor.NameFormat.HexArgb)};"
            f" border: 1px solid {border.name(QtGui.QColor.NameFormat.HexArgb)};"
            " }"
        )
        for mode, action in self._actions.draw:
            if mode not in _AI_CREATE_MODES:
                continue
            for widget in action.associatedObjects():
                if isinstance(widget, QtWidgets.QToolButton):
                    widget.setStyleSheet(style)

    def show_label_list_menu(self, point: QtCore.QPoint, /) -> None:
        self._label_list_menu_origin = self._docks.label_list.mapToGlobal(point)
        try:
            # PySide6 type QMenu.exec() argument too narrowly
            self._menus.label_list.exec(self._label_list_menu_origin)  # ty: ignore[invalid-argument-type]
        finally:
            self._label_list_menu_origin = None

    def validate_label(self, *, label: str) -> bool:
        policy = self._config["validate_label"]
        if policy is None:
            return True
        unique_label_list = self._docks.unique_label_list
        existing_labels = [
            unique_label_list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(unique_label_list.count())
        ]
        return _is_valid_label(
            label=label, existing_labels=existing_labels, policy=policy
        )

    def _edit_label(self) -> None:
        items = [
            item
            for item in self._docks.label_list.selected_items()
            if not cast(Shape, item.shape()).locked
        ]
        if not items:
            logger.warning("No unlocked label is selected, so cannot edit label.")
            return

        shapes = [cast(Shape, item.shape()) for item in items]
        first_shape = shapes[0]
        # A field whose value differs across the selection has no single value
        # to show, so it is locked in the dialog and left untouched on accept.
        locked = {
            field
            for field in typing.get_args(LabelDialogField)
            if any(
                getattr(shape, field) != getattr(first_shape, field)
                for shape in shapes[1:]
            )
        }

        canvas_menu_origin = self._canvas_widgets.canvas.context_menu_origin
        menu_origin = (
            canvas_menu_origin
            if canvas_menu_origin is not None
            else self._label_list_menu_origin
        )
        entry = self._label_dialog.popup(
            text=first_shape.label,
            flags=first_shape.flags,
            group_id=first_shape.group_id,
            description=first_shape.description,
            locked=locked,
            position=menu_origin,
        )
        if entry is None:
            # The next new-shape dialog starts from the label that was on show.
            self._label_dialog.remember_label(
                label="" if "label" in locked else first_shape.label or ""
            )
            return

        if "label" not in locked and not self.validate_label(label=entry.label):
            self.show_error_message(
                title=self.tr("Invalid Label"),
                message=self.tr("Invalid label '{}' with validation type '{}'").format(
                    entry.label, self._config["validate_label"]
                ),
            )
            return

        for item in items:
            shape = item.shape()
            assert shape is not None
            for field in typing.get_args(LabelDialogField):
                if field not in locked:
                    setattr(shape, field, getattr(entry, field))

            assert shape.label is not None
            fill_rgb = self._get_rgb_by_label(
                label=shape.label,
                unique_label_list=self._docks.unique_label_list,
            )
            item.set_label(
                text=format_shape_label(shape=shape),
                color=fill_rgb,
            )
            self.mark_dirty()
            if self._docks.unique_label_list.find_label_item(label=shape.label) is None:
                self._docks.unique_label_list.add_label_item(
                    label=shape.label,
                    color=self._get_rgb_by_label(
                        label=shape.label,
                        unique_label_list=self._docks.unique_label_list,
                    ),
                )
        self._canvas_widgets.canvas.backup_shapes()

    def _on_file_search_changed(self) -> None:
        try:
            self._file_search_pattern = re.compile(self._docks.file_search.text())
        except re.error:
            self._docks.file_search_error.show()
            return
        self._docks.file_search_error.hide()
        self._refresh_file_list()

    def _load_selected_image(
        self,
        current_item: QtWidgets.QListWidgetItem | None,
        previous_item: QtWidgets.QListWidgetItem | None,
        /,
    ) -> bool:
        if current_item is None:
            return False
        # Qt moves the selection before asking to save or staging the next
        # session, so retain the exact prior UI state for rollback.
        if not self._can_continue() or not self._load_file(
            image_or_label_path=_file_list_item_path(current_item)
        ):
            self._restore_file_list_state(item=previous_item)
            return False
        return True

    def _on_shape_selection_changed(self, selected_shapes: list[Shape], /) -> None:
        self._docks.label_list.item_selection_changed.disconnect(
            self._label_selection_changed
        )
        self._docks.label_list.clearSelection()
        self._canvas_widgets.canvas.selected_shapes = selected_shapes
        for shape in self._canvas_widgets.canvas.selected_shapes:
            item = self._docks.label_list.find_item_by_shape(shape=shape)
            self._docks.label_list.select_item(item=item)
            self._docks.label_list.scroll_to_item(item=item)
        self._docks.label_list.item_selection_changed.connect(
            self._label_selection_changed
        )
        n_selected = len(selected_shapes) > 0
        # Locked shapes stay selectable, but only unlocked ones can be altered.
        n_unlocked = any(not shape.locked for shape in selected_shapes)
        self._actions.delete.setEnabled(n_unlocked)
        self._actions.duplicate.setEnabled(n_selected)
        self._actions.merge.setEnabled(can_merge_shapes(selected_shapes))
        self._actions.copy.setEnabled(n_selected)
        self._actions.edit.setEnabled(n_unlocked)
        self._actions.lock.setEnabled(n_selected)
        self._actions.lock.setText(
            self.tr("Unlock Shapes")
            if n_selected and not n_unlocked
            else self.tr("Lock Shapes")
        )
        self._is_fit_selection_deferred = False
        # An emptied selection keeps the view: grabbing a vertex deselects, and
        # zooming out then would move the image under the cursor.
        if self._zoom_mode != _ZoomMode.FIT_SELECTION or not selected_shapes:
            return
        if self._is_canvas_pointer_active:
            # A press can start dragging the shape it just selected, and a
            # release can be the first half of a double-click, so fit once
            # the pointer settles without a move.
            self._is_fit_selection_deferred = True
            self._fit_selection_timer.start()
            return
        self._adjust_scale()

    def _toggle_selected_shapes_lock(self) -> None:
        canvas = self._canvas_widgets.canvas
        if canvas.is_drawing:
            # Reloading the shapes below would discard the unfinished shape.
            return
        shapes = list(canvas.selected_shapes)
        value = any(not shape.locked for shape in shapes)
        for shape in shapes:
            shape.locked = value
        # Reloading resets hover state, so no handle hovered before the lock
        # stays grabbable, and it rebuilds the Label List rows with their icon.
        self._commit_shapes(canvas.shapes)
        canvas.select_shapes(shapes=shapes)

    def add_label(self, *, shape: Shape) -> None:
        assert shape.label is not None
        label_list_item = LabelListWidgetItem(shape=shape)
        self._docks.label_list.add_item(item=label_list_item)
        if self._docks.unique_label_list.find_label_item(label=shape.label) is None:
            self._docks.unique_label_list.add_label_item(
                label=shape.label,
                color=self._get_rgb_by_label(
                    label=shape.label,
                    unique_label_list=self._docks.unique_label_list,
                ),
            )
        self._label_dialog.add_label_history(label=shape.label)

        fill_rgb = self._get_rgb_by_label(
            label=shape.label,
            unique_label_list=self._docks.unique_label_list,
        )
        label_list_item.set_label(
            text=format_shape_label(shape=shape),
            color=fill_rgb,
        )

    def _get_rgb_by_label(
        self,
        *,
        label: str,
        unique_label_list: UniqueLabelQListWidget,
    ) -> tuple[int, int, int]:
        item = unique_label_list.find_label_item(label=label)
        label_index: int = (
            unique_label_list.indexFromItem(item).row()
            if item
            else unique_label_list.count()
        )
        shape_color = self._shape_color_preview
        if shape_color is None:
            shape_color = self._config["shape_color"]
        return resolve_shape_color(
            config=shape_color,
            label=label,
            label_index=label_index,
        )

    def remove_labels(self, *, shapes: list[Shape]) -> None:
        self._docks.label_list.item_dropped.disconnect(self._on_label_order_changed)
        for shape in shapes:
            item = self._docks.label_list.find_item_by_shape(shape=shape)
            self._docks.label_list.remove_item(item=item)
        self._docks.label_list.item_dropped.connect(self._on_label_order_changed)

    def _load_shapes(self, shapes: list[Shape], /, *, replace: bool) -> None:
        self._docks.label_list.item_selection_changed.disconnect(
            self._label_selection_changed
        )
        shape: Shape
        for shape in shapes:
            self.add_label(shape=shape)
        self._docks.label_list.clearSelection()
        self._docks.label_list.item_selection_changed.connect(
            self._label_selection_changed
        )
        self._canvas_widgets.canvas.load_shapes(shapes=shapes, replace=replace)

    def _commit_shapes(self, shapes: list[Shape], /) -> None:
        # Canvas loading pushes the one undo snapshot, so callers must not
        # back up again. Edits the canvas makes itself (delete, point removal,
        # drag) already snapshot there and only need the dirty mark.
        self._docks.label_list.clear()
        self._load_shapes(shapes, replace=True)
        self.mark_dirty()

    def _load_flags(
        self,
        *,
        flags: dict[str, bool],
        widget: QtWidgets.QListWidget,
    ) -> None:
        widget.clear()
        for key in dict.fromkeys([*(self._config["flags"] or []), *flags]):
            item: QtWidgets.QListWidgetItem = QtWidgets.QListWidgetItem(key)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked
                if flags.get(key, False)
                else Qt.CheckState.Unchecked
            )
            widget.addItem(item)

    def _capture_save_request(self, *, label_path: str) -> SaveRequest:
        assert self._image_path
        assert self._annotation is not None
        image_path = self._file_list_image_path or self._image_path
        # Save As confirms an overwrite in its dialog; no other save may replace
        # another Image's Annotation File.
        if (
            label_path != self._auto_save_path
            and Path(label_path).exists()
            and not _label_file_belongs_to_image(
                label_path=Path(label_path), image_path=image_path, cached=False
            )
        ):
            raise LabelFileError(
                self.tr("The Annotation File belongs to another Image: %s") % label_path
            )
        return SaveRequest(
            filename=label_path,
            annotation=Annotation(
                image_path=_resolve_stored_image_path(
                    image_path=image_path,
                    label_dir=Path(label_path).parent,
                ),
                image_data=self._annotation.image_data,
                shapes=[
                    _shape_to_dict(shape)
                    for item in self._docks.label_list
                    if (shape := item.shape()) is not None
                ],
                flags=self._read_flag_dock_states(),
                other_data=copy.deepcopy(self._annotation.other_data),
            ),
            image_height=self._image.height(),
            image_width=self._image.width(),
            save_image_data=self._config["with_image_data"],
        )

    def _record_saved_annotation(self, *, label_path: str) -> None:
        assert self._image_path is not None
        self._label_file_path = label_path
        self._refresh_image_list_checkmarks(label_path=label_path)
        self._failed_save_path = None
        self._status_bar.save.setText(self.tr("Saved"))
        self._status_bar.save.setToolTip(label_path)
        self._status_bar.retry.hide()
        self._actions.delete_file.setEnabled(True)
        self.mark_clean()

    def _show_save_failure(self, *, label_path: str, error: BaseException) -> None:
        self._failed_save_path = label_path
        self._status_bar.save.setText(self.tr("Save failed"))
        self._status_bar.save.setToolTip(f"{label_path}\n{error}")
        self._status_bar.retry.show()

    def _retry_save(self) -> None:
        if self._failed_save_path is not None:
            self._queue_auto_save(label_path=self._failed_save_path)

    def save_labels(self, *, label_path: str) -> bool:
        self._save_writer.discard_pending()
        self._wait_for_save()
        try:
            request = self._capture_save_request(label_path=label_path)
            write_save_request(request)
        except (LabelFileError, OSError, ValueError) as e:
            self._show_save_failure(label_path=label_path, error=e)
            self.show_error_message(
                title=self.tr("Error Saving Annotation File"),
                message=self.tr("<b>%s</b>") % e,
            )
            return False
        self._record_saved_annotation(label_path=request.filename)
        return True

    def _insert_shapes(self, shapes: list[Shape], /) -> None:
        if not shapes:
            return
        apply_default_flags(shapes=shapes, label_flags=self._config["label_flags"])
        # A pasted or duplicated copy of a locked shape starts out editable.
        for shape in shapes:
            shape.locked = False
        self._commit_shapes([*self._canvas_widgets.canvas.shapes, *shapes])
        self._canvas_widgets.canvas.select_shapes(shapes=shapes)

    def _merge_selected_shapes(self) -> None:
        canvas = self._canvas_widgets.canvas
        selected = list(canvas.selected_shapes)
        if not can_merge_shapes(selected):
            return
        merged = merge_masks(selected)
        # The merged shape takes the first input's slot so the Label List
        # order is preserved; the other inputs are dropped.
        shapes = [
            merged if s is selected[0] else s
            for s in canvas.shapes
            if s is selected[0] or s not in selected
        ]
        self._commit_shapes(shapes)
        canvas.select_shapes(shapes=[merged])

    def _label_selection_changed(self) -> None:
        selected_shapes: list[Shape] = []
        for item in self._docks.label_list.selected_items():
            shape = item.shape()
            assert shape is not None
            selected_shapes.append(shape)
        if selected_shapes:
            self._canvas_widgets.canvas.select_shapes(shapes=selected_shapes)
        else:
            if self._canvas_widgets.canvas.deselect_shape():
                self._canvas_widgets.canvas.update()

    def _on_label_item_changed(self, item: LabelListWidgetItem, /) -> None:
        is_visible_new = item.checkState() == Qt.CheckState.Checked

        selected_group = (
            self._docks.label_list.selection_at_press()
            or self._docks.label_list.selected_items()
        )
        items_to_toggle = (
            selected_group
            if item in selected_group and len(selected_group) > 1
            else [item]
        )
        items_to_change = [
            it
            for it in items_to_toggle
            if (sh := it.shape()) is not None and sh.visible != is_visible_new
        ]
        if not items_to_change:
            return

        new_check_state = (
            Qt.CheckState.Checked if is_visible_new else Qt.CheckState.Unchecked
        )
        with QtCore.QSignalBlocker(self._docks.label_list._model):
            for item_to_toggle in items_to_change:
                shape_to_toggle = item_to_toggle.shape()
                assert shape_to_toggle is not None
                item_to_toggle.setCheckState(new_check_state)
                self._canvas_widgets.canvas.set_shape_visible(
                    shape=shape_to_toggle, value=is_visible_new
                )

        self._canvas_widgets.canvas.backup_shapes()
        self._actions.undo.setEnabled(self._canvas_widgets.canvas.can_restore_shape)

    def _on_label_order_changed(self) -> None:
        self._commit_shapes(
            [s for item in self._docks.label_list if (s := item.shape()) is not None]
        )

    # Callback functions:

    def _on_new_shape(self) -> None:
        items = self._docks.unique_label_list.selectedItems()
        text = items[0].data(Qt.ItemDataRole.UserRole) if items else None
        if self._config["display_label_popup"] or not text:
            entry = self._label_dialog.popup(text=text)
        else:
            entry = LabelDialogEntry(
                label=text, flags={}, group_id=None, description=""
            )

        if entry is not None and not self.validate_label(label=entry.label):
            self.show_error_message(
                title=self.tr("Invalid Label"),
                message=self.tr("Invalid label '{}' with validation type '{}'").format(
                    entry.label, self._config["validate_label"]
                ),
            )
            entry = None
        if entry is None:
            self._canvas_widgets.canvas.undo_last_line()
            self._canvas_widgets.canvas.shape_backups.pop()
            return

        self._docks.label_list.clearSelection()
        shapes = self._canvas_widgets.canvas.set_last_label(
            text=entry.label, flags=entry.flags
        )
        apply_default_flags(shapes=shapes, label_flags=self._config["label_flags"])
        for shape in shapes:
            if entry.group_id is not None or shape.group_id is None:
                shape.group_id = entry.group_id
            shape.description = entry.description
            self.add_label(shape=shape)
        # The draft snapshot was taken before the dialog ran, so retake it now
        # or undo would strip the group id and description along with the
        # next change.
        self._canvas_widgets.canvas.shape_backups.pop()
        self._canvas_widgets.canvas.backup_shapes()
        self._actions.edit_mode.setEnabled(True)
        self._actions.undo_last_point.setEnabled(False)
        self._actions.undo.setEnabled(True)
        self.mark_dirty()

    def _on_inference_produced_no_shapes(self) -> None:
        self.show_status_message(
            self.tr("AI inference produced no new annotation."), delay=5000
        )

    def _on_inference_failed(self, message: str, /) -> None:
        self.show_status_message(
            self.tr("AI inference failed: %s") % message, delay=10000
        )

    def _on_scroll_request(self, delta: int, orientation: Qt.Orientation, /) -> None:
        units = -delta * 0.1  # natural scroll
        bar = self._canvas_widgets.scroll_bars[orientation]
        value = bar.value() + bar.singleStep() * units
        self.set_scroll_value(orientation=orientation, value=value)

    def _on_pan_request(self, step: QtCore.QPoint, /) -> None:
        # Pan moves the viewport opposite to the cursor delta so the image
        # tracks the grabbed point one-for-one in widget pixels.
        self._move_canvas_view(step=QtCore.QPointF(step), constrain_to_center=True)

    def _move_canvas_view(
        self, *, step: QtCore.QPointF, constrain_to_center: bool
    ) -> None:
        h_bar = self._canvas_widgets.scroll_bars[Qt.Orientation.Horizontal]
        v_bar = self._canvas_widgets.scroll_bars[Qt.Orientation.Vertical]
        h_old = h_bar.value()
        v_old = v_bar.value()
        self.set_scroll_value(
            orientation=Qt.Orientation.Horizontal, value=h_bar.value() - step.x()
        )
        self.set_scroll_value(
            orientation=Qt.Orientation.Vertical, value=v_bar.value() - step.y()
        )
        # Scrollbars take the movement they can; the render offset carries any
        # clamped remainder without changing canvas geometry.
        self._canvas_widgets.canvas.pan_view(
            step=QtCore.QPointF(
                step.x() + h_bar.value() - h_old,
                step.y() + v_bar.value() - v_old,
            ),
            constrain_to_center=constrain_to_center,
        )

    def set_scroll_value(self, *, orientation: Qt.Orientation, value: float) -> None:
        self._canvas_widgets.scroll_bars[orientation].setValue(int(value))

    def _remember_current_viewport(self) -> None:
        if self._image_path is None:
            return
        self._viewport_states[self._image_path] = _ViewportState(
            zoom_mode=self._zoom_mode,
            zoom_value=self._canvas_widgets.zoom_widget.value(),
            scroll_values={
                orientation: bar.value()
                for orientation, bar in self._canvas_widgets.scroll_bars.items()
            },
            view_offset=self._canvas_widgets.canvas.get_view_offset(),
        )
        self._prev_image_path = self._image_path

    def _set_zoom(self, *, value: float, pos: QtCore.QPointF | None) -> None:
        if self._image_path is None:
            logger.warning("image_path is None, cannot set zoom")
            return

        canvas = self._canvas_widgets.canvas
        if self._zoom_mode != _ZoomMode.MANUAL_ZOOM:
            canvas.reset_view_offset()
            self._sync_zoom_mode_actions()
            self._canvas_widgets.zoom_widget.setValue(value)
            return

        if pos is None:
            pos = QtCore.QPointF(canvas.visibleRegion().boundingRect().center())
        viewport = self._canvas_widgets.scroll_area.viewport()
        image_pos = canvas.transform_widget_point_to_image(pos)
        viewport_pos = canvas.mapTo(viewport, pos)

        self._sync_zoom_mode_actions()
        # Setting the value fires valueChanged, which rescales the canvas.
        self._canvas_widgets.zoom_widget.setValue(value)

        self._move_image_point_to_viewport(
            image_pos=image_pos, viewport_pos=viewport_pos
        )

    def _move_image_point_to_viewport(
        self, *, image_pos: QtCore.QPointF, viewport_pos: QtCore.QPointF
    ) -> None:
        canvas = self._canvas_widgets.canvas
        viewport = self._canvas_widgets.scroll_area.viewport()
        # Canvas geometry lags a scale change, so map against its size hint.
        target = canvas.transform_image_point_to_widget(
            image_pos, area=canvas.sizeHint()
        )
        current = canvas.mapFrom(viewport, viewport_pos)
        self._move_canvas_view(step=current - target, constrain_to_center=False)

    def _set_zoom_to_original(self) -> None:
        self._zoom_mode = _ZoomMode.MANUAL_ZOOM
        self._set_zoom(value=100, pos=None)

    def _add_zoom(self, *, increment: float, pos: QtCore.QPointF | None) -> None:
        # Multiplicative stepping on a float widget; the QDoubleSpinBox rounds to
        # its decimal precision, so no integer ceil/floor clamping is needed.
        zoom_value = self._canvas_widgets.zoom_widget.value() * increment
        self._zoom_mode = _ZoomMode.MANUAL_ZOOM
        self._set_zoom(value=zoom_value, pos=pos)

    def _zoom_requested(self, delta: int, pos: QtCore.QPointF, /) -> None:
        self._add_zoom(increment=1.1 if delta > 0 else 0.9, pos=pos)

    def set_fit_window_mode(self, value: bool = True, /) -> None:  # noqa: FBT001, FBT002 -- QAction.triggered slot
        target = _ZoomMode.FIT_WINDOW if value else _ZoomMode.MANUAL_ZOOM
        self._switch_zoom_mode(target)

    def set_fit_selection_mode(self, value: bool = True, /) -> None:  # noqa: FBT001, FBT002 -- QAction.triggered slot
        target = _ZoomMode.FIT_SELECTION if value else _ZoomMode.MANUAL_ZOOM
        self._switch_zoom_mode(target)

    def _end_canvas_pointer_activity(self) -> None:
        self._is_canvas_pointer_active = False

    def _cancel_deferred_fit_selection(self) -> None:
        self._is_fit_selection_deferred = False

    def _apply_deferred_fit_selection(self) -> None:
        if not self._is_fit_selection_deferred:
            return
        if QtWidgets.QApplication.mouseButtons() != Qt.MouseButton.NoButton:
            return  # the release restarts the timer
        self._is_fit_selection_deferred = False
        if (
            self._zoom_mode == _ZoomMode.FIT_SELECTION
            and self._canvas_widgets.canvas.selected_shapes
        ):
            self._adjust_scale()

    def _switch_zoom_mode(self, mode: _ZoomMode, /) -> None:
        self._zoom_mode = mode
        self._adjust_scale()

    def _sync_zoom_mode_actions(self) -> None:
        self._actions.fit_window.setChecked(self._zoom_mode == _ZoomMode.FIT_WINDOW)
        self._actions.fit_selection.setChecked(
            self._zoom_mode == _ZoomMode.FIT_SELECTION
        )
        self._zoom_mode_label.setText(self._zoom_mode_captions[self._zoom_mode])

    def _on_brightness_contrast_changed(self, qimage: QtGui.QImage, /) -> None:
        self._canvas_widgets.canvas.load_pixmap(
            pixmap=QtGui.QPixmap.fromImage(qimage), clear_shapes=False
        )

    def open_brightness_contrast_dialog(
        self,
        _value: bool,  # noqa: FBT001 -- QAction.triggered slot
        /,
        *,
        is_initial_load: bool = False,
    ) -> None:
        if self._image_path is None:
            logger.warning("image_path is None, cannot set brightness/contrast")
            return

        brightness: int | None
        contrast: int | None
        brightness, contrast = self._brightness_contrast_values.get(
            self._image_path, (None, None)
        )
        if is_initial_load:
            if self._config["keep_prev_brightness_contrast"] and self._prev_image_path:
                brightness, contrast = self._brightness_contrast_values.get(
                    self._prev_image_path, (None, None)
                )
            if brightness is None and contrast is None:
                return

        logger.debug(
            "Opening brightness/contrast dialog with brightness={}, contrast={}",
            brightness,
            contrast,
        )
        assert self._annotation is not None
        dialog = BrightnessContrastDialog(
            img=_utils.img_data_to_pil(self._annotation.image_data),
            callback=self._on_brightness_contrast_changed,
            parent=self,
        )

        if brightness is not None:
            dialog.slider_brightness.setValue(brightness)
        if contrast is not None:
            dialog.slider_contrast.setValue(contrast)

        if is_initial_load:
            dialog.apply()
        else:
            dialog.exec()
            brightness = dialog.slider_brightness.value()
            contrast = dialog.slider_contrast.value()

        self._brightness_contrast_values[self._image_path] = (brightness, contrast)
        logger.debug(
            "Updated states for {}: brightness={}, contrast={}",
            self._image_path,
            brightness,
            contrast,
        )

    def toggle_shape_visibility(self, *, value: bool | None) -> None:
        for item in self._docks.label_list:
            target = (
                item.checkState() == Qt.CheckState.Unchecked if value is None else value
            )
            item.setCheckState(
                Qt.CheckState.Checked if target else Qt.CheckState.Unchecked
            )

    def _read_annotation_file(self, *, label_path: str) -> Annotation | None:
        try:
            return read_label_file(filename=label_path, max_decode_mb=_max_decode_mb())
        except LabelFileError as e:
            self._show_file_open_error(
                path=label_path, file_kind="label", exc=e, extra=None
            )
            return None

    def _read_image_as_annotation(self, *, image_path: str) -> Annotation | None:
        try:
            image_data = read_image_file(
                filename=image_path, max_decode_mb=_max_decode_mb()
            )
        except OSError as e:
            self._show_file_open_error(
                path=image_path, file_kind="image", exc=e, extra=None
            )
            return None
        return Annotation(
            image_path=os.path.basename(image_path),
            image_data=image_data,
            shapes=[],
            flags={},
            other_data={},
        )

    def _confirm_large_image_open(
        self, *, requirement: ImageDecodeRequirement, limit_mb: int
    ) -> bool:
        msg_box = QtWidgets.QMessageBox(self)
        msg_box.setWindowTitle(self.tr("Large Image"))
        msg_box.setText(self.tr("Large image requires more memory"))
        msg_box.setInformativeText(
            self.tr(
                "The image is {width}x{height} pixels and needs at least about "
                "{required} MB to decode, above the current {limit} MB safety "
                "limit. Opening it may temporarily make Labelme or other "
                "applications less responsive."
            ).format(
                width=requirement.width,
                height=requirement.height,
                required=requirement.required_mb,
                limit=limit_mb,
            )
        )
        open_button = msg_box.addButton(
            self.tr("Open Anyway"),
            QtWidgets.QMessageBox.ButtonRole.AcceptRole,
        )
        cancel_button = msg_box.addButton(
            self.tr("Cancel"), QtWidgets.QMessageBox.ButtonRole.RejectRole
        )
        msg_box.setDefaultButton(cancel_button)
        msg_box.setEscapeButton(cancel_button)
        msg_box.exec()
        return msg_box.clickedButton() is open_button

    def _restore_file_list_state(
        self, *, item: QtWidgets.QListWidgetItem | None
    ) -> None:
        with QtCore.QSignalBlocker(self._docks.file_list):
            if item is None:
                self._docks.file_list.setCurrentRow(-1)
            else:
                self._docks.file_list.setCurrentItem(item)
        self._docks.file_list.repaint()
        self.setWindowTitle(self._get_window_title(dirty=self._is_changed))

    def _load_file(self, *, image_or_label_path: str) -> bool:
        # Qt file dialogs separate with forward slashes even on Windows, while
        # the Image List holds the separator of the platform, so an unnormalized
        # path would neither select its Image List row nor receive the saved
        # checkmark, which both compare exact strings.
        image_or_label_path = os.path.normpath(image_or_label_path)
        file_list_image_path = (
            None
            if is_label_file_path(filename=image_or_label_path)
            else image_or_label_path
        )

        prev_shapes: list[Shape] = (
            self._canvas_widgets.canvas.shapes
            if self._config["keep_prev"]
            or QtWidgets.QApplication.keyboardModifiers()
            == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
            else []
        )
        if not QtCore.QFile.exists(image_or_label_path):
            self.show_error_message(
                title=self.tr("Error Opening File"),
                message=self.tr("No such file: <b>%s</b>") % image_or_label_path,
            )
            return False
        self.show_status_message(
            self.tr("Loading %s...") % Path(image_or_label_path).name
        )

        t0_load_file = time.time()
        label_path = (
            image_or_label_path
            if file_list_image_path is None
            else _find_label_path(
                image_path=image_or_label_path,
                output_dir=self._output_dir,
                root_prefix=self._file_list_root_prefix,
                cached=False,
            )
        )
        if label_path is None:
            annotation = self._read_image_as_annotation(image_path=image_or_label_path)
            if annotation is None:
                return False
            image_path = image_or_label_path
            label_file_path = None
            shapes = []
        else:
            annotation = self._read_annotation_file(label_path=label_path)
            if annotation is None:
                return False
            # The relative path stored in the Annotation File may carry "." or ".."
            # components, which would survive the join and break the
            # exact-string comparisons against the Image List.
            stored_image = Path(label_path).parent / annotation.image_path
            image_path = os.path.normpath(str(stored_image))
            # Following symlinks first keeps parent traversal on its intended target.
            if os.path.realpath(image_path) != os.path.realpath(stored_image):
                image_path = os.path.join(
                    os.path.realpath(stored_image.parent), stored_image.name
                )
            label_file_path = label_path
            shapes = _shapes_from_dicts(
                shape_dicts=annotation.shapes,
                label_flags=self._config["label_flags"],
            )
        t0 = time.time()
        image = (
            None
            if file_list_image_path is None
            else self._image_prefetcher.take(
                image_path=file_list_image_path, image_data=annotation.image_data
            )
        )
        if image is None:
            image = QtGui.QImage.fromData(annotation.image_data)
        logger.debug("Created QImage in {:.0f}ms", (time.time() - t0) * 1000)

        if image.isNull():
            requirement = get_image_decode_requirement(image_data=annotation.image_data)
            original_limit = QtGui.QImageReader.allocationLimit()
            if (
                requirement is not None
                and max(requirement.width, requirement.height) <= RASTER_MAX_SIDE
                and 0 < original_limit < requirement.required_mb
            ):
                if not self._confirm_large_image_open(
                    requirement=requirement, limit_mb=original_limit
                ):
                    return False
                try:
                    QtGui.QImageReader.setAllocationLimit(requirement.required_mb)
                    image = QtGui.QImage.fromData(annotation.image_data)
                finally:
                    QtGui.QImageReader.setAllocationLimit(original_limit)

        if image.isNull():
            extra = _make_image_too_large_message(image_data=annotation.image_data)
            if extra is None:
                formats = ", ".join(
                    f"*.{fmt.toStdString()}"
                    for fmt in QtGui.QImageReader.supportedImageFormats()
                )
                extra = self.tr("Allowed formats: {formats}").format(formats=formats)
            self._show_file_open_error(
                path=image_or_label_path,
                file_kind="image",
                exc=None,
                extra=extra,
            )
            return False

        # The replacement session is fully staged; only now replace the
        # current one.
        self._remember_current_viewport()
        self.reset_state()
        self._canvas_widgets.canvas.setEnabled(False)
        self._annotation = annotation
        self._image_path = image_path
        self._file_list_image_path = file_list_image_path
        self._label_file_path = label_file_path
        self._image = image
        t0 = time.time()
        self._canvas_widgets.canvas.load_pixmap(pixmap=QtGui.QPixmap.fromImage(image))
        self._canvas_widgets.surface.setCurrentWidget(self._canvas_widgets.scroll_area)
        logger.debug("Loaded pixmap in {:.0f}ms", (time.time() - t0) * 1000)
        # Record one baseline state. Loading carried-forward shapes separately
        # would create a false Undo step that discards them before any edit.
        carry_prev_shapes = bool(prev_shapes) and not shapes
        if carry_prev_shapes:
            # A lock approves a shape on its own image, not on the next one.
            for shape in prev_shapes:
                shape.locked = False
        self._load_shapes(prev_shapes if carry_prev_shapes else shapes, replace=True)
        self._load_flags(flags=annotation.flags, widget=self._docks.flag_list)
        if carry_prev_shapes:
            self.mark_dirty()
        else:
            self.mark_clean()
        self._actions.delete_file.setEnabled(self.has_label_file())
        self._canvas_widgets.canvas.setEnabled(True)
        # Zoom changes the live scroll positions, so resolve the intended
        # viewport first.
        target_viewport = self._viewport_states.get(self._image_path)
        if self._config["keep_prev_scale"] and self._prev_image_path is not None:
            target_viewport = self._viewport_states.get(self._prev_image_path)
        # set zoom values
        is_initial_load = not self._viewport_states
        if target_viewport is not None:
            self._zoom_mode = target_viewport.zoom_mode
            if self._zoom_mode == _ZoomMode.MANUAL_ZOOM:
                self._set_zoom(value=target_viewport.zoom_value, pos=None)
            else:
                self._adjust_scale()
        elif is_initial_load or not self._config["keep_prev_scale"]:
            self._zoom_mode = _ZoomMode.FIT_WINDOW
            self._adjust_scale()
        # The zoom value can be unchanged across images, so update geometry
        # explicitly before restoring positions against the new scroll range.
        self._apply_zoom_to_canvas()
        # A load leaves nothing selected, so Fit to Selection shows the whole
        # image; positions saved while zoomed to a shape no longer apply.
        if target_viewport is not None and self._zoom_mode != _ZoomMode.FIT_SELECTION:
            for orientation, value in target_viewport.scroll_values.items():
                self.set_scroll_value(orientation=orientation, value=value)
            self._canvas_widgets.canvas.reset_view_offset()
            self._canvas_widgets.canvas.pan_view(
                step=target_viewport.view_offset, constrain_to_center=False
            )
        self.open_brightness_contrast_dialog(
            False,  # noqa: FBT003 -- placeholder for the Qt triggered flag
            is_initial_load=True,
        )
        self._actions.image.setEnabled(True)
        self._sync_navigation_actions()
        self._prefetch_neighbors()
        # A load never pulls the keyboard out of the Image List, whatever drove
        # it; otherwise an arrow-key walk of the list ends after one keypress.
        if not self._docks.file_list.hasFocus():
            self._canvas_widgets.canvas.setFocus()
        self.show_status_message(self.tr("Loaded %s") % Path(image_or_label_path).name)
        logger.info(
            "Loaded file: {!r} in {:.0f}ms",
            image_or_label_path,
            (time.time() - t0_load_file) * 1000,
        )
        return True

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent, /) -> bool:
        if watched is self._canvas_widgets.canvas:
            if event.type() in (
                QtCore.QEvent.Type.MouseButtonPress,
                QtCore.QEvent.Type.MouseButtonDblClick,
            ):
                self._is_canvas_pointer_active = True
                self._fit_selection_timer.stop()
            elif event.type() == QtCore.QEvent.Type.MouseButtonRelease:
                # The canvas handles the release after this filter and may
                # change the selection then, so stay active until it is done.
                # A modal dialog that swallows a release leaves the flag set;
                # that only delays the next fit by the timer interval.
                QtCore.QTimer.singleShot(0, self._end_canvas_pointer_activity)
                if self._is_fit_selection_deferred:
                    # The timer fires after the canvas handles this release,
                    # which reports a finished move through shape_moved.
                    self._fit_selection_timer.start()
        if (
            watched is self._canvas_widgets.scroll_area
            and event.type() == QtCore.QEvent.Type.Resize
            and not self._image.isNull()
            and self._zoom_mode != _ZoomMode.MANUAL_ZOOM
        ):
            # The outer window resizes before its nested layout settles. Observe
            # the scroll area, whose size is also independent of scrollbar changes.
            self._adjust_scale()
        return super().eventFilter(watched, event)

    def _apply_zoom_to_canvas(self) -> None:
        if self._image.isNull():
            logger.warning("image is null, cannot apply zoom")
            return
        self._canvas_widgets.canvas.scale = self._canvas_widgets.zoom_widget.scale

    def _adjust_scale(self) -> None:
        if (
            self._zoom_mode == _ZoomMode.FIT_SELECTION
            and (bounds := self._canvas_widgets.canvas.get_selected_shapes_bounds())
            is not None
        ):
            self._fit_image_rect(rect=bounds)
            return
        if self._zoom_mode in (_ZoomMode.FIT_WINDOW, _ZoomMode.FIT_SELECTION):
            scale = self._fit_window_scale()
        else:
            scale = 1.0
        self._set_zoom(value=scale * 100, pos=None)

    def _fit_image_rect(self, *, rect: QtCore.QRectF) -> None:
        PADDING_RATIO: Final[float] = 0.15
        MIN_PADDING: Final[float] = 24.0  # image pixels, so tiny shapes keep context
        padding = max(max(rect.width(), rect.height()) * PADDING_RATIO, MIN_PADDING)
        rect = rect.adjusted(-padding, -padding, padding, padding)
        available = self._canvas_widgets.scroll_area.maximumViewportSize()
        scale = min(
            available.width() / rect.width(), available.height() / rect.height()
        )
        # The zoom control clamps the value, so center with the applied scale.
        self._set_zoom(value=scale * 100, pos=None)

        settled = self._canvas_widgets.canvas.compute_settled_viewport_size()
        assert settled is not None
        # Scrolling stops at the image edge; the render offset takes the rest,
        # so a shape at the edge is still centered.
        self._move_image_point_to_viewport(
            image_pos=rect.center(),
            viewport_pos=QtCore.QPointF(settled.width() / 2, settled.height() / 2),
        )

    def _fit_window_scale(self) -> float:
        FIT_WINDOW_SCROLLBAR_MARGIN: Final[float] = 2.0
        viewport = self._canvas_widgets.scroll_area
        pixmap = self._canvas_widgets.canvas.pixmap
        available_w = viewport.width() - FIT_WINDOW_SCROLLBAR_MARGIN
        available_h = viewport.height() - FIT_WINDOW_SCROLLBAR_MARGIN
        scale_by_width = available_w / pixmap.width()
        scale_by_height = available_h / pixmap.height()
        return min(scale_by_width, scale_by_height)

    def _reset_layout(self) -> None:
        self._window_state.remove(WINDOW_LAYOUT_KEY)
        self.restoreState(self._default_state)

    def closeEvent(self, a0: QtGui.QCloseEvent, /) -> None:
        if not self._can_continue():
            a0.ignore()
            return
        if not self._model_manager.shutdown():
            a0.ignore()
            return
        self._save_writer.shutdown()
        self._image_prefetcher.shutdown()
        self._window_state.setValue(WINDOW_SIZE_KEY, self.size())
        self._window_state.setValue(WINDOW_POSITION_KEY, self.pos())
        self._window_state.setValue(WINDOW_LAYOUT_KEY, self.saveState())

    def dragEnterEvent(self, a0: QtGui.QDragEnterEvent, /) -> None:
        # Accepting only drags that carry a loadable image keeps the cursor
        # from promising a drop that would change nothing.
        a0.setAccepted(bool(_extract_dropped_image_paths(mime=a0.mimeData())))

    def dropEvent(self, a0: QtGui.QDropEvent, /) -> None:
        if not self._can_continue():
            a0.ignore()
            return
        self.import_dropped_image_files(
            image_files=_extract_dropped_image_paths(mime=a0.mimeData())
        )

    # User Dialogs #

    def _get_neighbor_image_path(self, *, step: Literal[-1, 1]) -> str | None:
        paths = self._loaded_image_paths
        current_path = self._file_list_image_path
        # Closing an Image retains its selected row as the navigation origin.
        if current_path is None and (item := self._docks.file_list.currentItem()):
            current_path = _file_list_item_path(item)
        try:
            current = paths.index(current_path or "")
        except ValueError:
            current = -1
        # Filtering can hide the active row; navigation still follows directory order.
        indices = (
            range(current - 1, -1, -1) if step == -1 else range(current + 1, len(paths))
        )
        return next(
            (paths[i] for i in indices if self._matches_file_search(paths[i])),
            None,
        )

    def _prefetch_neighbors(self) -> None:
        self._image_prefetcher.retain(
            current=None
            if self._file_list_image_path is None or self._annotation is None
            else (self._file_list_image_path, self._annotation.image_data, self._image),
            neighbors=[
                path
                for step in (1, -1)
                if (path := self._get_neighbor_image_path(step=step)) is not None
            ],
        )

    def _sync_navigation_actions(self) -> None:
        self._actions.open_prev_img.setEnabled(
            self._get_neighbor_image_path(step=-1) is not None
        )
        self._actions.open_next_img.setEnabled(
            self._get_neighbor_image_path(step=1) is not None
        )

    def _open_prev_image(self) -> None:
        if (path := self._get_neighbor_image_path(step=-1)) is not None:
            self._docks.file_list.setCurrentRow(self.image_list.index(path))

    def _open_next_image(self) -> None:
        if (path := self._get_neighbor_image_path(step=1)) is not None:
            self._docks.file_list.setCurrentRow(self.image_list.index(path))

    def _open_file_with_dialog(self) -> None:
        if not self._can_continue():
            return
        formats = [
            f"*.{fmt.toStdString()}"
            for fmt in QtGui.QImageReader.supportedImageFormats()
        ]
        filters = self.tr("Images and annotation files (%s)") % " ".join(
            formats + [f"*{LABEL_FILE_SUFFIX}"]
        )
        image_or_label_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            self.tr("Open File"),
            self.current_path(),
            filters,
        )
        if image_or_label_path:
            self._load_from_file_or_dir(file_or_dir=image_or_label_path)

    def prompt_output_dir(self) -> None:
        default_output_dir: str
        if self._output_dir is not None:
            default_output_dir = str(self._output_dir)
        elif self._image_path:
            default_output_dir = str(Path(self._image_path).parent)
        else:
            default_output_dir = self.current_path()

        output_dir = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            self.tr("Choose Annotation Folder"),
            default_output_dir,
            QtWidgets.QFileDialog.Option.ShowDirsOnly
            | QtWidgets.QFileDialog.Option.DontResolveSymlinks,
        )
        output_dir = str(output_dir)

        if not output_dir:
            return

        if not self._can_continue():
            return

        if not self._switch_output_dir(Path(output_dir)):
            return
        self._docks.annotation_folder_footer.set_missing(None)
        assert self._file_list_root_prefix is not None
        self._remember_output_dir(opened_dir=self._file_list_root_prefix)
        self.statusBar().showMessage(
            self.tr("Annotation Folder: %s") % self._output_dir
        )
        self.statusBar().show()

    def _clear_output_dir(self) -> None:
        if not self._can_continue() or not self._switch_output_dir(None):
            return
        self._docks.annotation_folder_footer.set_missing(None)
        if self._file_list_root_prefix is not None:
            self._remember_output_dir(opened_dir=self._file_list_root_prefix)

    def _switch_output_dir(self, output_dir: Path | None, /) -> bool:
        # Reload the current image against the candidate directory and keep
        # the previous directory when that reload fails, so a bad candidate
        # never becomes the autosave target.
        previous_output_dir = self._output_dir
        self._output_dir = output_dir
        if self._file_list_image_path is not None and not self._load_file(
            image_or_label_path=self._file_list_image_path
        ):
            self._output_dir = previous_output_dir
            return False
        self._auto_save_path = None
        self._refresh_file_list()
        return True

    @property
    def _output_dir(self) -> Path | None:
        return self._output_dir_value

    @_output_dir.setter
    def _output_dir(self, value: Path | None, /) -> None:
        # The Annotation Folder footer mirrors every change, wherever it comes from.
        self._output_dir_value = value
        self._docks.annotation_folder_footer.set_folder(value)

    def _save_label_file(self, *, save_as: bool) -> None:
        assert not self._image.isNull(), "cannot save empty image"

        label_path: str | None = None
        if not save_as:
            # A first auto-save already owns a destination, even before it finishes.
            label_path = self._save_writer.get_latest_path() or self._label_file_path
        if label_path is None:
            label_path = self.prompt_save_file_path()
            if label_path:
                # The dialog confirmed any overwrite. Keep the chosen
                # destination through failure, Retry, and later edits.
                self._auto_save_path = label_path

        if not label_path:
            logger.warning("label_path={!r} is empty, so cannot save", label_path)
            return

        self.save_labels(label_path=label_path)

    def prompt_save_file_path(self) -> str:
        assert self._image_path is not None
        default_path = _resolve_label_path(
            image_path=self._file_list_image_path or self._image_path,
            output_dir=self._output_dir,
            root_prefix=self._file_list_root_prefix,
        )
        # The dialog cannot preselect a file in a mirrored subfolder of the
        # Annotation Folder that does not exist yet.
        with contextlib.suppress(OSError):
            Path(default_path).parent.mkdir(parents=True, exist_ok=True)
        label_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            parent=self,
            caption=self.tr("Save Annotation File"),
            dir=default_path,
            filter=self.tr("Annotation files (*%s)") % LABEL_FILE_SUFFIX,
        )
        return label_path

    def close_file(self) -> None:
        if not self._can_continue():
            return
        self._remember_current_viewport()
        self.reset_state()
        self.mark_clean()
        self._actions.delete_file.setEnabled(self.has_label_file())
        self._actions.image.setEnabled(False)
        self._canvas_widgets.canvas.setEnabled(False)
        self._canvas_widgets.surface.setCurrentWidget(self._canvas_widgets.empty_state)
        self._docks.file_list.setFocus()
        self._sync_navigation_actions()

    def current_label_file_path(self) -> str:
        assert self._image_path is not None
        if self._label_file_path is not None:
            return self._label_file_path
        return _resolve_label_path(
            image_path=self._file_list_image_path or self._image_path,
            output_dir=self._output_dir,
            root_prefix=self._file_list_root_prefix,
        )

    def _confirm_deletion(self, *, message: str) -> bool:
        msg_box = QtWidgets.QMessageBox(self)
        msg_box.setIcon(QtWidgets.QMessageBox.Icon.Warning)
        msg_box.setWindowTitle(self.tr("Delete Annotation File"))
        msg_box.setText(message)
        delete_button = msg_box.addButton(
            self.tr("Delete"), QtWidgets.QMessageBox.ButtonRole.DestructiveRole
        )
        cancel_button = msg_box.addButton(
            self.tr("Cancel"), QtWidgets.QMessageBox.ButtonRole.RejectRole
        )
        msg_box.setDefaultButton(cancel_button)
        msg_box.exec()
        return msg_box.clickedButton() is delete_button

    def delete_file(self) -> None:
        msg = self.tr(
            "Permanently delete this annotation file? This action cannot be undone."
        )
        if not self._confirm_deletion(message=msg):
            return

        self._save_writer.discard_pending()
        self._wait_for_save()
        label_path = self._own_label_file_path()
        if label_path is None:
            return
        annotation_path = Path(label_path)
        try:
            annotation_path.unlink()
        except FileNotFoundError:
            return
        except OSError as error:
            self.show_error_message(
                title=self.tr("Error Deleting Annotation File"), message=str(error)
            )
            return
        self._failed_save_path = None
        self._status_bar.save.clear()
        self._status_bar.retry.hide()
        logger.info(f"Label file is removed: {annotation_path}")

        self._refresh_image_list_checkmarks(label_path=str(annotation_path))

        # Only the label file was deleted, not the image: clear the annotations
        # but keep the image on the canvas.
        self._docks.label_list.clear()
        # Drop the pre-delete backups first so undo cannot resurrect the
        # annotations of the file we just removed; the reload below re-seeds the
        # stack with the empty state, keeping "top mirrors current" intact.
        self._canvas_widgets.canvas.shape_backups.clear()
        self._canvas_widgets.canvas.load_shapes(shapes=[], replace=True)
        self._actions.undo.setEnabled(self._canvas_widgets.canvas.can_restore_shape)
        self.mark_clean()
        self._actions.delete_file.setEnabled(self.has_label_file())

    @property
    def _is_settings_editable(self) -> bool:
        return self._config_file is not None and not self._config_overrides

    def _make_label_dialog(self, *, label_history: list[str] | None) -> LabelDialog:
        return LabelDialog(
            parent=self,
            labels=self._config["labels"],
            sort_labels=self._config["sort_labels"],
            show_text_field=self._config["show_label_text_field"],
            completion=self._config["label_completion"],
            fit_to_content=self._config["fit_to_content"],
            flags=self._config["label_flags"],
            label_history=label_history,
        )

    def _connect_persistent_actions(self) -> None:
        for key_path, action in self._persistent_actions.items():
            action.toggled.connect(
                lambda checked, path=key_path: self._apply_setting_change(path, checked)
            )

    def _on_ai_model_changed(self, model_id: str, /) -> None:
        self._canvas_widgets.canvas.set_ai_model_name(model_name=model_id)
        option = _ai_models.find_ai_assist_model_option(model_name=model_id)
        assert option is not None
        model_display = option.display_name
        if self._config["ai"]["default"] == model_display:
            return
        self._apply_setting_change(("ai", "default"), model_display)

    def _on_ai_polygon_detail_changed(self, detail: int, /) -> None:
        self._apply_setting_change(("mask_polygonization", "detail"), detail)

    def _set_setting_value(self, *, key_path: tuple[str, ...], value: object) -> None:
        node: dict = self._config
        for key in key_path[:-1]:
            node = node[key]
        node[key_path[-1]] = value

    def _read_setting_value(self, *, key_path: tuple[str, ...]) -> object:
        node: object = self._config
        for key in key_path:
            assert isinstance(node, dict)
            node = node[key]
        return node

    def _apply_setting_change(
        self, key_path: tuple[str, ...], value: object, /
    ) -> bool:
        if self._is_settings_editable and not self._try_set_overrides(
            overrides=[(key_path, value)]
        ):
            self._sync_setting_controls(key_path=key_path)
            return False

        self._set_setting_value(key_path=key_path, value=value)
        self._sync_setting_controls(key_path=key_path)
        return True

    def _preview_shape_color(
        self, key_path: tuple[str, ...], value: list[int] | None, /
    ) -> None:
        if value is None:
            self._shape_color_preview = None
        else:
            SHAPE_COLOR_KEY_PATH_LENGTH: Final[int] = 3
            assert (
                len(key_path) == SHAPE_COLOR_KEY_PATH_LENGTH
                and key_path[0] == "shape_color"
            )
            # Copy only the edited section so dragging stays transient without
            # duplicating a potentially large Label map.
            preview = dict(self._config["shape_color"])
            section = dict(preview[key_path[1]])
            section[key_path[2]] = value
            preview[key_path[1]] = section
            self._shape_color_preview = preview
        self._refresh_shape_colors()

    def _try_set_overrides(
        self, *, overrides: list[tuple[tuple[str, ...], object]]
    ) -> bool:
        assert self._config_file is not None
        try:
            _config.set_overrides(config_file=self._config_file, overrides=overrides)
        except (OSError, ValueError) as e:
            QtWidgets.QMessageBox.warning(self, self.tr("Configuration Error"), str(e))
            return False
        return True

    def _sync_setting_controls(self, *, key_path: tuple[str, ...]) -> None:
        if self._settings_dialog is not None:
            self._settings_dialog.set_value(
                key_path=key_path,
                value=self._read_setting_value(key_path=key_path),
            )
        self._apply_to_live_widgets(key_path=key_path)

    def _apply_to_live_widgets(self, *, key_path: tuple[str, ...]) -> None:
        if key_path == ("color_theme",):
            # apply_color_theme -> setColorScheme emits colorSchemeChanged, which
            # drives _retheme; no explicit refresh needed here.
            _utils.apply_color_theme(theme=self._config["color_theme"])
        elif key_path in self._persistent_actions:
            action = self._persistent_actions[key_path]
            value = self._read_setting_value(key_path=key_path)
            assert isinstance(value, bool)
            with QtCore.QSignalBlocker(action):
                action.setChecked(value)
            if key_path == ("canvas", "fill_drawing"):
                self._canvas_widgets.canvas.set_fill_drawing(value=value)
        elif key_path == ("shape", "show_labels"):
            canvas = self._canvas_widgets.canvas
            canvas.set_show_labels(value=self._config["shape"]["show_labels"])
            canvas.update()
        elif key_path == ("mask_polygonization", "detail"):
            detail = self._config["mask_polygonization"]["detail"]
            self._ai_annotation.set_polygon_detail(detail)
            self._canvas_widgets.canvas.set_ai_polygon_detail(detail=detail)
        elif key_path == ("canvas", "allow_out_of_bounds_points"):
            canvas = self._canvas_widgets.canvas
            canvas.set_allow_out_of_bounds_points(
                value=self._config["canvas"]["allow_out_of_bounds_points"]
            )
            canvas.update()
        elif key_path[0] == "shape_color":
            self._refresh_shape_colors()
        elif key_path[0] == "labels":
            # Update predefined labels in place so session history (labels learned
            # from loaded/created shapes via add_label_history) is preserved, while
            # a removed predefined label drops from suggestions unless it was used
            # this session.
            self._label_dialog.set_predefined_labels(
                labels=self._config["labels"] or []
            )
            # The Label List dock is append-only (a shape's label stays after the
            # shape is deleted), so add new predefined labels and leave removed
            # ones until restart.
            for label in self._config["labels"] or []:
                if (
                    self._docks.unique_label_list.find_label_item(label=label)
                    is not None
                ):
                    continue
                self._docks.unique_label_list.add_label_item(
                    label=label,
                    color=self._get_rgb_by_label(
                        label=label,
                        unique_label_list=self._docks.unique_label_list,
                    ),
                )
        elif key_path == ("label_flags",):
            self._label_dialog.set_flag_rules(flags=self._config["label_flags"])
        elif key_path[0] == "flags":
            # The flag dock otherwise only repopulates on the next image load.
            # Refresh it now additively: add newly predefined flags (unchecked) and
            # keep every flag already in the dock with its checked state. Like the
            # label docks, a flag removed from the config lingers until the next
            # image load, so the edit never drops a flag the current image carries.
            self._load_flags(
                flags=self._read_flag_dock_states(), widget=self._docks.flag_list
            )
        elif key_path in (
            ("sort_labels",),
            ("show_label_text_field",),
            ("label_completion",),
        ):
            # LabelDialog reads these values only during construction.
            old_label_dialog = self._label_dialog
            self._label_dialog = self._make_label_dialog(
                label_history=old_label_dialog.label_history
            )
            old_label_dialog.deleteLater()
        elif key_path == ("ai", "default"):
            self._ai_annotation.set_current_model(
                model_display=self._config["ai"]["default"] or ""
            )
            self._canvas_widgets.canvas.set_ai_model_name(
                model_name=self._ai_annotation.current_model_id
            )
        elif key_path == ("ai", "text_model"):
            self._ai_text.set_model_name(
                model_name=self._config["ai"]["text_model"] or ""
            )
        elif key_path == ("ai", "suppress_existing_shape_matches"):
            self._canvas_widgets.canvas.set_ai_existing_shape_suppression(
                enabled=self._config["ai"]["suppress_existing_shape_matches"]
            )

    def _refresh_shape_colors(self) -> None:
        unique_labels = self._docks.unique_label_list
        for row in range(unique_labels.count()):
            item = unique_labels.item(row)
            assert item is not None
            label = item.data(Qt.ItemDataRole.UserRole)
            color = self._get_rgb_by_label(label=label, unique_label_list=unique_labels)
            item.setData(LABEL_COLOR_ROLE, QtGui.QColor(*color))
        for item in self._docks.label_list:
            shape = item.shape()
            assert shape is not None and shape.label is not None
            item.set_label(
                text=format_shape_label(shape=shape),
                color=self._get_rgb_by_label(
                    label=shape.label, unique_label_list=unique_labels
                ),
            )
        # The canvas resolves colors during painting; the docks cache them.
        self._canvas_widgets.canvas.update()

    def _read_flag_dock_states(self) -> dict[str, bool]:
        flags: dict[str, bool] = {}
        for i in range(self._docks.flag_list.count()):
            item = self._docks.flag_list.item(i)
            assert item is not None
            flags[item.text()] = item.checkState() == Qt.CheckState.Checked
        return flags

    def _ensure_ai_model_ready(self, model_name: str, /) -> bool:
        if model_name and self._model_manager.is_ready(model_name):
            return True
        self._open_models()
        return False

    def _refresh_model_availability(self) -> None:
        available = {
            name
            for name in self._model_manager.models
            if self._model_manager.is_ready(name)
        }
        downloading = set(self._model_manager.queue)
        if self._model_manager.active is not None:
            downloading.add(self._model_manager.active)
        for widget in (self._ai_annotation, self._ai_text):
            widget.set_available_models(available=available, downloading=downloading)
        self._canvas_widgets.canvas.set_ai_model_name(
            model_name=self._ai_annotation.current_model_id
        )

    def _download_and_select(
        self, model_name: str, /, *, select: Callable[[str], None]
    ) -> None:
        notice = license_notice(model_name)
        if notice is not None:
            message = QtWidgets.QMessageBox(self)
            message.setWindowTitle(
                self.tr("Download {model}").format(
                    model=self._model_manager.models[model_name]
                )
            )
            message.setIcon(QtWidgets.QMessageBox.Icon.Information)
            message.setTextFormat(Qt.TextFormat.RichText)
            message.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextBrowserInteraction
            )
            message.setText(f"{html.escape(notice)}<br><br>{license_link(model_name)}")
            download = message.addButton(
                self.tr("Download"), QtWidgets.QMessageBox.ButtonRole.AcceptRole
            )
            message.addButton(QtWidgets.QMessageBox.StandardButton.Cancel)
            message.exec()
            if message.clickedButton() is not download:
                return
        select(model_name)
        self._model_manager.enqueue(model_name)

    def _remove_ai_model(self, model_name: str, /) -> None:
        option = _ai_models.find_ai_assist_model_option(model_name=model_name)
        overrides = []
        if option is not None and self._config["ai"]["default"] == option.display_name:
            overrides.append((("ai", "default"), None))
        if self._config["ai"]["text_model"] == model_name:
            overrides.append((("ai", "text_model"), None))
        if (
            overrides
            and self._is_settings_editable
            and not self._try_set_overrides(overrides=overrides)
        ):
            return
        for key_path, value in overrides:
            self._set_setting_value(key_path=key_path, value=value)
            self._sync_setting_controls(key_path=key_path)
        if (
            self._text_osam_session is not None
            and self._text_osam_session.model_name == model_name
        ):
            self._text_osam_session = None
        if self._canvas_widgets.canvas.get_ai_model_name() == model_name:
            self._canvas_widgets.canvas.set_ai_model_name(model_name="")

        self._model_manager.remove(model_name)

    def _open_models(self) -> None:
        if self._models_dialog is None:
            self._models_dialog = ModelsDialog(
                manager=self._model_manager,
                remove_model=self._remove_ai_model,
                parent=self,
            )
        self._model_manager.refresh()
        self._models_dialog.show()
        self._models_dialog.raise_()
        self._models_dialog.activateWindow()

    def _open_settings(self) -> None:
        # Keep a single dialog instance; it edits self._config by reference, so
        # reopening it shows the current values without rebuilding.
        if self._settings_dialog is None:
            self._settings_dialog = SettingsDialog(
                config=self._config,
                apply_setting=self._apply_setting_change,
                preview_shape_color=self._preview_shape_color,
                open_as_text=self._open_config_file,
                settings_editable=self._is_settings_editable,
                parent=self,
            )
        self._settings_dialog.show()
        self._settings_dialog.raise_()
        self._settings_dialog.activateWindow()

    def _open_config_file(self) -> None:
        # Command-line overrides cannot be edited through a config file.
        assert self._config_file is not None
        config_file: Path = self._config_file

        # Hand off to the text editor: close the dialog first so flush-on-close
        # persists current values, then drop it so a later Close cannot overwrite
        # the hand-edits.
        if self._settings_dialog is not None:
            self._settings_dialog.close()
            self._settings_dialog.deleteLater()
            self._settings_dialog = None

        system: str = platform.system()
        if system == "Darwin":
            subprocess.Popen(["open", "-t", config_file])
        elif system == "Windows":
            os.startfile(config_file)  # ty: ignore[unresolved-attribute]  # Windows-only
        else:
            subprocess.Popen(["xdg-open", config_file])

    def has_label_file(self) -> bool:
        if self._image_path is None:
            return False

        label_path = self._own_label_file_path()
        return label_path is not None and Path(label_path).exists()

    def _own_label_file_path(self) -> str | None:
        # Unlike current_label_file_path, never a destination that may hold
        # another Image's Annotation File.
        assert self._image_path is not None
        return self._label_file_path or _find_label_path(
            image_path=self._file_list_image_path or self._image_path,
            output_dir=self._output_dir,
            root_prefix=self._file_list_root_prefix,
            cached=False,
        )

    def _can_continue(self) -> bool:
        self._wait_for_save()
        if not self._is_changed:
            return True
        prompt_text = self.tr('Keep the annotation changes for "{}"?').format(
            self._image_path
        )
        user_choice = QtWidgets.QMessageBox.question(
            self,
            self.tr("Unsaved Changes"),
            prompt_text,
            QtWidgets.QMessageBox.StandardButton.Save
            | QtWidgets.QMessageBox.StandardButton.Discard
            | QtWidgets.QMessageBox.StandardButton.Cancel,
            QtWidgets.QMessageBox.StandardButton.Save,
        )
        if user_choice == QtWidgets.QMessageBox.StandardButton.Save:
            self._save_label_file(save_as=False)
            return not self._is_changed
        return user_choice == QtWidgets.QMessageBox.StandardButton.Discard

    def show_error_message(self, *, title: str, message: str) -> int:
        return QtWidgets.QMessageBox.critical(
            self, title, f"<p><b>{title}</b></p>{message}"
        )

    def _show_file_open_error(
        self,
        *,
        path: str,
        file_kind: Literal["label", "image"],
        exc: BaseException | None,
        extra: str | None,
    ) -> None:
        if isinstance(exc, ImageNotFoundError):
            dialog = QtWidgets.QMessageBox(self)
            dialog.setIcon(QtWidgets.QMessageBox.Icon.Critical)
            dialog.setWindowTitle(self.tr("Image Not Found"))
            dialog.setTextFormat(Qt.TextFormat.PlainText)
            dialog.setText(
                self.tr(
                    'This annotation refers to "{name}", but that image could not '
                    "be found.\n\nExpected location: {path}"
                ).format(name=Path(exc.image_path).name, path=exc.image_path)
            )
            dialog.setDetailedText(str(exc.__cause__))
            dialog.exec()
            self.show_status_message(
                self.tr("Failed to load: {path}").format(path=path)
            )
            return
        if file_kind == "label":
            message = self.tr(
                "The selected annotation file could not be opened: {path}"
            ).format(path=path)
        else:
            message = self.tr(
                "The selected image file could not be opened: {path}"
            ).format(path=path)
        # read_label_file wraps the error when the label refers to the image.
        too_large = exc.__cause__ if isinstance(exc, LabelFileReadError) else exc
        if isinstance(too_large, ImageTooLargeError):
            extra = _make_raster_side_message(
                width=too_large.width, height=too_large.height
            )
        elif exc is not None:
            message = f"{message}\n\n{exc}"
        if extra:
            message = f"{message}\n\n{extra}"
        QtWidgets.QMessageBox.critical(self, self.tr("Error Opening File"), message)
        self.show_status_message(self.tr("Failed to load: {path}").format(path=path))

    def current_path(self) -> str:
        return str(Path(self._image_path).parent) if self._image_path else "."

    def remove_selected_point(self) -> None:
        if not self._canvas_widgets.canvas.remove_selected_point():
            return
        if (
            self._canvas_widgets.canvas.hovered_shape
            and len(self._canvas_widgets.canvas.hovered_shape.points) == 0
        ):
            self._canvas_widgets.canvas.delete_shape(
                shape=self._canvas_widgets.canvas.hovered_shape
            )
            self.remove_labels(shapes=[self._canvas_widgets.canvas.hovered_shape])
        self.mark_dirty()

    def delete_selected_shapes(self) -> None:
        self.remove_labels(shapes=self._canvas_widgets.canvas.delete_selected())
        self.mark_dirty()

    def _load_from_file_or_dir(self, *, file_or_dir: str) -> None:
        if not file_or_dir:
            raise ValueError("file_or_dir cannot be empty")

        if is_label_file_path(filename=file_or_dir):
            # Load before dropping the Image List, so a failed load leaves the
            # previous session and Image List untouched.
            if not self._load_file(image_or_label_path=file_or_dir):
                return
            self._loaded_image_paths = []
            self._file_list_root_prefix = None
            self._refresh_file_list()
            self._docks.annotation_folder_footer.set_missing(None)
            self._docks.file_dock.setEnabled(False)
            self._docks.file_dock.setToolTip(
                self.tr("Image List is disabled when an annotation file is opened")
            )
            return

        if Path(file_or_dir).is_dir():
            # Settle unsaved changes before the Annotation Folder switches, so
            # a Save still goes where the open image saves. A Discard is final:
            # loading the folder's first image must not ask again after the
            # switch.
            if not self._can_continue():
                return
            self.mark_clean()
            opened_dir = file_or_dir
            previous_label_path = (
                self.current_label_file_path() if self._image_path else None
            )
            missing_output_dir = self._restore_remembered_output_dir(
                opened_dir=opened_dir
            )
            self._import_images_from_dir(root_dir=opened_dir)
            loaded = False
            if self.image_list:
                # Selecting the first row emits no change signal when it is
                # already current (reopening the same directory), so drive the
                # reload directly while retaining the prior item for rollback.
                file_list = self._docks.file_list
                previous_item = file_list.currentItem()
                with QtCore.QSignalBlocker(file_list):
                    file_list.setCurrentRow(0)
                loaded = self._load_selected_image(
                    file_list.currentItem(), previous_item
                )
                file_list.repaint()
            # A failed load keeps the previous image open beside the new
            # folder's Images: the new Annotation Folder serves those Images,
            # and the open image keeps saving where it did.
            if not loaded and previous_label_path is not None:
                self._label_file_path = previous_label_path
                self._auto_save_path = previous_label_path
        else:
            opened_dir = str(Path(file_or_dir).parent)
            previous_output_dir = self._output_dir
            previous_root_prefix = self._file_list_root_prefix
            missing_output_dir = self._restore_remembered_output_dir(
                opened_dir=opened_dir
            )
            # The Annotation File mirrors the image's place under the folder
            # being opened, not the one being replaced.
            self._file_list_root_prefix = opened_dir
            # Load before swapping the Image List, so a failed load leaves the
            # previous session and Image List untouched.
            if not self._load_file(image_or_label_path=file_or_dir):
                self._output_dir = previous_output_dir
                self._file_list_root_prefix = previous_root_prefix
                return
            self._import_images_from_dir(root_dir=opened_dir)
            # The load ran before the Image List knew the neighbors.
            self._prefetch_neighbors()

        # Set only once the open succeeded, so a rolled-back open keeps the
        # previous session's warning.
        self._docks.annotation_folder_footer.set_missing(missing_output_dir)
        # Shown last so the loading messages do not replace it.
        if missing_output_dir is not None:
            self.statusBar().showMessage(
                self.tr("Annotation Folder not found: %s") % missing_output_dir
            )

    def _restore_remembered_output_dir(self, *, opened_dir: str) -> str | None:
        remembered = self._remembered_output_dirs().get(os.path.abspath(opened_dir))
        # Report a missing folder to the caller but keep its entry: it may be
        # on a drive that is not mounted right now, and choosing another
        # folder replaces it.
        if remembered is not None and not Path(remembered).is_dir():
            self._output_dir = None
            return remembered
        self._output_dir = Path(remembered) if remembered else None
        return None

    def _remembered_output_dirs(self) -> dict[str, str]:
        return cast(
            dict[str, str], self._window_state.value(ANNOTATION_FOLDERS_KEY, {})
        )

    def _remember_output_dir(self, *, opened_dir: str) -> None:
        folders = self._remembered_output_dirs()
        key = os.path.abspath(opened_dir)
        if self._output_dir is None:
            folders.pop(key, None)
        else:
            folders[key] = os.path.abspath(self._output_dir)
        self._window_state.setValue(ANNOTATION_FOLDERS_KEY, folders)

    def _open_dir_with_dialog(self) -> None:
        # Unsaved changes are settled once a folder is chosen.
        default_open_dir_path: str
        if self._prev_opened_dir and Path(self._prev_opened_dir).exists():
            default_open_dir_path = self._prev_opened_dir
        else:
            default_open_dir_path = (
                str(Path(self._image_path).parent) if self._image_path else "."
            )

        dir_path = str(
            QtWidgets.QFileDialog.getExistingDirectory(
                self,
                self.tr("Open Folder"),
                default_open_dir_path,
                QtWidgets.QFileDialog.Option.ShowDirsOnly
                | QtWidgets.QFileDialog.Option.DontResolveSymlinks,
            )
        )
        if dir_path:
            self._load_from_file_or_dir(file_or_dir=dir_path)

    @property
    def image_list(self) -> list[str]:
        lst = []
        for i in range(self._docks.file_list.count()):
            item = self._docks.file_list.item(i)
            assert item
            lst.append(_file_list_item_path(item))
        return lst

    def import_dropped_image_files(self, *, image_files: list[str]) -> None:
        extensions = _list_supported_image_extensions()
        already_loaded = set(self._loaded_image_paths)
        new_files = [
            path
            for path in image_files
            if path not in already_loaded and path.lower().endswith(extensions)
        ]
        if not new_files:
            return

        self._loaded_image_paths.extend(new_files)
        self._refresh_file_list()

        visible_image_paths = self.image_list
        for image_path in new_files:
            if image_path in visible_image_paths:
                self._docks.file_list.setCurrentRow(
                    visible_image_paths.index(image_path)
                )
                self._docks.file_list.repaint()
                return

    def _import_images_from_dir(self, *, root_dir: str | None) -> None:
        if not root_dir:
            return

        self._docks.file_dock.setEnabled(True)
        self._docks.file_dock.setToolTip("")

        self._prev_opened_dir = root_dir
        self._file_list_root_prefix = root_dir
        self._loaded_image_paths = _scan_image_files(root_dir=root_dir)
        self._refresh_file_list()

    def _refresh_file_list(self) -> None:
        # The Annotation Folder is remembered per opened folder, so choosing
        # one needs a folder, and the footer has nothing to count without
        # images.
        has_folder = self._file_list_root_prefix is not None
        self._actions.change_output_dir.setEnabled(has_folder)
        self._docks.annotation_folder_footer.setVisible(
            has_folder and bool(self._loaded_image_paths)
        )
        image_paths = []
        self._hidden_annotated_paths = set()
        for path in self._loaded_image_paths:
            if self._matches_file_search(path):
                image_paths.append(path)
            elif _has_label_file(
                image_path=path,
                output_dir=self._output_dir,
                root_prefix=self._file_list_root_prefix,
            ):
                self._hidden_annotated_paths.add(path)

        file_list = self._docks.file_list
        with QtCore.QSignalBlocker(file_list):
            file_list.clear()
            for image_path in image_paths:
                file_list.addItem(
                    _make_image_list_item(
                        image_path=image_path,
                        label=self._file_list_label(image_path),
                        output_dir=self._output_dir,
                        root_prefix=self._file_list_root_prefix,
                    )
                )
            if self._file_list_image_path in image_paths:
                file_list.setCurrentRow(image_paths.index(self._file_list_image_path))

        self._update_annotated_count()
        self._sync_navigation_actions()
        self.setWindowTitle(self._get_window_title(dirty=self._is_changed))

    def _refresh_image_list_checkmarks(self, *, label_path: str) -> None:
        # Save As can write or delete any image's Annotation File, so re-apply
        # the build-time rule to every item that could own this file.
        # ponytail: matched by stem to keep auto-save cheap on large folders; an
        # Annotation File symlinked under another name stays stale until the
        # list is rebuilt. Drop the filter if that matters.
        # An extension-qualified x.png.json belongs to an Image with stem x
        # (see _label_path_candidates).
        stems = {_comparable_stem(label_path), _comparable_stem(Path(label_path).stem)}
        file_list = self._docks.file_list
        for row in range(file_list.count()):
            item = file_list.item(row)
            assert item
            if _comparable_stem(_file_list_item_path(item)) in stems:
                _set_annotated_check_state(
                    item,
                    output_dir=self._output_dir,
                    root_prefix=self._file_list_root_prefix,
                )

        # Images hidden by the search box have no item, so keep the count's
        # record of them by the same rule.
        for image_path in self._loaded_image_paths:
            if _comparable_stem(image_path) not in stems or self._matches_file_search(
                image_path
            ):
                continue
            if _has_label_file(
                image_path=image_path,
                output_dir=self._output_dir,
                root_prefix=self._file_list_root_prefix,
            ):
                self._hidden_annotated_paths.add(image_path)
            else:
                self._hidden_annotated_paths.discard(image_path)
        self._update_annotated_count()

    def _update_annotated_count(self) -> None:
        file_list = self._docks.file_list
        visible = sum(
            file_list.item(row).checkState() == Qt.CheckState.Checked
            for row in range(file_list.count())
        )
        self._docks.annotation_folder_footer.set_count(
            annotated=len(self._hidden_annotated_paths) + visible,
            total=len(self._loaded_image_paths),
        )

    def _file_list_label(self, image_path: str, /) -> str:
        # Paths under the opened folder are shown relative to it so the
        # Image List stays readable; the full path stays in the tooltip.
        relative = _relative_to_root(image_path, self._file_list_root_prefix)
        return image_path if relative is None else relative

    def _matches_file_search(self, image_path: str, /) -> bool:
        return bool(self._file_search_pattern.search(self._file_list_label(image_path)))

    def _update_status_stats(self, mouse_pos: QtCore.QPointF, /) -> None:
        self._status_mouse_pos = QtCore.QPointF(mouse_pos)
        self._refresh_status_stats()

    def _refresh_status_stats(self) -> None:
        stats: list[str] = []
        stats.append(f"mode={self._canvas_widgets.canvas.mode.name}")
        if self._status_mouse_pos is not None:
            stats.append(
                f"x={self._status_mouse_pos.x():6.1f}, "
                f"y={self._status_mouse_pos.y():6.1f}"
            )
        self._status_bar.stats.setText(" | ".join(stats))


def _shapes_from_dicts(
    *,
    shape_dicts: list[ShapeDict],
    label_flags: dict[str, list[str]] | None,
) -> list[Shape]:
    shapes: list[Shape] = []
    for shape_dict in shape_dicts:
        shape = Shape(
            label=shape_dict["label"],
            shape_type=cast(ShapeType, shape_dict["shape_type"]),
            group_id=shape_dict["group_id"],
            description=shape_dict["description"],
            mask=shape_dict["mask"],
            points=np.array(shape_dict["points"], dtype=np.float64),
            closed=True,
        )

        shape.flags = shape_dict["flags"]
        shape.other_data = shape_dict["other_data"]
        shape.locked = shape_dict["locked"]

        shapes.append(shape)
    apply_default_flags(shapes=shapes, label_flags=label_flags)
    return shapes


def _resolve_text_annotation_shape_type(
    *, create_mode: str, ai_output_format: _automation.AiOutputFormat
) -> _automation.AiOutputFormat | None:
    if create_mode in _AI_CREATE_MODES:
        return ai_output_format
    if create_mode in typing.get_args(_TextToAnnotationCreateMode):
        return cast(_TextToAnnotationCreateMode, create_mode)
    return None


def _is_valid_label(
    *, label: str, existing_labels: list[str], policy: str | None
) -> bool:
    if policy is None:
        return True
    if policy == "exact":
        return label in existing_labels
    return False


def _format_window_title(
    *,
    image_path: str | None,
    file_index: int | None,
    file_count: int,
    dirty: bool,
) -> str:
    title = __appname__
    if image_path:
        title = f"{title} - {image_path}"
        if file_count and file_index is not None:
            title = f"{title} [{file_index + 1}/{file_count}]"
    if dirty:
        title = f"{title}*"
    return title


def _resolve_label_path(
    *, image_path: str, output_dir: Path | None, root_prefix: str | None
) -> str:
    # The Image's Annotation File, or where a new one is written.
    if found := _find_label_path(
        image_path=image_path,
        output_dir=output_dir,
        root_prefix=root_prefix,
        cached=False,
    ):
        return found
    candidates = _label_path_candidates(
        image_path=image_path, output_dir=output_dir, root_prefix=root_prefix
    )
    # Never default to another Image's Annotation File. With every candidate
    # taken, the save refuses to overwrite the first one.
    return str(next((c for c in candidates if not c.exists()), candidates[0]))


def _find_label_path(
    *,
    image_path: str,
    output_dir: Path | None,
    root_prefix: str | None,
    cached: bool,
) -> str | None:
    for candidate in [
        *_label_path_candidates(
            image_path=image_path, output_dir=output_dir, root_prefix=root_prefix
        ),
        *_legacy_label_path_candidates(
            image_path=image_path, output_dir=output_dir, root_prefix=root_prefix
        ),
    ]:
        if _label_file_belongs_to_image(
            label_path=candidate, image_path=image_path, cached=cached
        ):
            return str(candidate)
    return None


def _label_path_candidates(
    *, image_path: str, output_dir: Path | None, root_prefix: str | None
) -> list[Path]:
    image = Path(image_path)
    if output_dir is None:
        parent = image.parent
    else:
        # Mirror the opened folder's subfolders, so Images sharing a name in
        # different subfolders keep separate Annotation Files.
        relative = _relative_to_root(image_path, root_prefix)
        parent = output_dir if relative is None else output_dir / Path(relative).parent
    return _label_names_in(parent, image)


def _legacy_label_path_candidates(
    *, image_path: str, output_dir: Path | None, root_prefix: str | None
) -> list[Path]:
    # Annotation Folders written before mirroring are flat. Their files are
    # still read, but new ones go to the mirrored subfolder.
    relative = _relative_to_root(image_path, root_prefix)
    if output_dir is None or relative is None or Path(relative).parent == Path():
        return []
    return _label_names_in(output_dir, Path(image_path))


def _label_names_in(parent: Path, image: Path, /) -> list[Path]:
    # _refresh_image_list_checkmarks maps both names back to the stem.
    # The stem name is the convention other tools read. Images sharing a stem in
    # one folder (x.jpg, x.png) cannot both have it, so the next one keeps its
    # extension (x.png.json).
    return [
        parent / f"{image.stem}{LABEL_FILE_SUFFIX}",
        parent / f"{image.name}{LABEL_FILE_SUFFIX}",
    ]


def _relative_to_root(path: str, root_prefix: str | None, /) -> str | None:
    if root_prefix is None:
        return None
    try:
        # A prefix check would miss "./a.jpg" under the opened folder ".",
        # which the scan lists as "a.jpg".
        relative = os.path.relpath(path, root_prefix)
    except ValueError:  # Windows paths on different drives
        return None
    if relative == os.pardir or relative.startswith(os.pardir + os.sep):
        return None
    return relative


def _label_file_belongs_to_image(
    *, label_path: Path, image_path: str, cached: bool
) -> bool:
    # An Annotation File records its Image in imagePath; the file name alone
    # cannot tell Images sharing a stem apart.
    try:
        stat = label_path.stat()
    except OSError:
        return False
    stored = (
        _read_stored_image_path_cached(str(label_path), stat.st_mtime_ns, stat.st_size)
        if cached
        else _read_stored_image_path(str(label_path))
    )
    if stored is None:
        # Unreadable: claim it, so opening the Image reports the error instead
        # of hiding the file and saving over it.
        return True
    if os.path.exists(stored):
        try:
            return os.path.samefile(stored, image_path)
        except OSError:
            return False
    # The recorded Image is gone, e.g. moved with its folder or embedded from
    # elsewhere. Moved Images keep their names, so a name that matches another
    # Image beside this one is that Image's.
    image = Path(image_path)
    stored_name = Path(stored).name
    return (
        os.path.normcase(stored_name) == os.path.normcase(image.name)
        or not (image.parent / stored_name).exists()
    )


# The Image List checks every Image on each rebuild and search keystroke, so
# its check marks parse each Annotation File once per revision. A rewrite of
# the same size within one timestamp tick keeps a stale check mark, so loading,
# saving and Delete read the file fresh.
# ponytail: the first parse reads the whole file, ~0.6 ms with embedded image
# data; stop reading at imagePath if first builds of such folders are slow.
@functools.lru_cache(maxsize=65536)
def _read_stored_image_path_cached(
    label_path: str, _mtime_ns: int, _size: int, /
) -> str | None:
    return _read_stored_image_path(label_path)


def _read_stored_image_path(label_path: str, /) -> str | None:
    try:
        image_path = read_label_file_image_path(filename=label_path)
    except LabelFileReadError:
        return None
    return str(Path(label_path).parent / image_path)


def _resolve_stored_image_path(*, image_path: str, label_dir: Path) -> str:
    try:
        image = Path(image_path)
        relative_path = os.path.relpath(image_path, label_dir)
        if os.path.realpath(label_dir / relative_path) != os.path.realpath(image):
            # Parent traversal follows directory symlinks, unlike lexical path math.
            # Keep valid project links and the source filename when correcting it.
            relative_path = os.path.relpath(
                os.path.join(os.path.realpath(image.parent), image.name),
                os.path.realpath(label_dir),
            )
        return relative_path
    except ValueError:
        # Windows drives have no relative path between them; an absolute path
        # costs portability but beats failing the save.
        return os.path.abspath(image_path)


def _make_image_list_item(
    *, image_path: str, label: str, output_dir: Path | None, root_prefix: str | None
) -> QtWidgets.QListWidgetItem:
    item = QtWidgets.QListWidgetItem(label)
    item.setData(Qt.ItemDataRole.UserRole, image_path)
    item.setToolTip(os.path.abspath(image_path))
    item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
    _set_annotated_check_state(item, output_dir=output_dir, root_prefix=root_prefix)
    return item


def _comparable_stem(path: str, /) -> str:
    # Over-matching only re-checks extra items, so fold the case and Unicode
    # forms a filesystem may treat as the same name.
    return unicodedata.normalize("NFC", Path(path).stem).casefold()


def _set_annotated_check_state(
    item: QtWidgets.QListWidgetItem,
    /,
    *,
    output_dir: Path | None,
    root_prefix: str | None,
) -> None:
    has_label = _has_label_file(
        image_path=_file_list_item_path(item),
        output_dir=output_dir,
        root_prefix=root_prefix,
    )
    item.setCheckState(Qt.CheckState.Checked if has_label else Qt.CheckState.Unchecked)


def _has_label_file(
    *, image_path: str, output_dir: Path | None, root_prefix: str | None
) -> bool:
    return (
        _find_label_path(
            image_path=image_path,
            output_dir=output_dir,
            root_prefix=root_prefix,
            cached=True,
        )
        is not None
    )


def _file_list_item_path(item: QtWidgets.QListWidgetItem, /) -> str:
    return item.data(Qt.ItemDataRole.UserRole)


def _shape_to_dict(shape: Shape, /) -> ShapeDict:
    assert shape.label is not None
    return ShapeDict(
        label=shape.label,
        points=shape.points.tolist(),
        shape_type=shape.shape_type,
        flags=dict(shape.flags or {}),
        description=shape.description or "",
        group_id=shape.group_id,
        mask=None if shape.mask is None else shape.mask.copy(),
        locked=shape.locked,
        other_data=copy.deepcopy(shape.other_data),
    )


def _max_decode_mb() -> int | None:
    limit_mb = QtGui.QImageReader.allocationLimit()
    return limit_mb if limit_mb > 0 else None  # 0 disables the limit


def _make_raster_side_message(*, width: int, height: int) -> str:
    return QtCore.QCoreApplication.translate(
        "MainWindow",
        "The image is too large to open: {width}x{height} pixels exceeds the "
        "{max_side} pixel per-side limit of the raster engine. Raising the "
        "decode limit will not help. Split the image into tiles (for example "
        "with gdal_retile.py) or open a smaller copy.",
    ).format(
        width=width,
        height=height,
        max_side=RASTER_MAX_SIDE,
    )


def _make_image_too_large_message(*, image_data: bytes) -> str | None:
    # None means the failure is not explained by image size, so the caller
    # falls back to the generic unsupported-format message.

    requirement = get_image_decode_requirement(image_data=image_data)
    if requirement is None:
        return None
    width = requirement.width
    height = requirement.height

    if max(width, height) > RASTER_MAX_SIDE:
        return _make_raster_side_message(width=width, height=height)

    limit_mb = QtGui.QImageReader.allocationLimit()
    if limit_mb <= 0:  # 0 disables the limit
        return None
    if requirement.required_mb <= limit_mb:
        return None

    # ceil never renders "needs about N MB" with N equal to the limit, which
    # round could when the overage is fractional.
    return QtCore.QCoreApplication.translate(
        "MainWindow",
        "The image is too large to open: {width}x{height} pixels needs about "
        "{required} MB, but the decode limit is {limit} MB. Split the image into "
        "tiles (for example with gdal_retile.py) or open a smaller copy.",
    ).format(
        width=width,
        height=height,
        required=requirement.required_mb,
        limit=limit_mb,
    )


def _list_supported_image_extensions() -> tuple[str, ...]:
    return tuple(
        f".{fmt.toStdString().lower()}"
        for fmt in QtGui.QImageReader.supportedImageFormats()
    )


def _extract_dropped_image_paths(*, mime: QtCore.QMimeData) -> list[str]:
    extensions = _list_supported_image_extensions()
    # QUrl separates with forward slashes even on Windows, while the file
    # list holds the separator of the platform, so an unnormalized drop
    # would list an image the directory scan already listed a second time.
    local_paths = (os.path.normpath(url.toLocalFile()) for url in mime.urls())
    return [path for path in local_paths if path.lower().endswith(extensions)]


def _scan_image_files(*, root_dir: str) -> list[str]:
    extensions = _list_supported_image_extensions()

    # (path below root_dir, path) pairs. Every path shares the root_dir prefix,
    # so sorting by the part below it gives the same order, and natsort's key
    # cost grows with path depth (~5x faster for a typical absolute root_dir).
    images: list[tuple[str, str]] = []
    for root, dirs, files in os.walk(root_dir):
        root_below = os.path.relpath(root, root_dir)
        for file in files:
            if file.lower().endswith(extensions):
                images.append(
                    (
                        os.path.normpath(os.path.join(root_below, file)),
                        os.path.normpath(os.path.join(root, file)),
                    )
                )

    logger.debug("found {:d} images in {!r}", len(images), root_dir)
    try:
        images = natsort.os_sorted(images, key=operator.itemgetter(0))
    except OSError:
        logger.warning(
            "natsort.os_sorted failed (known macOS strxfrm bug), "
            "falling back to locale-unaware natural sort"
        )
        images = natsort.natsorted(images, key=operator.itemgetter(0))
    return [path for _, path in images]
