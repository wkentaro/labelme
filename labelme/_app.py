from __future__ import annotations

import contextlib
import copy
import dataclasses
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
import webbrowser
from collections.abc import Callable
from pathlib import Path
from typing import Final
from typing import Literal
from typing import NamedTuple
from typing import cast
from typing import override

import natsort
import numpy as np
import PIL.features
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
from . import _image_codec
from . import _label_file
from . import _label_flags
from . import _label_path
from . import _save_request
from . import _shape
from . import _shape_color
from . import _utils
from . import _widgets
from ._image_prefetcher import ImagePrefetcher
from ._label_file import Annotation
from ._label_file import ImageDecodeLimitError
from ._label_file import ImageNotFoundError
from ._label_file import ImageTooLargeError
from ._label_file import LabelFileError
from ._label_file import LabelFileReadError
from ._model_manager import ModelManager
from ._save_request import SaveRequest
from ._save_writer import SaveWriter
from ._shape import ConvertBlocker
from ._shape import ConvertTarget
from ._shape import MergeBlocker
from ._shape import Shape
from ._shape import ShapeDict
from ._shape import ShapeType
from ._shape_clipboard import ShapeClipboard
from ._utils import ImageDecodeRequirement
from ._widgets import AiAssistedAnnotationWidget
from ._widgets import AiTextToAnnotationWidget
from ._widgets import AiToolGroup
from ._widgets import AnnotationFolderFooter
from ._widgets import BrightnessContrastDialog
from ._widgets import Canvas
from ._widgets import ConversionDetailDialog
from ._widgets import EmptyStateWidget
from ._widgets import ImageListDelegate
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


@dataclasses.dataclass(frozen=True, eq=False)
class _AiTextJob:
    pixmap_key: int
    texts: list[str]
    shape_type: _automation.AiOutputFormat
    iou_threshold: float
    score_threshold: float
    image_size: tuple[int, int] | None

    @property
    def query(self) -> str:
        return ", ".join(text.strip() for text in self.texts)


class _AiStatus(NamedTuple):
    # The AI job the status bar shows, when it started, and which of its
    # "task" and slow stages were announced.
    job: object
    started_at: float
    announced: frozenset[str]


class _OpenedFolder(NamedTuple):
    # The folder whose Images the Image List shows, with the Annotation Folder
    # they use. A None root is no opened folder, as for an Annotation File
    # opened directly.
    root: str | None
    output_dir: Path | None
    image_paths: tuple[str, ...]


class _FileContents(NamedTuple):
    # What an Annotation File holds, as a save writes it. A None path is an
    # Image that has no file.
    path: str | None
    shapes: list[ShapeDict]
    flags: dict[str, bool]


class _SaveTarget(NamedTuple):
    # Where a save that asks nothing writes the open document.
    path: str
    # The user chose path in a dialog that confirmed any overwrite.
    overwrite_confirmed: bool


class _ZoomMode(enum.Enum):
    FIT_WINDOW = enum.auto()
    FIT_SELECTION = enum.auto()
    MANUAL_ZOOM = enum.auto()


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
    ai: QtWidgets.QLabel


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
    file_list_delegate: ImageListDelegate


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
    convert: dict[ConvertTarget, QtGui.QAction]
    lock: QtGui.QAction
    undo_last_point: QtGui.QAction
    undo: QtGui.QAction
    add_point_to_edge: QtGui.QAction
    create_mode: QtGui.QAction
    edit_mode: QtGui.QAction
    create_rectangle_mode: QtGui.QAction
    create_point_mode: QtGui.QAction
    create_ai_segment_mode: QtGui.QAction
    create_ai_find_all_mode: QtGui.QAction
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
    shape_context_menu: tuple[QtGui.QAction, ...]
    canvas_context_menu: tuple[QtGui.QAction, ...]
    edit_menu: tuple[QtGui.QAction, ...]


class _Menus(NamedTuple):
    file: QtWidgets.QMenu
    edit: QtWidgets.QMenu
    view: QtWidgets.QMenu
    help: QtWidgets.QMenu
    label_list: QtWidgets.QMenu


def _default_window_geometry(
    *, available: QtCore.QRect, toolbar_width: int
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
    _label_list_menu_origin: QtCore.QPoint | None
    _large_image_confirmed: bool
    _save_revision: int
    _save_target: _SaveTarget | None
    _save_writer: SaveWriter
    _image_prefetcher: ImagePrefetcher
    _model_manager: ModelManager
    _osam_worker: _automation.OsamWorker
    _ai_text_job: _AiTextJob | None
    _ai_status: _AiStatus
    _ai_status_timer: QtCore.QTimer
    _hidden_annotated_paths: set[str]
    _window_state: QtCore.QSettings

    _config_file: Path | None
    _config: dict
    _config_overrides: dict

    _is_changed: bool = False
    # To tell when Undo returns to the file.
    _file_contents: _FileContents
    _shape_clipboard: ShapeClipboard
    _zoom_mode: _ZoomMode
    _is_canvas_pointer_active: bool = False
    _is_fit_selection_deferred: bool = False
    _fit_selection_timer: QtCore.QTimer
    _prev_opened_dir: str | None
    _canvas_widgets: _CanvasWidgets
    _status_bar: _StatusBarWidgets
    _zoom_mode_label: QtWidgets.QLabel
    _zoom_mode_captions: dict[_ZoomMode, str]
    _docks: _DockWidgets
    _flag_dock_wanted: bool
    _actions: _Actions
    _persistent_actions: dict[tuple[str, ...], QtGui.QAction]
    _menus: _Menus
    _label_dialog: LabelDialog
    _settings_dialog: SettingsDialog | None = None
    _models_dialog: ModelsDialog | None = None
    _shape_color_preview: dict | None
    _ai_annotation: AiAssistedAnnotationWidget
    _ai_text: AiTextToAnnotationWidget
    _ai_group: AiToolGroup

    _opened_folder_value: _OpenedFolder
    _image: QtGui.QImage
    _annotation: Annotation | None
    _label_file_path: str | None
    _failed_save_path: str | None
    _image_path: str | None
    _file_list_image_path: str | None
    _file_search_pattern: re.Pattern[str]
    _prev_image_path: str | None
    _viewport_states: dict[str, _ViewportState]
    _brightness_contrast_values: dict[str, tuple[int | None, int | None]]
    # The last Polygon Detail a Conversion used, apart from AI Assist's.
    _conversion_detail: int
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
        # Qt's own default is 256 MB, about 8192x8192 pixels.
        QtGui.QImageReader.setAllocationLimit(self._config["image_decode_limit_mb"])
        self._config_overrides = config_overrides or {}
        self._large_image_confirmed = False
        self._shape_color_preview = None

        self._shape_clipboard = ShapeClipboard(parent=self)

        self._label_dialog = self._make_label_dialog(label_history=None)

        self._prev_opened_dir = None
        self._label_list_menu_origin = None
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
            model_name=self._config["ai"]["default"] or "",
            polygon_detail=self._config["mask_polygonization"]["detail"],
            on_model_changed=self._on_ai_model_changed,
            on_output_format_changed=self._on_ai_output_format_changed,
            on_polygon_detail_changed=self._on_ai_polygon_detail_changed,
            parent=self,
        )
        self._canvas_widgets.canvas.set_ai_model_name(
            model_name=self._ai_annotation.current_model_id
        )
        self._canvas_widgets.canvas.set_ai_output_format(
            output_format=self._ai_annotation.output_format
        )
        self._canvas_widgets.canvas.set_ai_polygon_detail(
            detail=self._config["mask_polygonization"]["detail"]
        )

        self._ai_text = AiTextToAnnotationWidget(
            on_submit=self._submit_ai_prompt, parent=self
        )
        self._ai_text.set_model_name(model_name=self._config["ai"]["text_model"] or "")
        self._ai_text.set_label_suggestions(model=self._docks.unique_label_list.model())
        # The Setting, not the picker: the picker is empty until the model is
        # downloaded, and Prompt Compatibility is checked before that.
        self._canvas_widgets.canvas.get_ai_find_all_model_name = lambda: (
            self._config["ai"]["text_model"] or ""
        )
        self._canvas_widgets.canvas.get_ai_find_all_query = (
            self._ai_text.get_text_prompt
        )
        self._canvas_widgets.canvas.get_ai_find_all_thresholds = lambda: (
            self._ai_text.get_score_threshold(),
            self._ai_text.get_iou_threshold(),
        )
        self._ai_text.model_changed.connect(
            lambda model_name: self._apply_setting_change(
                ("ai", "text_model"), model_name
            )
        )
        self._ai_group = AiToolGroup(
            assist=self._ai_annotation,
            detect=self._ai_text,
            parent=self,
        )

        self._setup_toolbars()

        self._status_bar = self._setup_status_bar()
        self._save_revision = 0
        self._file_contents = _FileContents(path=None, shapes=[], flags={})
        self._save_target = None
        self._save_writer = SaveWriter(parent=self)
        self._save_writer.finished.connect(self._on_save_finished)
        self._image_prefetcher = ImagePrefetcher()
        self._model_manager = ModelManager(parent=self)
        self._osam_worker = _automation.OsamWorker(parent=self)
        self._osam_worker.finished.connect(self._on_ai_text_finished)
        self._osam_worker.failed.connect(self._on_ai_text_failed)
        self._osam_worker.not_pulled.connect(self._on_ai_model_not_pulled)
        self._osam_worker.unloaded.connect(
            lambda name: self._model_manager.remove(model_name=name)
        )
        self._osam_worker.activity_changed.connect(self._on_ai_activity_changed)
        self._osam_worker.set_device(device=self._config["ai"]["device"])
        self._model_manager.set_device(device=self._config["ai"]["device"])
        self._canvas_widgets.canvas.set_osam_worker(worker=self._osam_worker)
        self._ai_text_job = None
        # Kept while idle, so a job retried on CPU keeps its clock and what
        # was announced for it.
        self._ai_status = _AiStatus(job=None, started_at=0.0, announced=frozenset())
        self._ai_status_timer = QtCore.QTimer(self)
        self._ai_status_timer.setInterval(1000)
        self._ai_status_timer.timeout.connect(self._on_ai_activity_changed)
        self._model_manager.changed.connect(self._refresh_model_availability)
        self._canvas_widgets.canvas.ensure_ai_model_ready = self._ensure_ai_model_ready
        self._ai_annotation.manage_models_requested.connect(self._open_models)
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

        # Palette changes include the fallback used when the platform ignores
        # setColorScheme; queue the refresh until Qt has applied the palette.
        app = QtGui.QGuiApplication.instance()
        assert isinstance(app, QtGui.QGuiApplication)
        app.paletteChanged.connect(
            self._retheme, QtCore.Qt.ConnectionType.QueuedConnection
        )

    def _retheme(self) -> None:
        # Two things do not follow Qt's palette swap: cached QIcon pixmaps (keyed
        # by the old tint color) and stylesheet'd widgets (QStyleSheetStyle pins
        # their palette at polish time, leaving a palette(...) toolbar on the old
        # scheme).
        QtGui.QPixmapCache.clear()
        for widget in QtWidgets.QApplication.allWidgets():
            sheet = widget.styleSheet()
            # Only stylesheets with palette(...) references go stale on a scheme
            # change; re-applying just those avoids re-polishing composite widgets
            # (combo boxes, spin boxes) whose re-polish can invalidate siblings.
            if sheet and "palette(" in sheet:
                widget.setStyleSheet(sheet)  # re-resolve palette refs; also repaints
            else:
                widget.update()

    def _setup_actions(self) -> _Actions:
        image_actions = QtGui.QActionGroup(self)
        image_actions.setExclusive(False)
        image_actions.setEnabled(False)
        image_action = functools.partial(_utils.new_action, parent=image_actions)
        # The active mode shows as checked, not disabled, so it reads as the
        # selected tool. An action joins only one QActionGroup and these are in
        # the image group, so _switch_canvas_mode keeps one checked by hand.
        mode_action = functools.partial(image_action, checkable=True)
        action = functools.partial(_utils.new_action, parent=self)
        separator = functools.partial(_utils.new_separator, parent=self)
        shortcuts = self._config["shortcuts"]
        ctrl = _utils.modifier_text(modifiers=Qt.KeyboardModifier.ControlModifier)
        ctrl_shift = _utils.modifier_text(
            modifiers=Qt.KeyboardModifier.ControlModifier
            | Qt.KeyboardModifier.ShiftModifier
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
            slot=lambda: self._insert_shapes(shapes=self._shape_clipboard.paste()),
            shortcut=shortcuts["paste_shape"],
            icon="phosphor/clipboard-text.svg",
            tip=self.tr("Insert the clipboard shapes into this image"),
            enabled=False,
        )
        duplicate = action(
            text=self.tr("Duplicate Shapes"),
            toolbar_text=self.tr("Duplicate", "toolbar"),
            slot=lambda: self._insert_shapes(
                shapes=[s.copy() for s in self._canvas_widgets.canvas.selected_shapes]
            ),
            shortcut=shortcuts["duplicate_shape"],
            icon="phosphor/copy.svg",
            tip=self.tr("Create a duplicate of the selected shapes"),
            enabled=False,
        )
        merge = action(
            text=self.tr("Merge Shapes"),
            slot=self._merge_selected_shapes,
            icon="phosphor/unite.svg",
            tip=self.tr("Merge the selected mask shapes into one"),
            enabled=False,
        )
        # Every kind is listed, checked when the selection already has it, so
        # the menu reads the same for any selection.
        convert: dict[ConvertTarget, QtGui.QAction] = {
            "polygon": action(
                text=self.tr("Polygon"),
                slot=lambda: self._convert_selected_shapes(target="polygon"),
                icon="polygon.svg",
                tip=self.tr("Convert the selected shapes to polygons"),
                checkable=True,
                enabled=False,
            ),
            "rectangle": action(
                text=self.tr("Rectangle"),
                slot=lambda: self._convert_selected_shapes(target="rectangle"),
                icon="rectangle.svg",
                tip=self.tr("Replace the selected shapes with their bounding boxes"),
                checkable=True,
                enabled=False,
            ),
            "oriented_rectangle": action(
                text=self.tr("Oriented Rectangle"),
                slot=lambda: self._convert_selected_shapes(target="oriented_rectangle"),
                icon="oriented_rectangle.svg",
                tip=self.tr("Convert the selected shapes to oriented rectangles"),
                checkable=True,
                enabled=False,
            ),
            "circle": action(
                text=self.tr("Circle"),
                slot=lambda: self._convert_selected_shapes(target="circle"),
                icon="circle.svg",
                tip=self.tr("Convert the selected shapes to circles"),
                checkable=True,
                enabled=False,
            ),
            "line": action(
                text=self.tr("Line"),
                slot=lambda: self._convert_selected_shapes(target="line"),
                icon="line.svg",
                tip=self.tr("Convert the selected shapes to lines"),
                checkable=True,
                enabled=False,
            ),
            "point": action(
                text=self.tr("Point"),
                slot=lambda: self._convert_selected_shapes(target="point"),
                icon="point.svg",
                tip=self.tr("Convert the selected shapes to points"),
                checkable=True,
                enabled=False,
            ),
            "linestrip": action(
                text=self.tr("LineStrip"),
                slot=lambda: self._convert_selected_shapes(target="linestrip"),
                icon="linestrip.svg",
                tip=self.tr("Convert the selected shapes to linestrips"),
                checkable=True,
                enabled=False,
            ),
            "mask": action(
                text=self.tr("Mask"),
                slot=lambda: self._convert_selected_shapes(target="mask"),
                icon="mask.svg",
                tip=self.tr("Convert the selected shapes to masks"),
                checkable=True,
                enabled=False,
            ),
        }
        # Parented to the window, so clearing a menu that lists it does not
        # delete it.
        convert_menu = QtWidgets.QMenu(self.tr("Convert To"), self)
        convert_menu.setIcon(_utils.new_icon(name="phosphor/swap.svg"))
        convert_menu.addActions(list(convert.values()))
        # Lets a disabled item say why it is disabled, as the menus that list
        # this one do.
        convert_menu.setToolTipsVisible(True)
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
            slot=self._canvas_widgets.canvas.remove_selected_point,
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
        create_mode = mode_action(
            text=self.tr("Polygon"),
            slot=lambda: self._switch_canvas_mode(edit=False, create_mode="polygon"),
            shortcut=shortcuts["create_polygon"],
            icon="polygon.svg",
            tip=self.tr("Start drawing polygons"),
        )
        edit_mode = mode_action(
            text=self.tr("Edit Shapes"),
            toolbar_text=self.tr("Select", "toolbar"),
            slot=lambda: self._switch_canvas_mode(edit=True, create_mode=None),
            shortcut=shortcuts["edit_shape"],
            icon="phosphor/cursor.svg",
            tip=self.tr("Move and edit the selected shapes"),
            checked=True,
        )
        create_rectangle_mode = mode_action(
            text=self.tr("Rectangle"),
            slot=lambda: self._switch_canvas_mode(edit=False, create_mode="rectangle"),
            shortcut=shortcuts["create_rectangle"],
            icon="rectangle.svg",
            tip=self.tr("Start drawing rectangles"),
        )
        create_oriented_rectangle_mode = mode_action(
            text=self.tr("Oriented Rectangle"),
            slot=lambda: self._switch_canvas_mode(
                edit=False, create_mode="oriented_rectangle"
            ),
            shortcut=shortcuts["create_oriented_rectangle"],
            icon="oriented_rectangle.svg",
            tip=self.tr("Start drawing oriented rectangles"),
        )
        create_circle_mode = mode_action(
            text=self.tr("Circle"),
            slot=lambda: self._switch_canvas_mode(edit=False, create_mode="circle"),
            shortcut=shortcuts["create_circle"],
            icon="circle.svg",
            tip=self.tr("Start drawing circles"),
        )
        create_circle_3p_mode = mode_action(
            text=self.tr("3-Point Circle"),
            slot=lambda: self._switch_canvas_mode(edit=False, create_mode="circle_3p"),
            shortcut=shortcuts["create_circle_3p"],
            icon="circle_3p.svg",
            tip=self.tr("Start drawing circles with 3 points"),
        )
        create_line_mode = mode_action(
            text=self.tr("Line"),
            slot=lambda: self._switch_canvas_mode(edit=False, create_mode="line"),
            shortcut=shortcuts["create_line"],
            icon="line.svg",
            tip=self.tr("Start drawing lines"),
        )
        create_point_mode = mode_action(
            text=self.tr("Point"),
            slot=lambda: self._switch_canvas_mode(edit=False, create_mode="point"),
            shortcut=shortcuts["create_point"],
            icon="point.svg",
            tip=self.tr("Start drawing points"),
        )
        create_line_strip_mode = mode_action(
            text=self.tr("LineStrip"),
            slot=lambda: self._switch_canvas_mode(edit=False, create_mode="linestrip"),
            shortcut=shortcuts["create_linestrip"],
            icon="linestrip.svg",
            tip=self.tr(
                "Click to place LineStrip points; hold %s and click to place the"
                " last one."
            )
            % ctrl,
        )
        create_ai_segment_mode = mode_action(
            text=self.tr("AI-Segment"),
            slot=lambda: self._switch_canvas_mode(edit=False, create_mode="ai_segment"),
            shortcut=shortcuts["create_ai_segment"],
            icon="ai-points.svg",
            tip=self.tr(
                "Click points or drag a box to segment one object; hold %s and"
                " click to finish."
            )
            % ctrl,
        )
        create_ai_find_all_mode = mode_action(
            text=self.tr("AI-Find All"),
            slot=lambda: self._switch_canvas_mode(
                edit=False, create_mode="ai_find_all"
            ),
            shortcut=shortcuts["create_ai_find_all"],
            icon="ai-find-all.svg",
            tip=self.tr(
                "Find every object that matches the text prompt or an example box"
            ),
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
            icon="phosphor/circle-half-tilt.svg",
            tip=self.tr("Adjust brightness and contrast"),
        )
        zoom_in = image_action(
            text=self.tr("Zoom &In"),
            slot=lambda _: self._add_zoom(steps=1, pos=None),
            shortcut=shortcuts["zoom_in"],
            icon="phosphor/magnifying-glass-plus.svg",
            tip=self.tr("Make the image appear larger"),
        )
        zoom_out = image_action(
            text=self.tr("&Zoom Out"),
            slot=lambda _: self._add_zoom(steps=-1, pos=None),
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
            icon="phosphor/layout.svg",
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
        zoom_box_layout.addLayout(zoom_row)
        zoom_box_layout.addWidget(self._zoom_mode_label)
        # No gap above the caption, so it shares a line with the first line
        # of the toolbar's labels.
        zoom_box_layout.setSpacing(0)
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
            ("circle_3p", create_circle_3p_mode),
            ("point", create_point_mode),
            ("line", create_line_mode),
            ("linestrip", create_line_strip_mode),
            ("ai_segment", create_ai_segment_mode),
            ("ai_find_all", create_ai_find_all_mode),
        ]
        # The Edit menu follows the platform Edit-menu convention: history first,
        # then the clipboard group, then the actions that alter a shape.
        history = (undo, undo_last_point)
        clipboard = (copy, paste, duplicate)
        shape_context_menu = (
            edit,
            duplicate,
            copy,
            delete,
            merge,
            convert_menu.menuAction(),
            lock,
            separator(),
            add_point_to_edge,
            remove_point,
        )
        canvas_context_menu = (
            *[draw_action for _, draw_action in draw],
            edit_mode,
            separator(),
            *history,
            separator(),
            paste,
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
            convert_menu.menuAction(),
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
            convert=convert,
            lock=lock,
            undo_last_point=undo_last_point,
            undo=undo,
            add_point_to_edge=add_point_to_edge,
            create_mode=create_mode,
            edit_mode=edit_mode,
            create_rectangle_mode=create_rectangle_mode,
            create_point_mode=create_point_mode,
            create_ai_segment_mode=create_ai_segment_mode,
            create_ai_find_all_mode=create_ai_find_all_mode,
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
            shape_context_menu=shape_context_menu,
            canvas_context_menu=canvas_context_menu,
            edit_menu=edit_menu,
        )

    def _setup_menus(self) -> _Menus:
        action = functools.partial(_utils.new_action, parent=self)
        separator = functools.partial(_utils.new_separator, parent=self)
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
        unique_label_list = self._docks.unique_label_list
        unique_label_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        unique_label_list.customContextMenuRequested.connect(
            self.show_unique_label_list_menu
        )
        unique_label_list.label_remove_requested.connect(self._remove_unique_label)
        # The Labels dock lists every shape with its label, so its changes are
        # the ones that can make a label used or unused. Refresh once the
        # change is done: a row is inserted before its item is set, and a
        # load inserts one row per shape.
        refresh_unused_labels = QtCore.QTimer(self)
        refresh_unused_labels.setSingleShot(True)
        refresh_unused_labels.timeout.connect(self._refresh_unused_labels)
        label_model = self._docks.label_list.model()
        for signal in (
            label_model.rowsInserted,
            label_model.rowsRemoved,
            label_model.dataChanged,
            label_model.modelReset,
        ):
            signal.connect(refresh_unused_labels.start)

        file_menu.addActions(
            (
                self._actions.open,
                self._actions.open_dir,
                separator(),
                self._actions.open_prev_img,
                self._actions.open_next_img,
                separator(),
                self._actions.save,
                self._actions.save_as,
                self._actions.save_auto,
                self._actions.change_output_dir,
                self._actions.save_with_image_data,
                separator(),
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

        # Lets a disabled item say why it is disabled.
        canvas = self._canvas_widgets.canvas
        for menu in (canvas.shape_context_menu, canvas.canvas_context_menu, edit_menu):
            menu.setToolTipsVisible(True)

        return _Menus(
            file=file_menu,
            edit=edit_menu,
            view=view_menu,
            help=help_menu,
            label_list=label_menu,
        )

    def _setup_toolbars(self) -> None:
        separator = functools.partial(_utils.new_separator, parent=self)
        ai_group_action = QtWidgets.QWidgetAction(self)
        ai_group_action.setDefaultWidget(self._ai_group)

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
                    self._actions.undo,
                    self._actions.duplicate,
                    self._actions.delete,
                    self._actions.brightness_contrast,
                    separator(),
                    self._actions.zoom_widget_action,
                    separator(),
                    ai_group_action,
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
                    self._actions.edit_mode,
                    separator(),
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

    def _setup_app_state(
        self,
        *,
        file_or_dir: str | None,
        output_dir: str | None,
    ) -> None:
        self._opened_folder = _OpenedFolder(
            root=None,
            output_dir=Path(output_dir) if output_dir else None,
            image_paths=(),
        )

        self._image = QtGui.QImage()
        self._annotation = None
        self._label_file_path = None
        self._failed_save_path = None
        self._image_path = None
        self._file_list_image_path = None
        # Annotated images the search box hides, found when the list is
        # rebuilt and kept current by saves and deletions; the visible ones
        # are counted from their check marks.
        self._hidden_annotated_paths = set()
        self._file_search_pattern = re.compile("")
        self._prev_image_path = None
        self._viewport_states = {}
        self._brightness_contrast_values = {}
        self._conversion_detail = 60

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
            available=screen.availableGeometry(),
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
        if (
            self._opened_folder.output_dir is not None
            and not _label_file.is_label_file_path(filename=file_or_dir)
        ):
            # --output replaces the folder's remembered Annotation Folder, so
            # opening the folder restores it like any other choice. It must
            # exist, or the restore would skip it as missing.
            self._opened_folder.output_dir.mkdir(parents=True, exist_ok=True)
            self._remember_output_dir(
                opened_dir=file_or_dir
                if Path(file_or_dir).is_dir()
                else str(Path(file_or_dir).parent)
            )
        self._load_from_file_or_dir(file_or_dir=file_or_dir)

    def _setup_status_bar(self) -> _StatusBarWidgets:
        message = QtWidgets.QLabel()
        stats = StatusStats()
        self.statusBar().addWidget(message, 1)
        save = QtWidgets.QLabel()
        save.setTextFormat(Qt.TextFormat.PlainText)
        retry = QtWidgets.QToolButton()
        retry.setText(self.tr("Retry"))
        retry.clicked.connect(self._retry_save)
        retry.hide()
        ai = QtWidgets.QLabel()
        self.statusBar().addPermanentWidget(ai)
        self.statusBar().addPermanentWidget(save)
        self.statusBar().addPermanentWidget(retry)
        # Last, so the AI and save states that come and go never move it.
        self.statusBar().addPermanentWidget(stats)
        self.statusBar().show()
        return _StatusBarWidgets(
            message=message, stats=stats, save=save, retry=retry, ai=ai
        )

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
            palette=Palette.from_shape_config(shape=self._config["shape"])
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
        scroll_area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        scroll_area.setWidget(canvas)
        scroll_area.setWidgetResizable(True)
        scroll_bars = {
            Qt.Orientation.Vertical: scroll_area.verticalScrollBar(),
            Qt.Orientation.Horizontal: scroll_area.horizontalScrollBar(),
        }
        canvas.scroll_request.connect(self._on_scroll_request)
        canvas.pan_request.connect(self._on_pan_request)

        canvas.new_shape.connect(self._on_new_shape)
        canvas.ai_find_all_draft_committed.connect(self._on_ai_find_all_draft_committed)
        canvas.inference_produced_no_shapes.connect(
            self._on_inference_produced_no_shapes
        )
        canvas.example_box_unsupported.connect(self._on_example_box_unsupported)
        # The preview path emits this from inside paintEvent (an active
        # QPainter); a queued connection defers the status-bar update until
        # after the paint cycle so it never mutates UI mid-paint.
        canvas.inference_failed.connect(
            self._on_inference_failed,
            Qt.ConnectionType.QueuedConnection,
        )
        canvas.degenerate_shape_rejected.connect(
            lambda: self.show_status_message(
                message=self.tr("Shape had no area; nothing created."), delay=5000
            )
        )
        canvas.shape_moved.connect(self.mark_dirty)
        canvas.selection_changed.connect(self._on_shape_selection_changed)
        canvas.shape_moved.connect(self._cancel_deferred_fit_selection)
        canvas.shape_double_clicked.connect(self._edit_label)
        canvas.busy_changed.connect(self._sync_edit_actions)

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

        unique_label_list = UniqueLabelQListWidget(
            on_edit_settings_labels=self._edit_settings_labels,
            on_clear_unused=self._clear_unused_unique_labels,
        )
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
                    from_settings=True,
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
        file_list_delegate = ImageListDelegate(parent=file_list)
        file_list.setItemDelegate(file_list_delegate)
        file_list.currentItemChanged.connect(self._load_selected_image)
        # File > Close keeps the row current, so picking it again changes nothing.
        file_list.itemClicked.connect(self._reopen_closed_image)
        file_list.itemActivated.connect(self._reopen_closed_image)
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
        # What the user last chose for the Flags dock, kept while an empty
        # list hides it.
        self._flag_dock_wanted = not flag.isHidden()
        flag.toggleViewAction().toggled.connect(self._on_flag_dock_toggled)

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
            file_list_delegate=file_list_delegate,
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
        canvas = self._canvas_widgets.canvas
        for menu, menu_actions in (
            (canvas.shape_context_menu, self._actions.shape_context_menu),
            (canvas.canvas_context_menu, self._actions.canvas_context_menu),
        ):
            menu.clear()
            menu.addActions(menu_actions)
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

    def _save_destination(self) -> str:
        # Where a save that asks nothing writes the open document. It never
        # replaces an existing Annotation File other than the one loaded.
        assert self._image_path is not None
        # Chosen once per document: after its own first write the disk no
        # longer tells a first copy from a file that was already there.
        if self._save_target is None:
            self._save_target = _SaveTarget(
                path=self._choose_save_destination(), overwrite_confirmed=False
            )
        return self._save_target.path

    def _known_save_destination(self) -> str | None:
        # Like _save_destination, without choosing one.
        if self._save_target is not None:
            return self._save_target.path
        return self._label_file_path

    def _choose_save_destination(self) -> str:
        assert self._image_path is not None
        resolved = _label_path.resolve_label_path(
            image_path=self._file_list_image_path or self._image_path,
            output_dir=self._opened_folder.output_dir,
            root_prefix=self._opened_folder.root,
        )
        if self._label_file_path is None:
            return resolved
        # The Annotation Folder takes the first copy of a file opened from
        # elsewhere.
        if self._opened_folder.output_dir is not None and not Path(resolved).exists():
            return resolved
        return self._label_file_path

    def mark_dirty(self) -> None:
        # The Flags dock stays clickable with no Image open; nothing can be
        # dirty then.
        if self._image_path is None:
            return
        self._save_revision += 1
        self._sync_edit_actions()
        self._is_changed = True
        self._actions.save.setEnabled(True)
        self.setWindowTitle(self._get_window_title(dirty=True))
        if self._actions.save_auto.isChecked():
            assert self._image_path is not None
            self._queue_auto_save(label_path=self._save_destination())
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
        # can clear the dirty marker or replace its failure status, but every
        # write changes what the file holds.
        if error is None:
            self._record_file_contents(request=request)
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
        self._sync_edit_actions()
        self._is_changed = False
        self._actions.save.setEnabled(False)
        self.setWindowTitle(self._get_window_title(dirty=False))

    def show_status_message(self, *, message: str, delay: int = 500) -> None:
        self.statusBar().showMessage(message, delay)

    def _submit_ai_prompt(self) -> None:
        if not self._actions.image.isEnabled():
            return  # No image to detect in.
        prompt = self._ai_text.get_text_prompt()
        canvas = self._canvas_widgets.canvas
        if canvas.has_ai_find_all_draft:
            # Refine the example-box draft instead of adding Shapes on top; an
            # empty query keeps detecting like the examples.
            canvas.rerun_ai_find_all_draft()
            # Enter and Esc act on the draft from the canvas.
            canvas.setFocus()
            return
        if not prompt:
            self.show_status_message(message=self.tr("Type what to find"), delay=5000)
            self._ai_text.focus_text_prompt()
            return
        # Switching cancels a draft, so a Shape mid-drawing keeps its tool.
        if not canvas.is_drawing:
            self._actions.create_ai_find_all_mode.trigger()
        shape_type = self._ai_annotation.output_format

        # Checked against the Setting, so a model that is not downloaded yet is
        # rejected before the Models window offers its download.
        requested_model: str = self._config["ai"]["text_model"] or ""
        if requested_model in _text_models_unable_to_create(shape_type=shape_type):
            QtWidgets.QMessageBox.warning(
                self,
                self.tr("Mask Output Unavailable"),
                self.tr(
                    "%s only detects bounding boxes and cannot create "
                    "'%s' Shapes.\n\n"
                    "Switch the AI-Find All model to 'SAM 3', "
                    "or set the output format to 'Rectangle'."
                )
                % (self._model_manager.models[requested_model], shape_type),
            )
            return

        texts = [prompt]

        model_name: str = self._ai_text.get_model_name()
        if not self._ensure_ai_model_ready(model_name):
            return
        image = canvas.ai_image()
        job = _AiTextJob(
            pixmap_key=canvas.pixmap.cacheKey(),
            texts=texts,
            shape_type=shape_type,
            iou_threshold=self._ai_text.get_iou_threshold(),
            score_threshold=self._ai_text.get_score_threshold(),
            image_size=(
                None
                if self._config["canvas"]["allow_out_of_bounds_points"]
                else (self._image.width(), self._image.height())
            ),
        )
        self._ai_text_job = job
        self._osam_worker.submit(
            channel="text",
            job=job,
            request=_automation.InferenceRequest(
                model_name=model_name, image=image, texts=texts
            ),
        )

    def _take_ai_text_job(self, *, job: object) -> _AiTextJob | None:
        if job is not self._ai_text_job:
            return None
        self._ai_text_job = None
        assert isinstance(job, _AiTextJob)
        # A result for an image no longer shown is dropped.
        if job.pixmap_key != self._canvas_widgets.canvas.pixmap.cacheKey():
            return None
        return job

    def _on_ai_activity_changed(self) -> None:
        # The canvas rings a slow AI Assist prompt where it was placed; this
        # names the running task for every prompt, AI-Find All included.
        worker = self._osam_worker
        job = worker.job
        canvas = self._canvas_widgets.canvas
        # The worker also runs other AI tools, so Run follows only detection.
        self._ai_text.set_detecting(
            detecting=job is not None
            and (self._ai_text_job is not None or canvas.ai_find_all_job is not None)
        )
        on_cpu = worker.device == "cpu"
        detecting = True
        if job is None:
            text, detecting = "", False
        elif isinstance(job, _AiTextJob):
            text = (
                self.tr("Finding all '{query}' on CPU…")
                if on_cpu
                else self.tr("Finding all '{query}'…")
            ).format(query=job.query)
        elif (box_job := canvas.ai_find_all_job) is job:
            assert box_job is not None
            if box_job.query:
                text = (
                    self.tr("Finding all '{query}' on CPU…")
                    if on_cpu
                    else self.tr("Finding all '{query}'…")
                ).format(query=box_job.query)
            else:
                text = (
                    self.tr("Finding matches on CPU…")
                    if on_cpu
                    else self.tr("Finding matches…")
                )
        else:
            text = self.tr("Segmenting on CPU…") if on_cpu else self.tr("Segmenting…")
            detecting = False
        stage = worker.stage
        if stage == "starting":
            text = self.tr("Starting AI…")
        elif stage == "loading":
            model_name = worker.model_name or ""
            # Model names are product names, so they stay untranslated.
            text = self.tr("Loading {model}…").format(
                model=self._model_manager.models.get(model_name, model_name)
            )
        if job is None:
            self._ai_status_timer.stop()
        else:
            if job is not self._ai_status.job:
                self._ai_status = _AiStatus(
                    job=job, started_at=time.monotonic(), announced=frozenset()
                )
            # A detection is announced once as it starts, from text or a box,
            # and a slow stage once for any prompt; a fast Segment, never.
            kind = stage if stage in ("starting", "loading") else "task"
            if (detecting or kind != "task") and kind not in self._ai_status.announced:
                self._ai_status = self._ai_status._replace(
                    announced=self._ai_status.announced | {kind}
                )
                self._announce(message=text)
            self._ai_status_timer.start()  # restarts, so a tick follows a second
            seconds = int(time.monotonic() - self._ai_status.started_at)
            ELAPSED_SHOWN_AFTER_S: Final = 3
            if seconds >= ELAPSED_SHOWN_AFTER_S:
                text = self.tr("{status} · {seconds} s").format(
                    status=text, seconds=seconds
                )
        self._status_bar.ai.setText(text)

    def _announce(self, *, message: str) -> None:
        if not QtGui.QAccessible.isActive():
            return
        event = QtGui.QAccessibleAnnouncementEvent(self._status_bar.ai, message)
        event.setPoliteness(QtGui.QAccessible.AnnouncementPoliteness.Polite)
        QtGui.QAccessible.updateAccessibility(event)

    def _on_ai_model_not_pulled(self, device: str | None, /) -> None:
        # After a fall back to the CPU, a model such as SAM 3 runs other files,
        # so it shows as not downloaded until the Compute device changes.
        if device == "cpu":
            self._model_manager.set_device(device="cpu")

    def _on_ai_text_failed(self, job: object, message: str, /) -> None:
        if self._take_ai_text_job(job=job) is None:
            return
        logger.error("AI text inference failed: {}", message)
        self._on_inference_failed(message)

    def _on_ai_text_finished(self, job: object, annotations: object, /) -> None:
        # A result lands whenever inference ends. Applied mid-draw, mid-drag
        # or under a dialog, its Shapes would split that action's Undo
        # snapshot or join the Shapes being labeled, so it waits. The worker
        # holds results under a dialog; this retry must check again.
        if job is self._ai_text_job and (
            self._canvas_widgets.canvas.is_interacting
            or QtWidgets.QApplication.activeModalWidget() is not None
        ):
            QtCore.QTimer.singleShot(
                100,
                self,
                functools.partial(self._on_ai_text_finished, job, annotations),
            )
            return
        text_job = self._take_ai_text_job(job=job)
        if text_job is None:
            return
        propose = functools.partial(
            _automation.propose_shapes_from_texts,
            annotations=cast(list, annotations),
            texts=text_job.texts,
            shape_type=text_job.shape_type,
            existing_shapes=self._canvas_widgets.canvas.shapes,
            iou_threshold=text_job.iou_threshold,
            score_threshold=text_job.score_threshold,
            image_size=text_job.image_size,
            polygon_detail=self._config["mask_polygonization"]["detail"],
        )
        try:
            # Ignores existing Shapes: which ones cover the batch depends on
            # the label it takes, and that isn't known yet.
            shapes = propose(existing_shapes=[])
        except Exception as e:
            logger.opt(exception=e).error("AI text inference failed")
            self._on_inference_failed(f"{type(e).__name__}: {e}")
            return
        self._commit_ai_find_all(
            candidates=shapes,
            propose_for_label=lambda label: propose(suppressed_by=label),
            query=text_job.query,
        )
        # Loading clears the Label List's selection; the canvas keeps its own,
        # so the user's selection survives a result landing.
        canvas = self._canvas_widgets.canvas
        canvas.select_shapes(shapes=list(canvas.selected_shapes))

    def _on_ai_find_all_draft_committed(
        self,
        shapes: list[Shape],
        propose_for_label: Callable[[str], list[Shape]],
        query: str,
        /,
    ) -> None:
        added = self._commit_ai_find_all(
            candidates=shapes, propose_for_label=propose_for_label, query=query
        )
        # Select what the batch added, so it can be relabeled or deleted.
        self._canvas_widgets.canvas.select_shapes(shapes=added)

    def _commit_ai_find_all(
        self,
        *,
        candidates: list[Shape],
        propose_for_label: Callable[[str], list[Shape]],
        query: str,
    ) -> list[Shape]:
        # Every AI-Find All batch lands here, from a query or an example box, so
        # labeling, skipping covered objects and the result message stay one.
        if not candidates:
            self._report_ai_find_all_result(shapes=candidates, name=query)
            return []
        # One entry labels the whole batch, shown on the canvas meanwhile.
        canvas = self._canvas_widgets.canvas
        canvas.set_ai_find_all_pending(shapes=candidates)
        try:
            entry = self._ask_new_shape_entry(query=query)
        finally:
            canvas.set_ai_find_all_pending(shapes=[])
        if entry is None:
            return []  # Cancelled: the batch is never added.
        # "black dog" saved as "dog": skip what "dog" Shapes cover.
        shapes = propose_for_label(entry.label)
        self._report_ai_find_all_result(shapes=shapes, name=entry.label)
        if not shapes:
            return []
        for shape in shapes:
            shape.label = entry.label
            shape.flags = dict(entry.flags)
            shape.description = entry.description
            if entry.group_id is not None:
                shape.group_id = entry.group_id
        _label_flags.apply_default_flags(
            shapes=shapes, label_flags=self._config["label_flags"]
        )
        self._load_shapes(shapes=shapes, replace=False)
        self.mark_dirty()
        return shapes

    def _report_ai_find_all_result(self, *, shapes: list[Shape], name: str) -> None:
        # Polygons from one mask's separate lands share a Group: one object.
        count = len({id(s) if s.group_id is None else s.group_id for s in shapes})
        message = (
            self.tr("Found {count} new '{query}'")
            if count
            else self.tr("No new '{query}' found")
        ).format(count=count, query=name)
        self.show_status_message(message=message, delay=5000)
        self._announce(message=message)

    def reset_state(self) -> None:
        self._save_target = None
        self._docks.label_list.clear()
        self._load_flags(flags={}, widget=self._docks.flag_list)
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
        canvas = self._canvas_widgets.canvas
        before = canvas.shapes
        canvas.restore_last_shape()
        # Back where the file the document saves to is, nothing is unsaved. A
        # write still running may hold the step undone, so Undo then saves
        # over it as any edit.
        back_to_clean = (
            not self._save_writer.is_busy
            and self._file_contents.path == self._known_save_destination()
            and self._read_flag_dock_states() == self._file_contents.flags
            and _saved_shapes_equal(a=canvas.shapes, b=self._file_contents.shapes)
        )
        # Undoing a step that saves nothing, such as hiding a shape, leaves
        # the file as it was.
        self._commit_shapes(
            shapes=canvas.shapes,
            changed=not back_to_clean
            and not _saved_shapes_equal(a=before, b=canvas.shapes),
        )
        if back_to_clean:
            # Neither the pending changes nor a failed save are left.
            self._failed_save_path = None
            self._status_bar.save.clear()
            self._status_bar.retry.hide()
            self.mark_clean()

    def tutorial(self) -> None:
        url = "https://github.com/wkentaro/labelme/tree/main/examples/tutorial"  # NOQA
        webbrowser.open(url)

    def _sync_edit_actions(self) -> None:
        # Derived from the canvas alone, so a caller that runs at the wrong
        # moment cannot leave an action stuck.
        canvas = self._canvas_widgets.canvas
        busy = canvas.is_busy
        selected = canvas.selected_shapes
        self._actions.edit_mode.setEnabled(not busy)
        self._actions.undo_last_point.setEnabled(canvas.is_drawing)
        self._actions.undo.setEnabled(not busy and canvas.can_restore_shape)
        # Locked shapes stay selectable, but only unlocked ones can be deleted.
        self._actions.delete.setEnabled(
            not busy and any(not shape.locked for shape in selected)
        )
        blocker = _shape.merge_blocker(shapes=selected)
        self._actions.merge.setEnabled(not busy and blocker is None)
        # The tooltip is all a disabled menu item can show: Qt sends no status
        # tip for one on macOS or Fusion.
        self._actions.merge.setToolTip(self._merge_tip(blocker=blocker))
        for target, convert_action in self._actions.convert.items():
            blocker = _shape.convert_blocker(
                shapes=selected,
                target=target,
                image_size=self._convert_image_size(target=target),
            )
            convert_action.setEnabled(not busy and blocker is None)
            convert_action.setChecked(blocker == "already_target")
            # An ellipsis says the item asks for a Polygon Detail first.
            name = convert_action.text().removesuffix("…")
            needs_detail = blocker is None and _shape.conversion_needs_detail(
                shapes=selected, target=target
            )
            convert_action.setText(name + "…" if needs_detail else name)
            convert_action.setToolTip(self._convert_tip(target=target, blocker=blocker))

    def _merge_tip(self, *, blocker: MergeBlocker | None) -> str:
        match blocker:
            case None:
                # The status tip keeps the description the action was built with.
                return self._actions.merge.statusTip()
            case "too_few":
                return self.tr("Select at least two mask shapes to merge")
            case "not_masks":
                return self.tr("Only mask shapes can be merged")
            case "locked":
                return self.tr("Unlock the selected shapes to merge them")
            case "mixed_labels":
                return self.tr("Only shapes with the same label can be merged")

    def _convert_tip(
        self, *, target: ConvertTarget, blocker: ConvertBlocker | None
    ) -> str:
        match blocker:
            case None:
                return self._actions.convert[target].statusTip()
            case "no_selection":
                return self.tr("Select shapes to convert")
            case "already_target":
                return self.tr("The selected shapes are already this kind")
            case "wrong_type":
                return {
                    "polygon": self.tr(
                        "Lines and points can’t be converted to polygons"
                    ),
                    "rectangle": self.tr(
                        "Lines and points can’t be converted to rectangles"
                    ),
                    "oriented_rectangle": self.tr(
                        "Converting to oriented rectangles isn’t supported"
                    ),
                    "circle": self.tr("Converting to circles isn’t supported"),
                    "line": self.tr("Only linestrips can be converted to lines"),
                    "point": self.tr("Converting to points isn’t supported"),
                    "linestrip": self.tr(
                        "Only polygons and lines can be converted to linestrips"
                    ),
                    "mask": self.tr("Only polygons can be converted to masks"),
                }[target]
            case "too_few_points":
                return self.tr(
                    "A linestrip needs at least 3 points to become a polygon"
                )
            case "too_many_points":
                return self.tr("A linestrip needs exactly 2 points to become a line")
            case "no_area" if target == "rectangle":
                return self.tr("A shape with no area has no bounding box")
            case "no_area":
                return self.tr("A shape with no area in the image can’t be converted")
            case "locked":
                return self.tr("Unlock the selected shapes to convert them")

    def _switch_canvas_mode(self, *, edit: bool, create_mode: str | None) -> None:
        self._canvas_widgets.canvas.set_editing(value=edit, create_mode=create_mode)
        # Triggering a checkable action toggles it, so re-clicking the active
        # tool unchecks it until this re-checks it.
        for draw_mode, draw_action in self._actions.draw:
            draw_action.setChecked(not edit and create_mode == draw_mode)
        self._actions.edit_mode.setChecked(edit)
        self._sync_edit_actions()
        self._on_ai_activity_changed()
        self._refresh_text_model_choices()

    def _on_ai_output_format_changed(
        self, output_format: _automation.AiOutputFormat, /
    ) -> None:
        self._canvas_widgets.canvas.set_ai_output_format(output_format=output_format)
        self._refresh_text_model_choices()

    def _refresh_text_model_choices(self) -> None:
        # Grey out text models that cannot produce Shapes in the Output, which
        # AI-Find All always uses; _submit_ai_prompt still rejects a model
        # already chosen.
        shape_type = self._ai_annotation.output_format
        reason = self.tr("Detects boxes only. Switch to Rectangle to use this model.")
        unavailable = dict.fromkeys(
            _text_models_unable_to_create(shape_type=shape_type), reason
        )
        self._ai_text.set_unavailable_models(unavailable=unavailable)
        if self._settings_dialog is not None:
            self._settings_dialog.set_unavailable_choices(
                key_path=("ai", "text_model"), unavailable=unavailable
            )

    def show_label_list_menu(self, point: QtCore.QPoint, /) -> None:
        self._label_list_menu_origin = self._docks.label_list.mapToGlobal(point)
        try:
            # PySide6 type QMenu.exec() argument too narrowly
            self._menus.label_list.exec(self._label_list_menu_origin)  # ty: ignore[invalid-argument-type]
        finally:
            self._label_list_menu_origin = None

    def show_unique_label_list_menu(self, point: QtCore.QPoint, /) -> None:
        menu = self._build_unique_label_list_menu(point=point)
        global_pos = self._docks.unique_label_list.mapToGlobal(point)
        try:
            # PySide6 types QMenu.exec() argument too narrowly
            menu.exec(global_pos)  # ty: ignore[invalid-argument-type]
        finally:
            menu.deleteLater()

    def _build_unique_label_list_menu(self, *, point: QtCore.QPoint) -> QtWidgets.QMenu:
        menu = QtWidgets.QMenu(self)
        # Lets the disabled Remove item say why it is disabled.
        menu.setToolTipsVisible(True)
        unique_label_list = self._docks.unique_label_list
        unused_labels = self._unused_unique_labels()
        item = unique_label_list.itemAt(point)
        # Settings owns the label set, so only labels found in files are
        # removable here.
        if (
            item is not None
            and (label := item.data(Qt.ItemDataRole.UserRole))
            in unique_label_list.found_labels()
        ):
            remove_action = menu.addAction(
                self.tr("Remove from Label List"),
                functools.partial(self._remove_unique_label, label),
            )
            if label not in unused_labels:
                remove_action.setEnabled(False)
                remove_action.setToolTip(self._label_in_use_message(label=label))
            menu.addSeparator()
        menu.addAction(
            self.tr("Clear Unused Labels"), self._clear_unused_unique_labels
        ).setEnabled(bool(unused_labels))
        return menu

    def _unused_unique_labels(self) -> list[str]:
        in_use = {shape.label for shape in self._canvas_widgets.canvas.shapes}
        return [
            label
            for label in self._docks.unique_label_list.found_labels()
            if label not in in_use
        ]

    def _refresh_unused_labels(self) -> None:
        self._docks.unique_label_list.set_unused_labels(
            labels=self._unused_unique_labels()
        )

    def _label_in_use_message(self, *, label: str) -> str:
        return self.tr("The label '{label}' is in use by shapes on the canvas.").format(
            label=label
        )

    def _remove_unique_label(self, label: str, /) -> None:
        if label not in self._unused_unique_labels():
            self.show_error_message(
                title=self.tr("Cannot Remove Label"),
                message=self._label_in_use_message(label=label),
            )
            return
        self._forget_unique_labels(labels=[label])

    def _clear_unused_unique_labels(self) -> None:
        self._forget_unique_labels(labels=self._unused_unique_labels())

    def _forget_unique_labels(self, *, labels: list[str]) -> None:
        self._docks.unique_label_list.remove_label_items(labels=labels)
        for label in labels:
            self._label_dialog.remove_label(label=label)
        # Once for the batch: it repaints every remaining label.
        self._refresh_shape_colors()
        self._refresh_unused_labels()

    def validate_label(self, *, label: str) -> bool:
        policy = self._config["validate_label"]
        if policy is None:
            return True
        return _is_valid_label(
            label=label,
            existing_labels=self._docks.unique_label_list.labels(),
            policy=policy,
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

        edited_fields = [
            field for field in typing.get_args(LabelDialogField) if field not in locked
        ]
        # A Shape loaded without flags or a description holds None, which the
        # dialog shows, and returns, as empty.
        empty: dict[str, object] = {"flags": {}, "description": ""}
        if all(
            (
                empty.get(field)
                if getattr(shape, field) is None
                else getattr(shape, field)
            )
            == getattr(entry, field)
            for shape in shapes
            for field in edited_fields
        ):
            return

        for item in items:
            shape = item.shape()
            assert shape is not None
            for field in edited_fields:
                setattr(shape, field, getattr(entry, field))

            assert shape.label is not None
            fill_rgb = self._get_rgb_by_label(
                label=shape.label,
                unique_label_list=self._docks.unique_label_list,
            )
            item.set_label(
                text=_widgets.format_shape_label(shape=shape),
                color=fill_rgb,
            )
            self._register_label(label=shape.label)
        self._canvas_widgets.canvas.backup_shapes()
        # A new label changes the Shape's color and its drawn text.
        self._canvas_widgets.canvas.update()
        self.mark_dirty()

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
            image_or_label_path=_file_list_item_path(item=current_item)
        ):
            self._restore_file_list_state(item=previous_item)
            return False
        return True

    def _reopen_closed_image(self, item: QtWidgets.QListWidgetItem, /) -> None:
        if self._image_path is None and item is self._docks.file_list.currentItem():
            self._load_selected_image(item, item)

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
        self._sync_edit_actions()
        self._actions.duplicate.setEnabled(n_selected)
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
        self._commit_shapes(shapes=canvas.shapes)
        canvas.select_shapes(shapes=shapes)

    def _register_label(self, *, label: str) -> None:
        if self._docks.unique_label_list.find_label_item(label=label) is None:
            self._docks.unique_label_list.add_label_item(
                label=label,
                color=self._get_rgb_by_label(
                    label=label, unique_label_list=self._docks.unique_label_list
                ),
            )
        self._label_dialog.add_label_history(label=label)

    def add_label(self, *, shape: Shape) -> None:
        assert shape.label is not None
        label_list_item = LabelListWidgetItem(shape=shape)
        self._docks.label_list.add_item(item=label_list_item)
        self._register_label(label=shape.label)

        fill_rgb = self._get_rgb_by_label(
            label=shape.label,
            unique_label_list=self._docks.unique_label_list,
        )
        label_list_item.set_label(
            text=_widgets.format_shape_label(shape=shape),
            color=fill_rgb,
        )

    def _get_rgb_by_label(
        self,
        *,
        label: str,
        unique_label_list: UniqueLabelQListWidget,
    ) -> tuple[int, int, int]:
        label_index = unique_label_list.label_index(label=label)
        shape_color = self._shape_color_preview
        if shape_color is None:
            shape_color = self._config["shape_color"]
        return _shape_color.resolve_shape_color(
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

    def _load_shapes(self, *, shapes: list[Shape], replace: bool) -> None:
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

    def _commit_shapes(self, *, shapes: list[Shape], changed: bool = True) -> None:
        # Canvas loading pushes the one undo snapshot, so callers must not
        # back up again. Edits the canvas makes itself (delete, point removal,
        # drag) already snapshot there and only need the dirty mark.
        self._docks.label_list.clear()
        self._load_shapes(shapes=shapes, replace=True)
        if changed:
            self.mark_dirty()
        else:
            self._sync_edit_actions()

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
        if hasattr(self, "_docks"):
            self._sync_flag_dock()

    def _on_flag_dock_toggled(self, checked: bool, /) -> None:  # noqa: FBT001 -- QAction.toggled slot
        # Hiding or minimizing the window toggles the dock too, which is not
        # the user closing it.
        if self.isVisible() and not self.isMinimized():
            self._flag_dock_wanted = checked

    def _sync_flag_dock(self, *, hide_empty: bool = True) -> None:
        # An empty Flags dock only takes space, so it stays hidden until there
        # are flags to show.
        dock = self._docks.flag_dock
        with QtCore.QSignalBlocker(dock.toggleViewAction()):
            dock.setVisible(
                self._flag_dock_wanted
                and (not hide_empty or self._docks.flag_list.count() > 0)
            )

    def _capture_save_request(self, *, label_path: str) -> SaveRequest:
        assert self._image_path
        assert self._annotation is not None
        image_path = self._file_list_image_path or self._image_path
        # An Annotation File can hold the only copy of its Image; dropping the
        # embedded data then loses the Image and the file no longer opens.
        has_image_file = Path(image_path).is_file() and image_path.lower().endswith(
            _list_supported_image_extensions()
        )
        return SaveRequest(
            filename=label_path,
            annotation=Annotation(
                image_path=_label_path.resolve_stored_image_path(
                    image_path=image_path,
                    label_dir=Path(label_path).parent,
                ),
                image_data=self._annotation.image_data,
                shapes=self._shape_dicts(),
                flags=self._read_flag_dock_states(),
                other_data=copy.deepcopy(self._annotation.other_data),
            ),
            image_height=self._image.height(),
            image_width=self._image.width(),
            save_image_data=self._config["with_image_data"] or not has_image_file,
            # Save As confirms an overwrite in its dialog; no other save may
            # replace another Image's Annotation File.
            owner_image_path=(
                None
                if self._save_target
                == _SaveTarget(path=label_path, overwrite_confirmed=True)
                else image_path
            ),
        )

    def _shape_dicts(self) -> list[ShapeDict]:
        # The Shapes as a save writes them.
        return [
            _shape_to_dict(shape=shape)
            for item in self._docks.label_list
            if (shape := item.shape()) is not None
        ]

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

    def _save_error_text(self, *, error: BaseException) -> str:
        if isinstance(error, _save_request.ForeignAnnotationFileError):
            return (
                self.tr("The Annotation File belongs to another Image: %s")
                % error.filename
            )
        return str(error)

    def _show_save_failure(self, *, label_path: str, error: BaseException) -> None:
        self._failed_save_path = label_path
        self._status_bar.save.setText(self.tr("Save failed"))
        self._status_bar.save.setToolTip(
            f"{label_path}\n{self._save_error_text(error=error)}"
        )
        self._status_bar.retry.show()

    def _retry_save(self) -> None:
        if self._failed_save_path is not None:
            self._queue_auto_save(label_path=self._failed_save_path)

    def save_labels(self, *, label_path: str) -> bool:
        self._save_writer.discard_pending()
        self._wait_for_save()
        try:
            request = self._capture_save_request(label_path=label_path)
            _save_request.write_save_request(request=request)
        except (LabelFileError, OSError, ValueError) as e:
            self._show_save_failure(label_path=label_path, error=e)
            self.show_error_message(
                title=self.tr("Error Saving Annotation File"),
                message=self.tr("<b>%s</b>") % self._save_error_text(error=e),
            )
            return False
        self._record_file_contents(request=request)
        self._record_saved_annotation(label_path=request.filename)
        return True

    def _record_file_contents(self, *, request: SaveRequest) -> None:
        # Every successful write changes what the file holds.
        self._file_contents = _FileContents(
            path=request.filename,
            shapes=request.annotation.shapes,
            flags=request.annotation.flags,
        )

    def _insert_shapes(self, *, shapes: list[Shape]) -> None:
        # Committing reloads the shapes, which would discard an unfinished one.
        if not shapes or self._canvas_widgets.canvas.is_drawing:
            return
        _label_flags.apply_default_flags(
            shapes=shapes, label_flags=self._config["label_flags"]
        )
        # A pasted or duplicated copy of a locked shape starts out editable.
        for shape in shapes:
            shape.locked = False
        self._commit_shapes(shapes=[*self._canvas_widgets.canvas.shapes, *shapes])
        self._canvas_widgets.canvas.select_shapes(shapes=shapes)

    def _merge_selected_shapes(self) -> None:
        canvas = self._canvas_widgets.canvas
        selected = list(canvas.selected_shapes)
        if not _shape.can_merge_shapes(shapes=selected):
            return
        merged = _shape.merge_masks(shapes=selected)
        # The merged shape takes the first input's slot so the Label List
        # order is preserved; the other inputs are dropped.
        shapes = [
            merged if s is selected[0] else s
            for s in canvas.shapes
            if s is selected[0] or s not in selected
        ]
        self._commit_shapes(shapes=shapes)
        canvas.select_shapes(shapes=[merged])

    def _convert_image_size(self, *, target: ConvertTarget) -> tuple[int, int] | None:
        # New points stay inside the image unless out-of-bounds points are on.
        # A mask always does: pixels outside the image do not exist (ADR 0004).
        if target != "mask" and self._config["canvas"]["allow_out_of_bounds_points"]:
            return None
        return (self._image.width(), self._image.height())

    def _convert_selected_shapes(self, *, target: ConvertTarget) -> None:
        canvas = self._canvas_widgets.canvas
        selected = list(canvas.selected_shapes)
        image_size = self._convert_image_size(target=target)
        if _shape.convert_blocker(
            shapes=selected, target=target, image_size=image_size
        ):
            return

        def convert(detail: int | None) -> dict[Shape, list[Shape]]:
            return {
                s: _shape.convert_shape(
                    shape=s, target=target, image_size=image_size, detail=detail
                )
                for s in selected
                if s.shape_type != target
            }

        def preview(detail: int) -> None:
            canvas.set_conversion_preview(
                shapes=[c for shapes in convert(detail).values() for c in shapes]
            )

        detail = None
        if _shape.conversion_needs_detail(shapes=selected, target=target):
            dialog = ConversionDetailDialog(
                title=self.tr("Convert to Polygon"),
                detail=self._conversion_detail,
                on_detail_changed=preview,
                parent=self,
            )
            preview(self._conversion_detail)
            accepted = dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted
            canvas.set_conversion_preview(shapes=[])
            if not accepted:
                # Choosing the item checked it; the selection kept its kind.
                self._sync_edit_actions()
                return
            detail = self._conversion_detail = dialog.detail
        converted = convert(detail)
        # A mask split into several polygons keeps them together in a new
        # Group, unless it already had one.
        split: list[Shape] = []
        for i, shapes in enumerate(converted.values()):
            if len(shapes) > 1 and shapes[0].group_id is None:
                for c in shapes:
                    c.group_id = i
                split.extend(shapes)
        _automation.assign_available_group_ids(
            shapes=split, existing_shapes=canvas.shapes
        )
        self._commit_shapes(
            shapes=[c for s in canvas.shapes for c in converted.get(s, [s])]
        )
        canvas.select_shapes(
            shapes=[c for s in selected for c in converted.get(s, [s])]
        )

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
        # The model reports every data change, such as a new label or color;
        # only a flipped checkbox toggles visibility.
        shape = item.shape()
        if shape is None or shape.visible == is_visible_new:
            return

        selected_group = (
            self._docks.label_list.selection_at_press()
            or self._docks.label_list.selected_items()
        )
        items_to_toggle = (
            selected_group
            if item in selected_group and len(selected_group) > 1
            else [item]
        )
        self._apply_item_visibility(
            changes=[(it, is_visible_new) for it in items_to_toggle]
        )

    def _apply_item_visibility(
        self, *, changes: list[tuple[LabelListWidgetItem, bool]]
    ) -> None:
        canvas = self._canvas_widgets.canvas
        label_list = self._docks.label_list
        changed = False
        # Detached so a row's own handler cannot flip its selection group
        # again, and so the whole change takes one Undo snapshot. The model
        # keeps notifying the view, which repaints the checkboxes.
        label_list.item_changed.disconnect(self._on_label_item_changed)
        try:
            for item, value in changes:
                shape = item.shape()
                if shape is None or shape.visible == value:
                    continue
                item.setCheckState(
                    Qt.CheckState.Checked if value else Qt.CheckState.Unchecked
                )
                canvas.set_shape_visible(shape=shape, value=value)
                changed = True
        finally:
            label_list.item_changed.connect(self._on_label_item_changed)
        if changed:
            canvas.backup_shapes()
            self._sync_edit_actions()

    def _on_label_order_changed(self) -> None:
        self._commit_shapes(
            shapes=[
                s for item in self._docks.label_list if (s := item.shape()) is not None
            ]
        )

    # Callback functions:

    def _on_new_shape(self) -> None:
        entry = self._ask_new_shape_entry(query="")
        if entry is None:
            # Drop the snapshot first so the busy_changed handler that
            # undo_last_line triggers sees the Undo state without it.
            self._canvas_widgets.canvas.shape_backups.pop()
            self._canvas_widgets.canvas.undo_last_line()
            return

        self._docks.label_list.clearSelection()
        shapes = self._canvas_widgets.canvas.set_last_label(
            text=entry.label, flags=entry.flags
        )
        _label_flags.apply_default_flags(
            shapes=shapes, label_flags=self._config["label_flags"]
        )
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
        self.mark_dirty()

    def _ask_new_shape_entry(self, *, query: str) -> LabelDialogEntry | None:
        # One entry labels every Shape one action made. An AI-Find All query is
        # a prompt, not always the label ("black dog" may be a "dog"), so it
        # only prefills the dialog. None discards the new Shapes.
        items = self._docks.unique_label_list.selectedItems()
        text = items[0].data(Qt.ItemDataRole.UserRole) if items else None
        if self._config["display_label_popup"] or not text:
            entry = self._label_dialog.popup(text=query or text)
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
            return None
        return entry

    def _on_inference_produced_no_shapes(self) -> None:
        self.show_status_message(
            message=self.tr("AI inference produced no new annotation."), delay=5000
        )

    def _on_example_box_unsupported(self) -> None:
        self.show_status_message(
            message=self.tr("%s can't use an example box. Choose SAM 3.")
            % self._model_manager.models[
                self._canvas_widgets.canvas.get_ai_find_all_model_name()
            ],
            delay=5000,
        )

    def _on_inference_failed(self, message: str, /) -> None:
        self.show_status_message(
            message=self.tr("AI inference failed: %s") % message, delay=10000
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
        image_pos = canvas.transform_widget_point_to_image(point=pos)
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
            point=image_pos, area=canvas.sizeHint()
        )
        current = canvas.mapFrom(viewport, viewport_pos)
        self._move_canvas_view(step=current - target, constrain_to_center=False)

    def _set_zoom_to_original(self) -> None:
        self._zoom_mode = _ZoomMode.MANUAL_ZOOM
        self._set_zoom(value=100, pos=None)

    def _add_zoom(self, *, steps: float, pos: QtCore.QPointF | None) -> None:
        # Steps in and out cancel, so zooming in then out returns to the start.
        zoom_value = (
            self._canvas_widgets.zoom_widget.value() * _widgets.ZOOM_STEP_FACTOR**steps
        )
        self._zoom_mode = _ZoomMode.MANUAL_ZOOM
        self._set_zoom(value=zoom_value, pos=pos)

    def _zoom_requested(self, delta: int, pos: QtCore.QPointF, /) -> None:
        # 120 is one mouse wheel notch. Trackpads send many smaller deltas,
        # so they zoom in finer steps instead of a full step per event.
        self._add_zoom(steps=delta / 120, pos=pos)

    def set_fit_window_mode(self, value: bool = True, /) -> None:  # noqa: FBT001, FBT002 -- QAction.triggered slot
        target = _ZoomMode.FIT_WINDOW if value else _ZoomMode.MANUAL_ZOOM
        self._switch_zoom_mode(mode=target)

    def set_fit_selection_mode(self, value: bool = True, /) -> None:  # noqa: FBT001, FBT002 -- QAction.triggered slot
        target = _ZoomMode.FIT_SELECTION if value else _ZoomMode.MANUAL_ZOOM
        self._switch_zoom_mode(mode=target)

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

    def _switch_zoom_mode(self, *, mode: _ZoomMode) -> None:
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
            img=_image_codec.img_data_to_pil(img_data=self._annotation.image_data),
            callback=self._on_brightness_contrast_changed,
            brightness=brightness,
            contrast=contrast,
            parent=self,
        )

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
        self._apply_item_visibility(
            changes=[
                (item, not shape.visible if value is None else value)
                for item in self._docks.label_list
                if (shape := item.shape()) is not None
            ]
        )

    def _read_annotation_file(
        self, *, label_path: str, image_path: str | None
    ) -> tuple[Annotation, str | None] | None:
        # The second value is a located Image path, which _load_file writes to
        # the Annotation File once the load is certain to complete.
        try:
            try:
                annotation = self._read_confirming_large_image(
                    read=lambda *, max_decode_mb: _label_file.read_label_file(
                        filename=label_path, max_decode_mb=max_decode_mb
                    )
                )
                return None if annotation is None else (annotation, None)
            except ImageNotFoundError as e:
                # An Annotation File found for an Image has only a stale
                # recorded path, which the next save replaces. One opened
                # directly needs the user to locate its Image.
                located = image_path is None
                if image_path is None:
                    image_path = self._locate_missing_image(
                        label_path=label_path, exc=e
                    )
                    if image_path is None:
                        return None
                stored_image_path = _label_path.resolve_stored_image_path(
                    image_path=image_path, label_dir=Path(label_path).parent
                )
                annotation = self._read_confirming_large_image(
                    read=lambda *, max_decode_mb: _label_file.read_label_file(
                        filename=label_path,
                        image_path_override=stored_image_path,
                        max_decode_mb=max_decode_mb,
                    )
                )
                if annotation is None:
                    return None
                return annotation, stored_image_path if located else None
        except LabelFileError as e:
            self._show_file_open_error(
                path=label_path, file_kind="label", exc=e, extra=None
            )
            return None

    def _locate_missing_image(
        self, *, label_path: str, exc: ImageNotFoundError
    ) -> str | None:
        dialog = self._make_image_not_found_dialog(exc=exc)
        dialog.setInformativeText(
            self.tr("Locating the image updates the annotation file to refer to it.")
        )
        locate_button = dialog.addButton(
            self.tr("Locate Image…"), QtWidgets.QMessageBox.ButtonRole.AcceptRole
        )
        dialog.addButton(QtWidgets.QMessageBox.StandardButton.Cancel)
        dialog.setDefaultButton(locate_button)
        dialog.exec()
        located_path = ""
        if dialog.clickedButton() is locate_button:
            missing_dir = Path(exc.image_path).parent
            located_path, _ = QtWidgets.QFileDialog.getOpenFileName(
                self,
                self.tr("Locate Image"),
                str(missing_dir if missing_dir.is_dir() else Path(label_path).parent),
                self.tr("Images (%s)")
                % " ".join(f"*{ext}" for ext in _list_supported_image_extensions()),
            )
        if not located_path:
            self.show_status_message(
                message=self.tr("Failed to load: {path}").format(path=label_path)
            )
            return None
        return located_path

    def _make_image_not_found_dialog(
        self, *, exc: ImageNotFoundError
    ) -> QtWidgets.QMessageBox:
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
        return dialog

    def _read_image_as_annotation(self, *, image_path: str) -> Annotation | None:
        try:
            image_data = self._read_confirming_large_image(
                read=lambda *, max_decode_mb: _label_file.read_image_file(
                    filename=image_path, max_decode_mb=max_decode_mb
                )
            )
        except OSError as e:
            self._show_file_open_error(
                path=image_path, file_kind="image", exc=e, extra=None
            )
            return None
        if image_data is None:
            return None
        return Annotation(
            image_path=os.path.basename(image_path),
            image_data=image_data,
            shapes=[],
            flags={},
            other_data={},
        )

    def _read_confirming_large_image[T](self, *, read: Callable[..., T]) -> T | None:
        # None means the user declined to open an image past the decode limit.
        try:
            return read(max_decode_mb=_max_decode_mb())
        except (OSError, LabelFileReadError) as e:
            limit_error = e.__cause__ if isinstance(e, LabelFileReadError) else e
            if not isinstance(limit_error, ImageDecodeLimitError):
                raise
        if not self._confirm_large_image_open(
            requirement=ImageDecodeRequirement(
                width=limit_error.width,
                height=limit_error.height,
                required_mb=limit_error.required_mb,
            ),
            limit_mb=QtGui.QImageReader.allocationLimit(),
        ):
            return None
        self._large_image_confirmed = True
        return read(max_decode_mb=None)

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
        self._large_image_confirmed = False
        file_list_image_path = (
            None
            if _label_file.is_label_file_path(filename=image_or_label_path)
            else image_or_label_path
        )

        # Keep Previous carries Shapes onto another Image. Reloading the open
        # one, as a change of Annotation Folder does, would copy its Shapes
        # into the new destination, discarded edits included.
        is_reload = image_or_label_path in (
            self._file_list_image_path,
            self._image_path,
            self._label_file_path,
        )
        prev_shapes: list[Shape] = (
            self._canvas_widgets.canvas.shapes
            if not is_reload
            and (
                self._config["keep_prev"]
                or QtWidgets.QApplication.keyboardModifiers()
                == (
                    Qt.KeyboardModifier.ControlModifier
                    | Qt.KeyboardModifier.ShiftModifier
                )
            )
            else []
        )
        if not QtCore.QFile.exists(image_or_label_path):
            self.show_error_message(
                title=self.tr("Error Opening File"),
                message=self.tr("No such file: <b>%s</b>") % image_or_label_path,
            )
            return False
        self.show_status_message(
            message=self.tr("Loading %s...") % Path(image_or_label_path).name
        )

        t0_load_file = time.time()
        label_path = (
            image_or_label_path
            if file_list_image_path is None
            else _label_path.find_label_path(
                image_path=image_or_label_path,
                output_dir=self._opened_folder.output_dir,
                root_prefix=self._opened_folder.root,
                cached=False,
            )
        )
        if label_path is None:
            annotation = self._read_image_as_annotation(image_path=image_or_label_path)
            if annotation is None:
                return False
            located_image_path = None
            image_path = image_or_label_path
            label_file_path = None
            shapes = []
        else:
            read_result = self._read_annotation_file(
                label_path=label_path, image_path=file_list_image_path
            )
            if read_result is None:
                return False
            annotation, located_image_path = read_result
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
            requirement = _utils.get_image_decode_requirement(
                image_data=annotation.image_data
            )
            original_limit = QtGui.QImageReader.allocationLimit()
            if (
                requirement is not None
                and max(requirement.width, requirement.height)
                <= _label_file.RASTER_MAX_SIDE
                and 0 < original_limit < requirement.required_mb
            ):
                if (
                    not self._large_image_confirmed
                    and not self._confirm_large_image_open(
                        requirement=requirement, limit_mb=original_limit
                    )
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
                    f"*{ext}" for ext in _list_supported_image_extensions()
                )
                extra = self.tr("Allowed formats: {formats}").format(formats=formats)
            self._show_file_open_error(
                path=image_or_label_path,
                file_kind="image",
                exc=None,
                extra=extra,
            )
            return False

        if located_image_path is not None:
            assert label_path is not None
            try:
                # Choosing the Image was the confirmation, and nothing can
                # cancel this load any more, so the repair is written now.
                _label_file.relink_label_file(
                    filename=label_path, image_path=located_image_path
                )
            except LabelFileError as e:
                self._show_file_open_error(
                    path=label_path, file_kind="label", exc=e, extra=None
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
        # An Annotation File with no Shapes is a deliberate empty annotation.
        carry_prev_shapes = bool(prev_shapes) and not shapes and label_file_path is None
        if carry_prev_shapes:
            # A lock approves a shape on its own image, not on the next one.
            for shape in prev_shapes:
                shape.locked = False
        self._load_shapes(
            shapes=prev_shapes if carry_prev_shapes else shapes, replace=True
        )
        self._load_flags(flags=annotation.flags, widget=self._docks.flag_list)
        # The carried Shapes are not in this Image's file.
        self._file_contents = _FileContents(
            path=label_file_path,
            shapes=[] if carry_prev_shapes else self._shape_dicts(),
            flags=self._read_flag_dock_states(),
        )
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
        self._update_zoom_floor()
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
        self.show_status_message(
            message=self.tr("Loaded %s") % Path(image_or_label_path).name
        )
        logger.info(
            "Loaded file: {!r} in {:.0f}ms",
            image_or_label_path,
            (time.time() - t0_load_file) * 1000,
        )
        return True

    @override
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
        ):
            # The outer window resizes before its nested layout settles. Observe
            # the scroll area, whose size is also independent of scrollbar changes.
            self._update_zoom_floor()
            if self._zoom_mode != _ZoomMode.MANUAL_ZOOM:
                self._adjust_scale()
        return super().eventFilter(watched, event)

    def _update_zoom_floor(self) -> None:
        # Let an image too big for 1% still zoom out to half of Fit to Window.
        half_fit_percent = self._fit_window_scale() * 100 / 2
        self._canvas_widgets.zoom_widget.setMinimum(
            min(_widgets.MIN_ZOOM, half_fit_percent)
        )

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
        # The scroll area's size rather than its viewport's, which shrinks while
        # scroll bars show.
        scroll_area = self._canvas_widgets.scroll_area
        pixmap = self._canvas_widgets.canvas.pixmap
        available_w = scroll_area.width() - 2 * scroll_area.frameWidth()
        available_h = scroll_area.height() - 2 * scroll_area.frameWidth()
        scale_by_width = available_w / pixmap.width()
        scale_by_height = available_h / pixmap.height()
        return min(scale_by_width, scale_by_height)

    def _reset_layout(self) -> None:
        self._window_state.remove(WINDOW_LAYOUT_KEY)
        self.restoreState(self._default_state)

    @override
    def saveState(self, /, version: int | None = 0) -> QtCore.QByteArray:
        # Window state holds the Flags dock as the user left it, not as an
        # empty list hid it.
        self._sync_flag_dock(hide_empty=False)
        state = super().saveState(version or 0)
        self._sync_flag_dock()
        return state

    @override
    def restoreState(
        self,
        state: QtCore.QByteArray | bytes | bytearray | memoryview,
        /,
        version: int | None = 0,
    ) -> bool:
        self._sync_flag_dock(hide_empty=False)
        restored = super().restoreState(state, version or 0)
        self._flag_dock_wanted = not self._docks.flag_dock.isHidden()
        self._sync_flag_dock()
        return restored

    @override
    def closeEvent(self, a0: QtGui.QCloseEvent, /) -> None:
        if not self._can_continue():
            a0.ignore()
            return
        self._model_manager.shutdown()
        self._save_writer.shutdown()
        self._image_prefetcher.shutdown()
        self._osam_worker.shutdown()
        self._window_state.setValue(WINDOW_SIZE_KEY, self.size())
        self._window_state.setValue(WINDOW_POSITION_KEY, self.pos())
        self._window_state.setValue(WINDOW_LAYOUT_KEY, self.saveState())

    @override
    def dragEnterEvent(self, a0: QtGui.QDragEnterEvent, /) -> None:
        # Accepting only drags that carry a loadable image keeps the cursor
        # from promising a drop that would change nothing.
        a0.setAccepted(bool(_extract_dropped_image_paths(mime=a0.mimeData())))

    @override
    def dropEvent(self, a0: QtGui.QDropEvent, /) -> None:
        image_files = self._new_image_files(
            image_files=_extract_dropped_image_paths(mime=a0.mimeData())
        )
        # Only a dropped Image the Image List shows is opened, which replaces
        # the document.
        if any(self._matches_file_search(image_path=path) for path in image_files):
            if not self._can_continue():
                a0.ignore()
                return
            # A Discard is final: selecting the dropped Image must not ask again.
            self.mark_clean()
        self._add_image_files(image_files=image_files)

    # User Dialogs #

    def _get_neighbor_image_path(self, *, step: Literal[-1, 1]) -> str | None:
        paths = self._opened_folder.image_paths
        current_path = self._file_list_image_path
        # Closing an Image retains its selected row as the navigation origin.
        if current_path is None and (item := self._docks.file_list.currentItem()):
            current_path = _file_list_item_path(item=item)
        try:
            current = paths.index(current_path or "")
        except ValueError:
            current = -1
        # Filtering can hide the active row; navigation still follows directory order.
        indices = (
            range(current - 1, -1, -1) if step == -1 else range(current + 1, len(paths))
        )
        return next(
            (
                paths[i]
                for i in indices
                if self._matches_file_search(image_path=paths[i])
            ),
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
        formats = [f"*{ext}" for ext in _list_supported_image_extensions()]
        filters = self.tr("Images and annotation files (%s)") % " ".join(
            formats + [f"*{_label_file.LABEL_FILE_SUFFIX}"]
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
        if self._opened_folder.output_dir is not None:
            default_output_dir = str(self._opened_folder.output_dir)
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

        if not self._switch_output_dir(output_dir=Path(output_dir)):
            return
        self._docks.annotation_folder_footer.set_missing(missing=None)
        assert self._opened_folder.root is not None
        self._remember_output_dir(opened_dir=self._opened_folder.root)
        self.statusBar().showMessage(
            self.tr("Annotation Folder: %s") % self._opened_folder.output_dir
        )
        self.statusBar().show()

    def _clear_output_dir(self) -> None:
        if not self._can_continue() or not self._switch_output_dir(output_dir=None):
            return
        self._docks.annotation_folder_footer.set_missing(missing=None)
        if self._opened_folder.root is not None:
            self._remember_output_dir(opened_dir=self._opened_folder.root)

    def _switch_output_dir(self, *, output_dir: Path | None) -> bool:
        # Reload the current image against the candidate directory and keep
        # the previous directory when that reload fails, so a bad candidate
        # never becomes the autosave target.
        previous_folder = self._opened_folder
        self._opened_folder = previous_folder._replace(output_dir=output_dir)
        if self._file_list_image_path is not None and not self._load_file(
            image_or_label_path=self._file_list_image_path
        ):
            self._opened_folder = previous_folder
            return False
        self._save_target = None
        self._refresh_file_list()
        return True

    @property
    def _opened_folder(self) -> _OpenedFolder:
        return self._opened_folder_value

    @_opened_folder.setter
    def _opened_folder(self, value: _OpenedFolder, /) -> None:
        # The Annotation Folder footer mirrors every change, wherever it comes from.
        self._opened_folder_value = value
        self._docks.annotation_folder_footer.set_folder(folder=value.output_dir)

    def _save_label_file(self, *, save_as: bool) -> None:
        assert not self._image.isNull(), "cannot save empty image"

        label_path: str | None = None
        if not save_as:
            # A first auto-save already owns a destination, even before it finishes.
            label_path = self._save_writer.get_latest_path()
            if label_path is None and (
                (
                    self._save_target is not None
                    and self._save_target.overwrite_confirmed
                )
                or self._label_file_path is not None
            ):
                label_path = self._save_destination()
        if label_path is None:
            label_path = self.prompt_save_file_path()
            if label_path:
                # The dialog confirmed any overwrite. Keep the chosen
                # destination through failure, Retry, and later edits.
                self._save_target = _SaveTarget(
                    path=label_path, overwrite_confirmed=True
                )

        if not label_path:
            logger.warning("label_path={!r} is empty, so cannot save", label_path)
            return

        self.save_labels(label_path=label_path)

    def prompt_save_file_path(self) -> str:
        assert self._image_path is not None
        # Suggest where the document saves until the user picks elsewhere.
        target = self._save_target
        default_path = (
            target.path
            if target is not None and not target.overwrite_confirmed
            else _label_path.resolve_label_path(
                image_path=self._file_list_image_path or self._image_path,
                output_dir=self._opened_folder.output_dir,
                root_prefix=self._opened_folder.root,
            )
        )
        # The dialog cannot preselect a file in a mirrored subfolder of the
        # Annotation Folder that does not exist yet.
        with contextlib.suppress(OSError):
            Path(default_path).parent.mkdir(parents=True, exist_ok=True)
        label_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            parent=self,
            caption=self.tr("Save Annotation File"),
            dir=default_path,
            filter=self.tr("Annotation files (*%s)") % _label_file.LABEL_FILE_SUFFIX,
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
        return _label_path.resolve_label_path(
            image_path=self._file_list_image_path or self._image_path,
            output_dir=self._opened_folder.output_dir,
            root_prefix=self._opened_folder.root,
        )

    def _confirm_deletion(self, *, message: str) -> bool:
        msg_box = QtWidgets.QMessageBox(self)
        msg_box.setIcon(QtWidgets.QMessageBox.Icon.Warning)
        msg_box.setWindowTitle(self.tr("Delete Annotation File"))
        # File names may contain "<b>" and would otherwise render as markup.
        msg_box.setTextFormat(Qt.TextFormat.PlainText)
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
        # An in-flight first save may not have created the file yet; the
        # deletion below resolves the path again after waiting for it.
        label_path = self._own_label_file_path()
        if label_path is None:
            msg = self.tr("Delete the annotation file? You can't undo this.")
        else:
            msg = self.tr('Delete "{}"? You can\'t undo this.').format(
                Path(label_path).name
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
        self._load_flags(flags={}, widget=self._docks.flag_list)
        assert self._annotation is not None
        self._annotation = dataclasses.replace(
            self._annotation, flags={}, other_data={}
        )
        # Drop the pre-delete backups first so undo cannot resurrect the
        # annotations of the file we just removed; the reload below re-seeds the
        # stack with the empty state, keeping "top mirrors current" intact.
        self._canvas_widgets.canvas.shape_backups.clear()
        self._canvas_widgets.canvas.load_shapes(shapes=[], replace=True)
        # As an Image with no file.
        self._file_contents = _FileContents(
            path=None, shapes=[], flags=self._read_flag_dock_states()
        )
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
        if self._config["ai"]["default"] == model_id:
            return
        self._apply_setting_change(("ai", "default"), model_id)

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
            self._ai_annotation.set_polygon_detail(detail=detail)
            self._canvas_widgets.canvas.set_ai_polygon_detail(detail=detail)
        elif key_path == ("canvas", "allow_out_of_bounds_points"):
            canvas = self._canvas_widgets.canvas
            canvas.set_allow_out_of_bounds_points(
                value=self._config["canvas"]["allow_out_of_bounds_points"]
            )
            canvas.update()
            # Whether a bounding box has area depends on clipping it.
            self._sync_edit_actions()
        elif key_path[0] == "shape_color":
            self._refresh_shape_colors()
        elif key_path[0] == "labels":
            self._apply_predefined_labels()
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
            self._recreate_label_dialog()
        elif key_path == ("ai", "default"):
            self._ai_annotation.set_current_model(
                model_name=self._config["ai"]["default"] or ""
            )
            self._canvas_widgets.canvas.set_ai_model_name(
                model_name=self._ai_annotation.current_model_id
            )
        elif key_path == ("ai", "text_model"):
            self._ai_text.set_model_name(
                model_name=self._config["ai"]["text_model"] or ""
            )
        elif key_path == ("ai", "device"):
            self._osam_worker.set_device(device=self._config["ai"]["device"])
            self._model_manager.set_device(device=self._config["ai"]["device"])
        elif key_path == ("ai", "suppress_existing_shape_matches"):
            self._canvas_widgets.canvas.set_ai_existing_shape_suppression(
                enabled=self._config["ai"]["suppress_existing_shape_matches"]
            )

    def _apply_predefined_labels(self) -> None:
        # Update predefined labels in place so session history (labels learned
        # from loaded/created shapes via add_label_history) is preserved, while
        # a removed predefined label drops from suggestions unless it was used
        # this session.
        self._label_dialog.set_predefined_labels(labels=self._config["labels"] or [])
        # The Found in files section is append-only (a shape's label stays after
        # the shape is deleted), so a label leaving Settings stays there when
        # it was used this session, as it does in the dialog's suggestions.
        self._docks.unique_label_list.set_settings_labels(
            labels=self._config["labels"] or [],
            found_in_annotations=self._label_dialog.label_history,
            color=lambda label: self._get_rgb_by_label(
                label=label, unique_label_list=self._docks.unique_label_list
            ),
        )
        # Moving labels between sections changes their positions, and auto
        # colors follow position.
        self._refresh_shape_colors()
        self._refresh_unused_labels()

    def _recreate_label_dialog(self) -> None:
        # LabelDialog reads sort_labels, show_label_text_field and
        # label_completion only during construction.
        old_label_dialog = self._label_dialog
        self._label_dialog = self._make_label_dialog(
            label_history=old_label_dialog.label_history
        )
        self._label_dialog.remember_label(label=old_label_dialog.last_label)
        old_label_dialog.deleteLater()

    def _refresh_shape_colors(self) -> None:
        unique_labels = self._docks.unique_label_list
        for label in unique_labels.labels():
            item = unique_labels.find_label_item(label=label)
            assert item is not None
            color = self._get_rgb_by_label(label=label, unique_label_list=unique_labels)
            item.setData(_widgets.LABEL_COLOR_ROLE, QtGui.QColor(*color))
        for item in self._docks.label_list:
            shape = item.shape()
            assert shape is not None and shape.label is not None
            item.set_label(
                text=_widgets.format_shape_label(shape=shape),
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
        if model_name and self._model_manager.is_ready(model_name=model_name):
            return True
        self._open_models()
        return False

    def _refresh_model_availability(self) -> None:
        available = {
            name
            for name in self._model_manager.models
            if self._model_manager.is_ready(model_name=name)
        }
        downloading = set(self._model_manager.queue)
        if self._model_manager.active is not None:
            downloading.add(self._model_manager.active)
        for widget in (self._ai_annotation, self._ai_text):
            widget.set_available_models(available=available, downloading=downloading)
        self._ai_group.set_download_sizes(sizes=self._model_manager.download_sizes())
        self._canvas_widgets.canvas.set_ai_model_name(
            model_name=self._ai_annotation.current_model_id
        )

    def _download_and_select(
        self, model_name: str, /, *, select: Callable[[str], None]
    ) -> None:
        notice = _widgets.license_notice(model_name=model_name)
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
            message.setText(
                f"{html.escape(notice)}<br><br>{_widgets.license_link(model_name=model_name)}"
            )
            download = message.addButton(
                self.tr("Download"), QtWidgets.QMessageBox.ButtonRole.AcceptRole
            )
            message.addButton(QtWidgets.QMessageBox.StandardButton.Cancel)
            message.exec()
            if message.clickedButton() is not download:
                return
        select(model_name)
        self._model_manager.enqueue(model_name=model_name)

    def _remove_ai_model(self, model_name: str, /) -> None:
        overrides = []
        if self._config["ai"]["default"] == model_name:
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
        if self._canvas_widgets.canvas.get_ai_model_name() == model_name:
            self._canvas_widgets.canvas.set_ai_model_name(model_name="")
        # The worker's server holds the model's files open, so they go once
        # it unloads the model.
        self._model_manager.start_removing(model_name=model_name)
        self._osam_worker.unload(model_name=model_name)

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
            self._refresh_text_model_choices()
        self._settings_dialog.show()
        self._settings_dialog.raise_()
        self._settings_dialog.activateWindow()

    def _edit_settings_labels(self) -> None:
        self._open_settings()
        assert self._settings_dialog is not None
        self._settings_dialog.focus_setting(key_path=("labels",))

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
        return self._label_file_path or _label_path.find_label_path(
            image_path=self._file_list_image_path or self._image_path,
            output_dir=self._opened_folder.output_dir,
            root_prefix=self._opened_folder.root,
            cached=False,
        )

    def _can_continue(self) -> bool:
        self._wait_for_save()
        if not self._is_changed:
            return True
        assert self._image_path is not None
        prompt_text = self.tr('Save annotation changes to "{}"?').format(
            Path(self._image_path).name
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
            self._make_image_not_found_dialog(exc=exc).exec()
            self.show_status_message(
                message=self.tr("Failed to load: {path}").format(path=path)
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
        self.show_status_message(
            message=self.tr("Failed to load: {path}").format(path=path)
        )

    def current_path(self) -> str:
        return str(Path(self._image_path).parent) if self._image_path else "."

    def delete_selected_shapes(self) -> None:
        self.remove_labels(shapes=self._canvas_widgets.canvas.delete_selected())
        self.mark_dirty()

    def _load_from_file_or_dir(self, *, file_or_dir: str) -> None:
        if not file_or_dir:
            raise ValueError("file_or_dir cannot be empty")

        if _label_file.is_label_file_path(filename=file_or_dir):
            # Load before dropping the Image List, so a failed load leaves the
            # previous session and Image List untouched.
            if not self._load_file(image_or_label_path=file_or_dir):
                return
            # The Annotation Folder stays with the folder being closed; one
            # given with --output and no folder still applies.
            self._opened_folder = _OpenedFolder(
                root=None,
                output_dir=self._opened_folder.output_dir
                if self._opened_folder.root is None
                else None,
                image_paths=(),
            )
            self._refresh_file_list()
            self._docks.annotation_folder_footer.set_missing(missing=None)
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
            # A failed load keeps the previous image open beside the new
            # folder's Images: the new Annotation Folder serves those Images,
            # and the open image keeps saving where it did.
            if self._image_path:
                self._save_destination()
            output_dir, missing_output_dir = self._remembered_output_dir(
                opened_dir=opened_dir
            )
            self._import_images_from_dir(root_dir=opened_dir, output_dir=output_dir)
            if self.image_list:
                # Selecting the first row emits no change signal when it is
                # already current (reopening the same directory), so drive the
                # reload directly while retaining the prior item for rollback.
                file_list = self._docks.file_list
                previous_item = file_list.currentItem()
                with QtCore.QSignalBlocker(file_list):
                    file_list.setCurrentRow(0)
                self._load_selected_image(file_list.currentItem(), previous_item)
                file_list.repaint()
        else:
            opened_dir = str(Path(file_or_dir).parent)
            previous_folder = self._opened_folder
            output_dir, missing_output_dir = self._remembered_output_dir(
                opened_dir=opened_dir
            )
            # The Annotation File mirrors the image's place under the folder
            # being opened, not the one being replaced.
            self._opened_folder = previous_folder._replace(
                root=opened_dir, output_dir=output_dir
            )
            # Load before swapping the Image List, so a failed load leaves the
            # previous session and Image List untouched.
            if not self._load_file(image_or_label_path=file_or_dir):
                self._opened_folder = previous_folder
                return
            self._import_images_from_dir(root_dir=opened_dir, output_dir=output_dir)
            # The load ran before the Image List knew the neighbors.
            self._prefetch_neighbors()

        # Set only once the open succeeded, so a rolled-back open keeps the
        # previous session's warning.
        self._docks.annotation_folder_footer.set_missing(missing=missing_output_dir)
        # Shown last so the loading messages do not replace it.
        if missing_output_dir is not None:
            self.statusBar().showMessage(
                self.tr("Annotation Folder not found: %s") % missing_output_dir
            )

    def _remembered_output_dir(
        self, *, opened_dir: str
    ) -> tuple[Path | None, str | None]:
        # The Annotation Folder to use, and a remembered one that is missing.
        remembered = self._remembered_output_dirs().get(os.path.abspath(opened_dir))
        # Report a missing folder to the caller but keep its entry: it may be
        # on a drive that is not mounted right now, and choosing another
        # folder replaces it.
        if remembered is not None and not Path(remembered).is_dir():
            return None, remembered
        return (Path(remembered) if remembered else None), None

    def _remembered_output_dirs(self) -> dict[str, str]:
        return cast(
            dict[str, str], self._window_state.value(ANNOTATION_FOLDERS_KEY, {})
        )

    def _remember_output_dir(self, *, opened_dir: str) -> None:
        folders = self._remembered_output_dirs()
        key = os.path.abspath(opened_dir)
        if self._opened_folder.output_dir is None:
            folders.pop(key, None)
        else:
            folders[key] = os.path.abspath(self._opened_folder.output_dir)
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
            lst.append(_file_list_item_path(item=item))
        return lst

    def _new_image_files(self, *, image_files: list[str]) -> list[str]:
        extensions = _list_supported_image_extensions()
        already_loaded = set(self._opened_folder.image_paths)
        return [
            path
            for path in image_files
            if path not in already_loaded and path.lower().endswith(extensions)
        ]

    def import_dropped_image_files(self, *, image_files: list[str]) -> None:
        self._add_image_files(
            image_files=self._new_image_files(image_files=image_files)
        )

    def _add_image_files(self, *, image_files: list[str]) -> None:
        if not image_files:
            return

        self._opened_folder = self._opened_folder._replace(
            image_paths=(*self._opened_folder.image_paths, *image_files)
        )
        self._refresh_file_list()

        visible_image_paths = self.image_list
        for image_path in image_files:
            if image_path in visible_image_paths:
                self._docks.file_list.setCurrentRow(
                    visible_image_paths.index(image_path)
                )
                self._docks.file_list.repaint()
                return

    def _import_images_from_dir(
        self, *, root_dir: str, output_dir: Path | None
    ) -> None:
        self._docks.file_dock.setEnabled(True)
        self._docks.file_dock.setToolTip("")

        self._prev_opened_dir = root_dir
        self._opened_folder = _OpenedFolder(
            root=root_dir,
            output_dir=output_dir,
            image_paths=tuple(_scan_image_files(root_dir=root_dir)),
        )
        self._refresh_file_list()

    def _refresh_file_list(self) -> None:
        # The Annotation Folder is remembered per opened folder, so choosing
        # one needs a folder, and the footer has nothing to count without
        # images.
        has_folder = self._opened_folder.root is not None
        self._actions.change_output_dir.setEnabled(has_folder)
        self._docks.annotation_folder_footer.setVisible(
            has_folder and bool(self._opened_folder.image_paths)
        )
        # Once per path: the search, the headings and the rows all show it.
        labels = [
            self._file_list_label(image_path=path)
            for path in self._opened_folder.image_paths
        ]
        image_paths = []
        shown_labels = []
        self._hidden_annotated_paths = set()
        for path, label in zip(self._opened_folder.image_paths, labels):
            if self._file_search_pattern.search(label):
                image_paths.append(path)
                shown_labels.append(label)
            elif _label_path.has_label_file(
                image_path=path,
                output_dir=self._opened_folder.output_dir,
                root_prefix=self._opened_folder.root,
            ):
                self._hidden_annotated_paths.add(path)

        file_list = self._docks.file_list
        # Decided from every loaded Image, so headings don't come and go while
        # a search narrows the list.
        self._docks.file_list_delegate.set_labels(labels=labels)
        with QtCore.QSignalBlocker(file_list):
            file_list.clear()
            for image_path, label in zip(image_paths, shown_labels):
                file_list.addItem(
                    _make_image_list_item(
                        image_path=image_path,
                        label=label,
                        output_dir=self._opened_folder.output_dir,
                        root_prefix=self._opened_folder.root,
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
        # (see _label_path._label_path_candidates).
        stems = {
            _label_path.comparable_stem(path=label_path),
            _label_path.comparable_stem(path=Path(label_path).stem),
        }
        file_list = self._docks.file_list
        for row in range(file_list.count()):
            item = file_list.item(row)
            assert item
            if (
                _label_path.comparable_stem(path=_file_list_item_path(item=item))
                in stems
            ):
                _set_annotated_check_state(
                    item=item,
                    output_dir=self._opened_folder.output_dir,
                    root_prefix=self._opened_folder.root,
                )

        # Images hidden by the search box have no item, so keep the count's
        # record of them by the same rule.
        for image_path in self._opened_folder.image_paths:
            if _label_path.comparable_stem(
                path=image_path
            ) not in stems or self._matches_file_search(image_path=image_path):
                continue
            if _label_path.has_label_file(
                image_path=image_path,
                output_dir=self._opened_folder.output_dir,
                root_prefix=self._opened_folder.root,
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
            total=len(self._opened_folder.image_paths),
        )

    def _file_list_label(self, *, image_path: str) -> str:
        # Paths under the opened folder are shown relative to it so the
        # Image List stays readable; the full path stays in the tooltip.
        # ImageListDelegate groups rows by this path's folder.
        relative = _label_path.relative_to_root(
            path=image_path, root_prefix=self._opened_folder.root
        )
        return image_path if relative is None else relative

    def _matches_file_search(self, *, image_path: str) -> bool:
        return bool(
            self._file_search_pattern.search(
                self._file_list_label(image_path=image_path)
            )
        )

    def _update_status_stats(self, mouse_pos: QtCore.QPointF, /) -> None:
        self._status_bar.stats.set_position(x=mouse_pos.x(), y=mouse_pos.y())


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
    _label_flags.apply_default_flags(shapes=shapes, label_flags=label_flags)
    return shapes


def _text_models_unable_to_create(
    *, shape_type: _automation.AiOutputFormat | None
) -> frozenset[str]:
    if shape_type in _automation.MASK_REQUIRED_SHAPE_TYPES:
        return _ai_models.AI_TEXT_BOX_ONLY_MODELS
    return frozenset()


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


def _make_image_list_item(
    *, image_path: str, label: str, output_dir: Path | None, root_prefix: str | None
) -> QtWidgets.QListWidgetItem:
    item = QtWidgets.QListWidgetItem(label)
    item.setData(Qt.ItemDataRole.UserRole, image_path)
    item.setToolTip(os.path.abspath(image_path))
    item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
    _set_annotated_check_state(
        item=item, output_dir=output_dir, root_prefix=root_prefix
    )
    return item


def _set_annotated_check_state(
    *,
    item: QtWidgets.QListWidgetItem,
    output_dir: Path | None,
    root_prefix: str | None,
) -> None:
    has_label = _label_path.has_label_file(
        image_path=_file_list_item_path(item=item),
        output_dir=output_dir,
        root_prefix=root_prefix,
    )
    item.setCheckState(Qt.CheckState.Checked if has_label else Qt.CheckState.Unchecked)


def _file_list_item_path(*, item: QtWidgets.QListWidgetItem) -> str:
    return item.data(Qt.ItemDataRole.UserRole)


def _saved_shapes_equal(*, a: list[Shape], b: list[Shape] | list[ShapeDict]) -> bool:
    # Compares what a save writes, so view state such as visibility is ignored.
    # Shape by Shape, so the first difference ends the comparison.
    return len(a) == len(b) and all(
        _shape_dicts_equal(
            a=_shape_to_dict(shape=shape_a),
            b=shape_b if isinstance(shape_b, dict) else _shape_to_dict(shape=shape_b),
        )
        for shape_a, shape_b in zip(a, b, strict=True)
    )


def _shape_dicts_equal(*, a: ShapeDict, b: ShapeDict) -> bool:
    mask_a, mask_b = a["mask"], b["mask"]
    if {**a, "mask": None} != {**b, "mask": None}:
        return False
    if mask_a is None or mask_b is None:
        return mask_a is mask_b
    return np.array_equal(mask_a, mask_b)


def _shape_to_dict(*, shape: Shape) -> ShapeDict:
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
        max_side=_label_file.RASTER_MAX_SIDE,
    )


def _make_image_too_large_message(*, image_data: bytes) -> str | None:
    # None means the failure is not explained by image size, so the caller
    # falls back to the generic unsupported-format message.

    requirement = _utils.get_image_decode_requirement(image_data=image_data)
    if requirement is None:
        return None
    width = requirement.width
    height = requirement.height

    if max(width, height) > _label_file.RASTER_MAX_SIDE:
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
    extensions = {
        f".{fmt.toStdString().lower()}"
        for fmt in QtGui.QImageReader.supportedImageFormats()
    }
    if PIL.features.check_codec("jpg_2000"):
        extensions.update((".jp2", ".jpx", ".j2k", ".j2c"))
    return tuple(sorted(extensions))


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
