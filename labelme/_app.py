from __future__ import annotations

import enum
import functools
import math
import os
import platform
import re
import subprocess
import time
import typing
import webbrowser
from pathlib import Path
from typing import Final
from typing import Literal
from typing import NamedTuple
from typing import TypeAlias
from typing import cast

import natsort
import numpy as np
import osam
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
from ._label_file import LABEL_FILE_SUFFIX
from ._label_file import Annotation
from ._label_file import LabelFileError
from ._label_file import ShapeDict
from ._label_file import is_label_file_path
from ._label_file import read_image_file
from ._label_file import read_label_file
from ._label_file import write_label_file
from ._label_flags import compile_label_flags
from ._shape import Shape
from ._shape import ShapeType
from ._shape_clipboard import ShapeClipboard
from ._shape_color import resolve_shape_color
from ._widgets import AiAssistedAnnotationWidget
from ._widgets import AiTextToAnnotationWidget
from ._widgets import BrightnessContrastDialog
from ._widgets import Canvas
from ._widgets import EmptyStateWidget
from ._widgets import LabelDialog
from ._widgets import LabelDialogEntry
from ._widgets import LabelDialogField
from ._widgets import LabelListWidget
from ._widgets import LabelListWidgetItem
from ._widgets import Palette
from ._widgets import SettingsDialog
from ._widgets import StatusStats
from ._widgets import ToolBar
from ._widgets import UniqueLabelQListWidget
from ._widgets import ZoomWidget
from ._widgets import download_ai_model
from ._widgets import format_shape_label
from ._widgets.label_list_widget import LABEL_COLOR_ROLE


class _ZoomMode(enum.Enum):
    FIT_WINDOW = enum.auto()
    FIT_WIDTH = enum.auto()
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


class _StatusBarWidgets(NamedTuple):
    message: QtWidgets.QLabel
    stats: StatusStats


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


class _FileSession(NamedTuple):
    image_path: str
    file_list_image_path: str | None
    label_file_path: str | None
    annotation: Annotation
    image: QtGui.QImage
    shapes: list[Shape]


class _DockWidgets(NamedTuple):
    flag_dock: QtWidgets.QDockWidget
    flag_list: QtWidgets.QListWidget
    shape_dock: QtWidgets.QDockWidget
    label_list: LabelListWidget
    label_dock: QtWidgets.QDockWidget
    unique_label_list: UniqueLabelQListWidget
    file_dock: QtWidgets.QDockWidget
    file_search: QtWidgets.QLineEdit
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
    fit_width: QtGui.QAction
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
    zoom: tuple[ZoomWidget | QtGui.QAction, ...]
    on_load_active: tuple[QtGui.QAction, ...]
    on_shapes_present: tuple[QtGui.QAction, ...]
    context_menu: tuple[QtGui.QAction, ...]
    edit_menu: tuple[QtGui.QAction, ...]


class _Menus(NamedTuple):
    file: QtWidgets.QMenu
    edit: QtWidgets.QMenu
    view: QtWidgets.QMenu
    help: QtWidgets.QMenu
    label_list: QtWidgets.QMenu


class MainWindow(QtWidgets.QMainWindow):
    _config_file: Path | None
    _config: dict
    _config_overrides: dict

    _text_osam_session: _automation.OsamSession | None = None
    _is_changed: bool = False
    _shape_clipboard: ShapeClipboard
    _zoom_mode: _ZoomMode
    _prev_opened_dir: str | None
    _canvas_widgets: _CanvasWidgets
    _status_bar: _StatusBarWidgets
    _status_mouse_pos: QtCore.QPointF | None
    _docks: _DockWidgets
    _actions: _Actions
    _persistent_actions: dict[tuple[str, ...], QtGui.QAction]
    _menus: _Menus
    _label_dialog: LabelDialog
    _settings_dialog: SettingsDialog | None = None
    _shape_color_preview: dict | None
    _ai_annotation: AiAssistedAnnotationWidget
    _ai_text: AiTextToAnnotationWidget

    _output_dir: Path | None
    _image: QtGui.QImage
    _annotation: Annotation | None
    _label_file_path: str | None
    _last_failed_auto_save_path: str | None
    _image_path: str | None
    _file_list_image_path: str | None
    _loaded_image_paths: list[str]
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
            lambda _available: self._sync_paste_action()
        )
        self._menus = self._setup_menus()

        self._ai_annotation = AiAssistedAnnotationWidget(
            default_model=self._config["ai"]["default"],
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
        self._ai_text.setEnabled(False)

        self._setup_toolbars()

        self._status_bar = self._setup_status_bar()

        self._setup_app_state(file_or_dir=file_or_dir, output_dir=output_dir)

        self._canvas_widgets.zoom_widget.valueChanged.connect(
            self._apply_zoom_to_canvas
        )
        self._canvas_widgets.scroll_area.installEventFilter(self)

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

    def _join_action_groups(
        self, *groups: typing.Sequence[QtGui.QAction]
    ) -> tuple[QtGui.QAction, ...]:
        # Stitches non-empty action groups together, dropping a separator in
        # between each pair so callers describe *what* belongs together
        # rather than *where* every divider goes.
        new_separator = functools.partial(_utils.new_separator, self)
        joined_actions: list[QtGui.QAction] = []
        for group in groups:
            if not group:
                continue
            if joined_actions:
                joined_actions.append(new_separator())
            joined_actions.extend(group)
        return tuple(joined_actions)

    def _setup_actions(self) -> _Actions:
        action = functools.partial(_utils.new_action, self)
        shortcuts = self._config["shortcuts"]

        about = action(
            text=f"&About {__appname__}",
            slot=functools.partial(
                QMessageBox.about,
                self,
                f"About {__appname__}",
                f"""
<h3>{__appname__}</h3>
<p>Image Polygonal Annotation with Python</p>
<p>Version: {__version__}</p>
<p>Author: Kentaro Wada</p>
<p>
    <a href="https://labelme.io">Homepage</a> |
    <a href="https://labelme.io/docs">Documentation</a> |
    <a href="https://labelme.io/docs/troubleshoot">Troubleshooting</a>
</p>
<p>
    <a href="https://github.com/wkentaro/labelme">GitHub</a> |
    <a href="https://x.com/labelmeai">Twitter/X</a>
</p>
""",
            ),
        )
        open_ = action(
            text=self.tr("&Open"),
            slot=self._open_file_with_dialog,
            shortcut=shortcuts["open"],
            icon="phosphor/folder-open.svg",
            tip=self.tr("Open an image or a label file"),
        )
        open_dir = action(
            text=self.tr("Open &Folder"),
            slot=self._open_dir_with_dialog,
            shortcut=shortcuts["open_dir"],
            icon="phosphor/folder-open.svg",
            tip=self.tr("Open a folder of images"),
        )
        save = action(
            text=self.tr("&Save"),
            slot=lambda: self._save_label_file(save_as=False),
            shortcut=shortcuts["save"],
            icon="phosphor/floppy-disk.svg",
            tip=self.tr("Write the current annotations to disk"),
            enabled=False,
        )
        save_as = action(
            text=self.tr("Save &As"),
            slot=lambda: self._save_label_file(save_as=True),
            shortcut=shortcuts["save_as"],
            icon="phosphor/floppy-disk.svg",
            tip=self.tr("Save the annotations under a new file name"),
            enabled=False,
        )
        save_auto = action(
            text=self.tr("Save Auto&matically"),
            tip=self.tr("Write annotations to disk after every change"),
            checkable=True,
            enabled=True,
        )
        save_auto.setChecked(self._config["auto_save"])
        save_with_image_data = action(
            text=self.tr("Save With &Image Data"),
            tip=self.tr("Embed the source image bytes in the label file"),
            checkable=True,
            checked=self._config["with_image_data"],
        )
        change_output_dir = action(
            text=self.tr("C&hange Output Folder"),
            slot=self.prompt_output_dir,
            shortcut=shortcuts["save_to"],
            icon="phosphor/folders.svg",
            tip=self.tr("Choose a different folder for loading and saving annotations"),
        )
        close = action(
            text=self.tr("&Close"),
            slot=self.close_file,
            shortcut=shortcuts["close"],
            icon="phosphor/x-circle.svg",
            tip=self.tr("Close the current file"),
        )
        delete_file = action(
            text=self.tr("&Delete Label File"),
            slot=self.delete_file,
            shortcut=shortcuts["delete_file"],
            icon="phosphor/file-x.svg",
            tip=self.tr("Permanently remove the current label file"),
            enabled=False,
        )
        keep_prev_action = action(
            text=self.tr("Carry Shapes Forward"),
            shortcut=shortcuts["toggle_keep_prev_mode"],
            tip=self.tr("Reuse shapes from the previous image"),
            checkable=True,
            checked=self._config["keep_prev"],
        )
        toggle_keep_prev_brightness_contrast = action(
            text=self.tr("Keep Previous Brightness/Contrast"),
            checkable=True,
            checked=self._config["keep_prev_brightness_contrast"],
        )
        undo = action(
            text=self.tr("Undo"),
            slot=self.undo_shape_edit,
            shortcut=shortcuts["undo"],
            icon="phosphor/arrow-u-up-left.svg",
            tip=self.tr("Revert the last shape change"),
            enabled=False,
        )
        undo_last_point = action(
            text=self.tr("Undo Last Point"),
            slot=self._canvas_widgets.canvas.undo_last_point,
            shortcut=shortcuts["undo_last_point"],
            icon="phosphor/arrow-u-up-left.svg",
            tip=self.tr("Remove the most recently placed point"),
            enabled=False,
        )
        copy = action(
            text=self.tr("Copy to Clipboard"),
            slot=lambda: self._shape_clipboard.store(
                shapes=self._canvas_widgets.canvas.selected_shapes
            ),
            shortcut=shortcuts["copy_shape"],
            icon="phosphor/copy.svg",
            tip=self.tr("Copy the selected shapes to the clipboard"),
            enabled=False,
        )
        paste = action(
            text=self.tr("Paste from Clipboard"),
            slot=lambda: self._insert_shapes(self._shape_clipboard.paste()),
            shortcut=shortcuts["paste_shape"],
            icon="phosphor/note-pencil.svg",
            tip=self.tr("Paste shapes from the clipboard into this image"),
            enabled=False,
        )
        duplicate = action(
            text=self.tr("Duplicate Shapes"),
            slot=lambda: self._insert_shapes(
                [s.copy() for s in self._canvas_widgets.canvas.selected_shapes]
            ),
            shortcut=shortcuts["duplicate_shape"],
            icon="phosphor/copy.svg",
            tip=self.tr("Add a copy of the selected shapes"),
            enabled=False,
        )
        edit = action(
            text=self.tr("&Edit Label"),
            slot=self._edit_label,
            shortcut=shortcuts["edit_label"],
            icon="phosphor/note-pencil.svg",
            tip=self.tr("Change the label of the selected shape"),
            enabled=False,
        )
        delete = action(
            text=self.tr("Delete Shapes"),
            slot=self.delete_selected_shapes,
            shortcut=shortcuts["delete_shape"],
            icon="phosphor/trash.svg",
            tip=self.tr("Remove the selected shapes"),
            enabled=False,
        )
        remove_point = action(
            text=self.tr("Delete selected vertex"),
            slot=self.remove_selected_point,
            shortcut=shortcuts["remove_selected_point"],
            icon="phosphor/trash.svg",
            tip=self.tr("Delete the selected vertex from the polygon"),
            enabled=False,
        )
        add_point_to_edge = action(
            text=self.tr("Add Point to Edge"),
            slot=self._canvas_widgets.canvas.add_point_to_edge,
            tip=self.tr("Add a vertex on the hovered edge"),
            enabled=False,
        )
        # Every drawing tool wires the same way: pick a shape kind, hand it to
        # _switch_canvas_mode. Building them from one table keeps the nine
        # entries in lockstep instead of nine near-identical calls.
        draw_mode_specs: tuple[tuple[str, str, str | None, str, str], ...] = (
            (
                "polygon",
                self.tr("Polygon"),
                shortcuts["create_polygon"],
                "phosphor/polygon.svg",
                self.tr("Draw a polygon shape"),
            ),
            (
                "rectangle",
                self.tr("Rectangle"),
                shortcuts["create_rectangle"],
                "phosphor/rectangle.svg",
                self.tr("Draw a rectangle shape"),
            ),
            (
                "oriented_rectangle",
                self.tr("Oriented Rectangle"),
                shortcuts["create_oriented_rectangle"],
                "phosphor/rectangle.svg",
                self.tr("Draw a rotatable rectangle"),
            ),
            (
                "circle",
                self.tr("Circle"),
                shortcuts["create_circle"],
                "phosphor/circle.svg",
                self.tr("Draw a circle shape"),
            ),
            (
                "point",
                self.tr("Point"),
                shortcuts["create_point"],
                "phosphor/circles-four.svg",
                self.tr("Mark a single point"),
            ),
            (
                "line",
                self.tr("Line"),
                shortcuts["create_line"],
                "phosphor/line-segment.svg",
                self.tr("Draw a straight line"),
            ),
            (
                "linestrip",
                self.tr("LineStrip"),
                shortcuts["create_linestrip"],
                "phosphor/line-segments.svg",
                self.tr(
                    "Click to add linestrip points; Ctrl+click adds the final point."
                ),
            ),
            (
                "ai_points_to_shape",
                self.tr("AI-Points"),
                None,
                "phosphor/sparkle.svg",
                self.tr("Click points on the object; Ctrl+click finishes the shape."),
            ),
            (
                "ai_box_to_shape",
                self.tr("AI-Box"),
                None,
                "phosphor/sparkle.svg",
                self.tr("Draw a box around the object to segment it."),
            ),
        )
        draw = [
            (
                mode,
                action(
                    text=text,
                    slot=functools.partial(
                        self._switch_canvas_mode, edit=False, create_mode=mode
                    ),
                    shortcut=shortcut,
                    icon=icon,
                    tip=tip,
                    enabled=False,
                ),
            )
            for mode, text, shortcut, icon, tip in draw_mode_specs
        ]

        edit_mode = action(
            text=self.tr("Edit Shapes"),
            slot=functools.partial(
                self._switch_canvas_mode, edit=True, create_mode=None
            ),
            shortcut=shortcuts["edit_shape"],
            icon="phosphor/note-pencil.svg",
            tip=self.tr("Switch to editing existing shapes"),
            enabled=False,
        )
        open_next_img = action(
            text=self.tr("&Next Image"),
            slot=self._open_next_image,
            shortcut=shortcuts["open_next"],
            icon="phosphor/arrow-fat-right.svg",
            tip=self.tr("Go to the next image (hold Ctrl+Shift to carry over labels)"),
            enabled=False,
        )
        open_prev_img = action(
            text=self.tr("&Previous Image"),
            slot=self._open_prev_image,
            shortcut=shortcuts["open_prev"],
            icon="phosphor/arrow-fat-left.svg",
            tip=self.tr(
                "Go to the previous image (hold Ctrl+Shift to carry over labels)"
            ),
            enabled=False,
        )
        keep_prev_zoom = action(
            text=self.tr("&Keep Previous Zoom"),
            checkable=True,
            checked=self._config["keep_prev_scale"],
        )
        fit_window = action(
            text=self.tr("Fit to &Window"),
            slot=self.set_fit_window_mode,
            shortcut=shortcuts["fit_window"],
            icon="phosphor/frame-corners.svg",
            tip=self.tr("Scale the image to always fit the window"),
            checkable=True,
            enabled=False,
        )
        fit_width = action(
            text=self.tr("Fit to Wi&dth"),
            slot=self.set_fit_width_mode,
            shortcut=shortcuts["fit_width"],
            icon="phosphor/frame-corners.svg",
            tip=self.tr("Scale the image to match the window width"),
            checkable=True,
            enabled=False,
        )
        brightness_contrast = action(
            text=self.tr("&Brightness Contrast"),
            slot=self.open_brightness_contrast_dialog,
            shortcut=None,
            icon="phosphor/sliders-horizontal.svg",
            tip=self.tr("Adjust the image brightness and contrast"),
            enabled=False,
        )
        zoom_in = action(
            text=self.tr("Zoom &In"),
            slot=lambda _: self._add_zoom(increment=1.1, pos=None),
            shortcut=shortcuts["zoom_in"],
            icon="phosphor/magnifying-glass-plus.svg",
            tip=self.tr("Increase the zoom level"),
            enabled=False,
        )
        zoom_out = action(
            text=self.tr("Zoom &Out"),
            slot=lambda _: self._add_zoom(increment=0.9, pos=None),
            shortcut=shortcuts["zoom_out"],
            icon="phosphor/magnifying-glass-minus.svg",
            tip=self.tr("Decrease the zoom level"),
            enabled=False,
        )
        zoom_org = action(
            text=self.tr("&Actual Size"),
            slot=self._set_zoom_to_original,
            shortcut=shortcuts["zoom_to_original"],
            icon="phosphor/image-square.svg",
            tip=self.tr("Reset the zoom to 100%"),
            enabled=False,
        )
        reset_layout = action(
            text=self.tr("Reset Layout"),
            slot=self._reset_layout,
            icon="phosphor/layout-duotone.svg",
            tip=self.tr("Restore the default panel and toolbar layout"),
        )
        fill_drawing = action(
            text=self.tr("Fill Drawing Polygon"),
            icon="phosphor/paint-bucket.svg",
            tip=self.tr("Preview a filled polygon while drawing"),
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
            icon="phosphor/eye.svg",
            tip=self.tr("Hide every shape on the canvas"),
            enabled=False,
        )
        show_all = action(
            text=self.tr("&Show Shapes"),
            slot=functools.partial(self.toggle_shape_visibility, value=True),
            shortcut=shortcuts["show_all_shapes"],
            icon="phosphor/eye.svg",
            tip=self.tr("Show every shape on the canvas"),
            enabled=False,
        )
        toggle_all = action(
            text=self.tr("&Toggle Shapes"),
            slot=functools.partial(self.toggle_shape_visibility, value=None),
            shortcut=shortcuts["toggle_all_shapes"],
            icon="phosphor/eye.svg",
            tip=self.tr("Flip visibility for every shape"),
            enabled=False,
        )

        zoom_widget_action = QtWidgets.QWidgetAction(self)
        zoom_box_layout = QtWidgets.QVBoxLayout()
        zoom_label = QtWidgets.QLabel(self.tr("Zoom"))
        zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        zoom_label.setBuddy(self._canvas_widgets.zoom_widget)
        zoom_box_layout.addWidget(zoom_label)
        zoom_box_layout.addWidget(self._canvas_widgets.zoom_widget)
        zoom_widget_action.setDefaultWidget(QtWidgets.QWidget())
        zoom_widget_action.defaultWidget().setLayout(zoom_box_layout)
        self._canvas_widgets.zoom_widget.setToolTip(
            self.tr("Ctrl+Wheel zooms the canvas")
        )
        self._canvas_widgets.zoom_widget.setEnabled(False)

        self._zoom_mode = _ZoomMode.FIT_WINDOW
        fit_window.setChecked(True)

        self._canvas_widgets.canvas.vertex_selected.connect(remove_point.setEnabled)
        self._canvas_widgets.canvas.edge_selected.connect(add_point_to_edge.setEnabled)

        by_mode = dict(draw)
        zoom = (
            self._canvas_widgets.zoom_widget,
            zoom_in,
            zoom_out,
            zoom_org,
            fit_window,
            fit_width,
        )
        # Loading pixels unlocks every drawing tool plus image-only controls.
        on_load_active = (
            brightness_contrast,
            close,
            save_as,
            *(draw_action for _, draw_action in draw),
        )
        on_shapes_present = (hide_all, show_all, toggle_all)
        history = (undo, undo_last_point)
        clipboard = (copy, paste, duplicate)
        shape_edits = (edit, delete, add_point_to_edge, remove_point)
        # The right-click canvas menu leads with tool switching (it doubles as
        # a mode picker), then the platform-standard history/clipboard/edit
        # progression.
        context_menu = self._join_action_groups(
            (*(a for _, a in draw), edit_mode), history, clipboard, shape_edits
        )
        edit_menu = self._join_action_groups(
            history, clipboard, (edit, delete, remove_point), (keep_prev_action,)
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
            undo_last_point=undo_last_point,
            undo=undo,
            remove_point=remove_point,
            add_point_to_edge=add_point_to_edge,
            create_mode=by_mode["polygon"],
            edit_mode=edit_mode,
            create_rectangle_mode=by_mode["rectangle"],
            create_oriented_rectangle_mode=by_mode["oriented_rectangle"],
            create_circle_mode=by_mode["circle"],
            create_line_mode=by_mode["line"],
            create_point_mode=by_mode["point"],
            create_line_strip_mode=by_mode["linestrip"],
            create_ai_points_to_shape_mode=by_mode["ai_points_to_shape"],
            create_ai_box_to_shape_mode=by_mode["ai_box_to_shape"],
            open_next_img=open_next_img,
            open_prev_img=open_prev_img,
            keep_prev_zoom=keep_prev_zoom,
            fit_window=fit_window,
            fit_width=fit_width,
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
            zoom=zoom,
            on_load_active=on_load_active,
            on_shapes_present=on_shapes_present,
            context_menu=context_menu,
            edit_menu=edit_menu,
        )

    def _setup_menus(self) -> _Menus:
        action = functools.partial(_utils.new_action, self)

        quit_ = action(
            text=self.tr("&Quit"),
            slot=self.close,
            shortcut=self._config["shortcuts"]["quit"],
            icon=None,
            tip=self.tr("Close the application"),
        )
        settings_editable = self._is_settings_editable
        open_config = action(
            text=self.tr("Se&ttings…"),
            slot=self._open_settings,
            shortcut="Ctrl+," if platform.system() == "Darwin" else "Ctrl+Shift+,",
            icon=None,
            tip=(
                self.tr("Open the settings dialog")
                if settings_editable
                else self.tr(
                    "Settings are locked to the --config file for this session"
                )
            ),
            enabled=settings_editable,
        )
        open_config.setMenuRole(QtGui.QAction.MenuRole.PreferencesRole)
        tutorial = action(
            text=self.tr("&Tutorial"),
            slot=self.tutorial,
            icon="phosphor/question.svg",
            tip=self.tr("Open the tutorial in a browser"),
        )
        copy_here = action(text=self.tr("&Copy Here"), slot=self.copy_shape)
        move_here = action(text=self.tr("&Move Here"), slot=self.move_shape)

        file_menu = self.menuBar().addMenu(self.tr("&File"))
        edit_menu = self.menuBar().addMenu(self.tr("&Edit"))
        view_menu = self.menuBar().addMenu(self.tr("&View"))
        help_menu = self.menuBar().addMenu(self.tr("&Help"))

        actions = self._actions
        file_menu.addActions(
            self._join_action_groups(
                (
                    actions.open,
                    actions.open_dir,
                    actions.open_prev_img,
                    actions.open_next_img,
                ),
                (
                    actions.save,
                    actions.save_as,
                    actions.save_auto,
                    actions.save_with_image_data,
                    actions.change_output_dir,
                ),
                (actions.close, actions.delete_file),
                (open_config,),
                (quit_,),
            )
        )
        # Zoom controls lead, since they are reached for the most; shape
        # visibility and canvas preferences follow, and dock/layout toggles
        # sit at the bottom since they are set once and rarely revisited.
        view_menu.addActions(
            self._join_action_groups(
                (
                    actions.zoom_in,
                    actions.zoom_out,
                    actions.zoom_org,
                    actions.keep_prev_zoom,
                ),
                (actions.fit_window, actions.fit_width),
                (
                    actions.brightness_contrast,
                    actions.toggle_keep_prev_brightness_contrast,
                ),
                (actions.hide_all, actions.show_all, actions.toggle_all),
                (actions.fill_drawing,),
                (
                    self._docks.flag_dock.toggleViewAction(),
                    self._docks.label_dock.toggleViewAction(),
                    self._docks.shape_dock.toggleViewAction(),
                    self._docks.file_dock.toggleViewAction(),
                ),
                (actions.reset_layout,),
            )
        )
        help_menu.addActions((tutorial, actions.about))

        self._canvas_widgets.canvas.context_menus.without_selection.addActions(
            actions.context_menu
        )
        self._canvas_widgets.canvas.context_menus.with_selection.addActions(
            (copy_here, move_here)
        )

        label_menu = QtWidgets.QMenu()
        label_menu.addActions((actions.edit, actions.delete))
        self._docks.label_list.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self._docks.label_list.customContextMenuRequested.connect(
            self.show_label_list_menu
        )

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
                title="Tools",
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
                    self._actions.fit_window,
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
                title="CreateShapeTools",
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
        self._reset_session_state()

        if self._config["file_search"]:
            self._docks.file_search.setText(self._config["file_search"])

        self._restore_window_state()

        if file_or_dir:
            self._load_from_file_or_dir(file_or_dir=file_or_dir)

    def _reset_session_state(self) -> None:
        self._image = QtGui.QImage()
        self._annotation = None
        self._label_file_path = None
        self._last_failed_auto_save_path = None
        self._image_path = None
        self._file_list_image_path = None
        self._loaded_image_paths = []
        self._prev_image_path = None
        self._viewport_states = {}
        self._brightness_contrast_values = {}

    def _restore_window_state(self) -> None:
        # This Qt-managed store holds only window geometry and dock layout,
        # kept separate from the user-facing Config.
        DEFAULT_SIZE: Final = QtCore.QSize(900, 500)
        DEFAULT_POSITION: Final = QtCore.QPoint(0, 0)
        # Bump this when the dock/toolbar layout changes, to reset window
        # state for users upgrading from an older version.
        CURRENT_SETTINGS_VERSION: Final[int] = 1

        self._default_state = self.saveState()
        self._window_state = QtCore.QSettings("labelme", "labelme")

        stored_version = self._window_state.value("settingsVersion", 0, type=int)
        if stored_version != CURRENT_SETTINGS_VERSION:
            self._reset_layout()
            self._window_state.setValue("settingsVersion", CURRENT_SETTINGS_VERSION)

        self.resize(
            cast(QtCore.QSize, self._window_state.value(WINDOW_SIZE_KEY, DEFAULT_SIZE))
        )
        self.move(
            cast(
                QtCore.QPoint,
                self._window_state.value(WINDOW_POSITION_KEY, DEFAULT_POSITION),
            )
        )
        self.restoreState(
            cast(
                QtCore.QByteArray,
                self._window_state.value(WINDOW_LAYOUT_KEY, QtCore.QByteArray()),
            )
        )

        is_reachable = any(
            screen.availableGeometry().intersects(self.frameGeometry())
            for screen in QtWidgets.QApplication.screens()
        )
        if is_reachable:
            return
        # The saved screen is no longer connected: land on the primary
        # screen instead of leaving the window off any visible display.
        primary_screen = QtWidgets.QApplication.primaryScreen()
        if primary_screen is not None:
            self.move(primary_screen.availableGeometry().topLeft())

    def _setup_status_bar(self) -> _StatusBarWidgets:
        message = QtWidgets.QLabel(self.tr("%s is ready.") % __appname__)
        stats = StatusStats()
        # Temporary QStatusBar messages replace ordinary widgets. These two
        # describe persistent canvas state, so keep them visible beside alerts.
        self.statusBar().addPermanentWidget(message)
        self.statusBar().addPermanentWidget(stats)
        self.statusBar().show()
        return _StatusBarWidgets(message=message, stats=stats)

    def _setup_canvas(self) -> _CanvasWidgets:
        canvas_config = self._config["canvas"]
        shape_config = self._config["shape"]

        canvas = Canvas(
            epsilon=self._config["epsilon"],
            double_click=canvas_config["double_click"],
            num_backups=canvas_config["num_backups"],
            crosshair=canvas_config["crosshair"],
            allow_out_of_bounds_points=canvas_config["allow_out_of_bounds_points"],
        )

        # The canvas only ever renders inside this scroll area, so the
        # central widget goes up before anything else touches the canvas.
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidget(canvas)
        scroll_area.setWidgetResizable(True)
        empty_state = EmptyStateWidget(
            on_open_image=self._open_file_with_dialog,
            on_open_directory=self._open_dir_with_dialog,
        )
        surface = QtWidgets.QStackedWidget()
        surface.addWidget(empty_state)
        surface.addWidget(scroll_area)
        surface.setCurrentWidget(empty_state)
        self.setCentralWidget(surface)
        scroll_bars = {
            Qt.Orientation.Horizontal: scroll_area.horizontalScrollBar(),
            Qt.Orientation.Vertical: scroll_area.verticalScrollBar(),
        }

        canvas.set_draft_palette(
            palette=Palette(
                line=QtGui.QColor(*shape_config["line_color"]),
                fill=QtGui.QColor(*shape_config["fill_color"]),
                select_line=QtGui.QColor(*shape_config["select_line_color"]),
                select_fill=QtGui.QColor(*shape_config["select_fill_color"]),
                vertex_fill=QtGui.QColor(*shape_config["vertex_fill_color"]),
                hvertex_fill=QtGui.QColor(*shape_config["hvertex_fill_color"]),
            )
        )
        canvas.set_point_size(point_size=shape_config["point_size"])
        canvas.set_show_labels(value=shape_config["show_labels"])
        canvas.set_ai_existing_shape_suppression(
            enabled=self._config["ai"]["suppress_existing_shape_matches"]
        )
        canvas.set_color_resolver(
            resolver=lambda label: self._get_rgb_by_label(
                label=label, unique_label_list=self._docks.unique_label_list
            )
        )

        # One pass over every plain signal->handler pairing; the two signals
        # below need special connection handling and stay out of the loop.
        plain_connections = (
            (canvas.zoom_request, self._zoom_requested),
            (canvas.mouse_moved, self._update_status_stats),
            (canvas.scroll_request, self._on_scroll_request),
            (canvas.pan_request, self._on_pan_request),
            (canvas.new_shape, self._on_new_shape),
            (
                canvas.inference_produced_no_shapes,
                self._on_inference_produced_no_shapes,
            ),
            (canvas.point_prompt_rejected, self._on_point_prompt_rejected),
            (canvas.shape_moved, self.mark_dirty),
            (canvas.selection_changed, self._on_shape_selection_changed),
            (canvas.drawing_polygon, self._on_drawing_polygon_changed),
        )
        for signal, slot in plain_connections:
            signal.connect(slot)

        canvas.status_updated.connect(
            lambda text: self._status_bar.message.setText(text)
        )
        canvas.degenerate_shape_rejected.connect(
            lambda: self.show_status_message(
                self.tr("Shape had no area; nothing created."), delay=5000
            )
        )
        # The preview path emits this from inside paintEvent (an active
        # QPainter); a queued connection defers the status-bar update until
        # after the paint cycle so it never mutates UI mid-paint.
        canvas.inference_failed.connect(
            self._on_inference_failed,
            Qt.ConnectionType.QueuedConnection,
        )

        return _CanvasWidgets(
            canvas=canvas,
            empty_state=empty_state,
            scroll_area=scroll_area,
            surface=surface,
            zoom_widget=ZoomWidget(),
            scroll_bars=scroll_bars,
        )

    def _setup_dock_widgets(self) -> _DockWidgets:
        flag_list = QtWidgets.QListWidget()
        flag_list.setAccessibleName(self.tr("Flags"))
        flag = QtWidgets.QDockWidget(self.tr("Flags"), self)
        flag.setObjectName("Flags")
        if self._config["flags"]:
            self._load_flags(
                flags={k: False for k in self._config["flags"]},
                widget=flag_list,
            )
        flag.setWidget(flag_list)
        flag_list.itemChanged.connect(self.mark_dirty)

        label_list = LabelListWidget()
        label_list.setAccessibleName(self.tr("Shape List"))
        label_list.item_selection_changed.connect(self._label_selection_changed)
        label_list.item_double_clicked.connect(self._edit_label)
        label_list.item_changed.connect(self._on_label_item_changed)
        label_list.item_dropped.connect(self._on_label_order_changed)
        shape = QtWidgets.QDockWidget(self.tr("Shape List"), self)
        shape.setObjectName("Labels")
        shape.setWidget(label_list)

        unique_label_list = UniqueLabelQListWidget()
        unique_label_list.setAccessibleName(self.tr("Label List"))
        unique_label_list.setToolTip(
            self.tr("Select label to start annotating for it. Press 'Esc' to deselect.")
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

        file_search = QtWidgets.QLineEdit()
        file_search.setAccessibleName(self.tr("Search Filename"))
        file_search.setPlaceholderText(self.tr("Search Filename"))
        file_search.textChanged.connect(self._on_file_search_changed)
        file_list = QtWidgets.QListWidget()
        file_list.setAccessibleName(self.tr("File List"))
        file_list.currentItemChanged.connect(self._load_selected_image)
        file_list_layout = QtWidgets.QVBoxLayout()
        file_list_layout.setContentsMargins(0, 0, 0, 0)
        file_list_layout.setSpacing(0)
        file_list_layout.addWidget(file_search)
        file_list_layout.addWidget(file_list)
        file = QtWidgets.QDockWidget(self.tr("File List"), self)
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
            file_search=file_search,
            file_list=file_list,
        )

    def _load_config(
        self, *, config_file: Path | None, config_overrides: dict | None
    ) -> tuple[Path | None, dict]:
        try:
            config = _config.load_config(
                config_file=config_file, config_overrides=config_overrides or {}
            )
        except Exception as e:
            logger.warning("Failed to load config: {}", e)
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Icon.Warning)
            msg_box.setWindowTitle(self.tr("Configuration Errors"))
            msg_box.setText(
                self.tr(
                    "Errors were found while loading the configuration. "
                    "Please review the errors below and reload your configuration or "
                    "ignore the erroneous lines."
                )
            )
            msg_box.setInformativeText(str(e))
            msg_box.setStandardButtons(QMessageBox.StandardButton.Ignore)
            msg_box.setModal(False)
            msg_box.show()

            config_file = None
            config_overrides = {}
            config = _config.load_config(
                config_file=config_file, config_overrides=config_overrides
            )
        return config_file, config

    def has_no_shapes(self) -> bool:
        return not len(self._docks.label_list)

    def _sync_shapes_present_actions(self) -> None:
        enabled = not self.has_no_shapes()
        for action in self._actions.on_shapes_present:
            action.setEnabled(enabled)

    def _sync_paste_action(self) -> None:
        self._actions.paste.setEnabled(
            self._image_path is not None and self._shape_clipboard.has_shapes()
        )

    def populate_mode_actions(self) -> None:
        without_selection = self._canvas_widgets.canvas.context_menus.without_selection
        without_selection.clear()
        without_selection.addActions(self._actions.context_menu)

        self._menus.edit.clear()
        mode_switch_group = (
            *(draw_action for _, draw_action in self._actions.draw),
            self._actions.edit_mode,
        )
        self._menus.edit.addActions(
            self._join_action_groups(mode_switch_group, self._actions.edit_menu)
        )

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
        self._actions.undo.setEnabled(self._canvas_widgets.canvas.can_restore_shape)

        if self._actions.save_auto.isChecked():
            assert self._image_path is not None
            label_path = (
                self.current_label_file_path()
                if self._output_dir is None
                else _resolve_label_path(
                    image_or_label_path=self._image_path,
                    output_dir=self._output_dir,
                )
            )
            if self.save_labels(
                label_path=label_path,
                show_error=self._last_failed_auto_save_path != label_path,
            ):
                self.mark_clean()
                return
            self._last_failed_auto_save_path = label_path
        self._is_changed = True
        self._actions.save.setEnabled(True)
        self.setWindowTitle(self._get_window_title(dirty=True))

    def mark_clean(self) -> None:
        canvas = self._canvas_widgets.canvas
        self._actions.undo.setEnabled(
            not canvas.is_drawing and canvas.can_restore_shape
        )
        self._is_changed = False
        self._actions.save.setEnabled(False)
        self.setWindowTitle(self._get_window_title(dirty=False))

    def _reset_label_file_actions(self) -> None:
        # The draw half is a reset, not a re-derivation: a label file
        # transition returns the UI to the neutral edit-mode state, where every
        # draw action is available. Narrowing them again is _switch_canvas_mode.
        for _, action in self._actions.draw:
            action.setEnabled(True)
        self._actions.delete_file.setEnabled(self.has_label_file())

    def update_action_states(self, *, value: bool = True) -> None:
        for action in (*self._actions.zoom, *self._actions.on_load_active):
            action.setEnabled(value)
        self._sync_paste_action()

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

        texts = [
            text.strip()
            for text in self._ai_text.get_text_prompt().split(",")
            if text.strip()
        ]
        if not texts:
            self.show_status_message(
                self.tr("Enter at least one label before running AI."), delay=5000
            )
            return

        model_name: str = self._ai_text.get_model_name()
        model_type = osam.apis.get_model_type_by_name(model_name)
        if model_type.get_size() is None:
            if not download_ai_model(model_name=model_name, parent=self):
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
                    "'%s' annotations.\n\n"
                    "Switch the AI Text-to-Annotation model to 'SAM3 (smart)', "
                    "or set the output format to 'Rectangle'."
                )
                % (self._ai_text.get_model_display_name(), shape_type),
            )
            return
        except Exception as e:
            logger.opt(exception=e).error("AI text inference failed")
            self._on_inference_failed(f"{type(e).__name__}: {e}")
            return

        self._load_shapes(shapes, replace=False)
        self.mark_dirty()

    def reset_state(self) -> None:
        self._switch_canvas_mode(edit=True, create_mode=None)
        self._docks.label_list.clear()
        self._docks.flag_list.clear()
        self._annotation = None
        self._image = QtGui.QImage()
        self._image_path = None
        self._file_list_image_path = None
        self._label_file_path = None
        self._last_failed_auto_save_path = None
        self._canvas_widgets.canvas.reset_state()

    def undo_shape_edit(self) -> None:
        if not self._canvas_widgets.canvas.can_restore_shape:
            return
        self._canvas_widgets.canvas.restore_last_shape()
        self._docks.label_list.clear()
        self._load_shapes(self._canvas_widgets.canvas.shapes, replace=True)
        self.mark_dirty()

    def tutorial(self) -> None:
        url = "https://github.com/labelmeai/labelme/tree/main/examples/tutorial"  # NOQA
        webbrowser.open(url)

    def _on_drawing_polygon_changed(self, drawing: bool, /) -> None:  # noqa: FBT001 -- Canvas.drawing_polygon slot
        idle = not drawing
        self._actions.edit_mode.setEnabled(idle)
        self._actions.undo_last_point.setEnabled(drawing)
        self._actions.undo.setEnabled(
            idle and self._canvas_widgets.canvas.can_restore_shape
        )
        self._actions.delete.setEnabled(
            idle and bool(self._canvas_widgets.canvas.selected_shapes)
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
        self._set_point_prompt_mode(enabled=create_mode == "ai_points_to_shape")

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
        items = self._docks.label_list.selected_items()
        if not items:
            logger.warning("No label is selected, so cannot edit label.")
            return

        shapes = [cast(Shape, item.shape()) for item in items]
        first_shape = shapes[0]
        fields = typing.get_args(LabelDialogField)
        editable_fields = tuple(
            field
            for field in fields
            if all(
                getattr(shape, field) == getattr(first_shape, field)
                for shape in shapes[1:]
            )
        )
        locked = set(fields) - set(editable_fields)

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
            self._label_dialog.remember_label(
                label="" if "label" in locked else first_shape.label or ""
            )
            return

        if "label" in editable_fields and not self.validate_label(label=entry.label):
            self.show_error_message(
                title=self.tr("Label not allowed"),
                message=self.tr("'{}' does not match the '{}' label policy.").format(
                    entry.label, self._config["validate_label"]
                ),
            )
            return

        self._canvas_widgets.canvas.backup_shapes()
        for item in items:
            shape = item.shape()
            assert shape is not None
            for field in editable_fields:
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
            if self._docks.unique_label_list.find_label_item(label=shape.label) is None:
                self._docks.unique_label_list.add_label_item(
                    label=shape.label,
                    color=self._get_rgb_by_label(
                        label=shape.label,
                        unique_label_list=self._docks.unique_label_list,
                    ),
                )
        self.mark_dirty()

    def _on_file_search_changed(self) -> None:
        self._refresh_file_list()

    def _load_selected_image(
        self,
        current_item: QtWidgets.QListWidgetItem | None,
        previous_item: QtWidgets.QListWidgetItem | None,
        /,
    ) -> None:
        if current_item is None:
            return
        if not self._can_continue() or not self._load_file(
            image_or_label_path=current_item.text()
        ):
            self._restore_file_selection(item=previous_item)

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
        has_selection = bool(selected_shapes)
        # Selection-only commands follow selection state regardless of mode.
        for selection_action in (
            self._actions.edit,
            self._actions.copy,
            self._actions.duplicate,
            self._actions.delete,
        ):
            selection_action.setEnabled(has_selection)

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
        self._sync_shapes_present_actions()

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
        self._sync_shapes_present_actions()

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
        self._sync_shapes_present_actions()

    def _load_flags(
        self,
        *,
        flags: dict[str, bool],
        widget: QtWidgets.QListWidget,
    ) -> None:
        widget.clear()
        key: str
        flag: bool
        for key, flag in flags.items():
            item: QtWidgets.QListWidgetItem = QtWidgets.QListWidgetItem(key)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if flag else Qt.CheckState.Unchecked
            )
            widget.addItem(item)

    def save_labels(self, *, label_path: str, show_error: bool = True) -> bool:
        label_path = os.path.normpath(label_path)
        try:
            assert self._image_path
            assert self._annotation is not None
            shapes = [
                _shape_to_dict(shape)
                for item in self._docks.label_list
                if (shape := item.shape()) is not None
            ]
            label_dir = Path(label_path).parent
            label_dir.mkdir(parents=True, exist_ok=True)
            annotation = Annotation(
                image_path=_resolve_stored_image_path(
                    image_path=self._image_path, label_dir=label_dir
                ),
                image_data=self._annotation.image_data,
                shapes=shapes,
                flags=self._read_flag_dock_states(),
                other_data=self._annotation.other_data,
            )
            write_label_file(
                filename=label_path,
                annotation=annotation,
                image_height=self._image.height(),
                image_width=self._image.width(),
                save_image_data=self._config["with_image_data"],
            )
            self._label_file_path = label_path
            self._actions.delete_file.setEnabled(True)
            image_list_path = self._file_list_image_path or self._image_path
            items = self._docks.file_list.findItems(
                image_list_path, Qt.MatchFlag.MatchExactly
            )
            for item in items:
                item.setCheckState(Qt.CheckState.Checked)
            self._last_failed_auto_save_path = None
            return True
        except (LabelFileError, OSError, TypeError, ValueError) as e:
            if show_error:
                self.show_error_message(
                    title=self.tr("Could not save the annotations"),
                    message=str(e),
                )
            return False

    def _insert_shapes(self, shapes: list[Shape], /) -> None:
        if not shapes:
            return
        self._load_shapes(shapes, replace=False)
        self._canvas_widgets.canvas.select_shapes(shapes=shapes)
        self.mark_dirty()

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
        self.mark_dirty()
        shapes = [
            s for item in self._docks.label_list if (s := item.shape()) is not None
        ]
        self._canvas_widgets.canvas.load_shapes(shapes=shapes)

    def _on_new_shape(self) -> None:
        items = self._docks.unique_label_list.selectedItems()
        text = items[0].data(Qt.ItemDataRole.UserRole) if items else None
        show_popup = not text
        if self._config["display_label_popup"]:
            show_popup = True

        if show_popup:
            entry = self._label_dialog.popup(text=text)
        else:
            assert text is not None
            entry = LabelDialogEntry(
                label=text, flags={}, group_id=None, description=""
            )

        if entry is not None and not self.validate_label(label=entry.label):
            self.show_error_message(
                title=self.tr("Invalid label"),
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
        for shape in shapes:
            if entry.group_id is not None or shape.group_id is None:
                shape.group_id = entry.group_id
            shape.description = entry.description
            self.add_label(shape=shape)
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

    def _on_point_prompt_rejected(self, model_name: str, /) -> None:
        option = _ai_models.find_ai_assist_model_option(model_name=model_name)
        assert option is not None
        QtWidgets.QMessageBox.warning(
            self,
            self.tr("AI-Points Unavailable"),
            self.tr(
                "%s does not support point prompts.\n"
                "Please select a different model or use AI-Box mode."
            )
            % option.display_name,
        )

    def _on_scroll_request(self, delta: int, orientation: Qt.Orientation, /) -> None:
        bar = self._canvas_widgets.scroll_bars[orientation]
        target_value = _natural_scroll_target(
            current=bar.value(), single_step=bar.singleStep(), delta=delta
        )
        self.set_scroll_value(orientation=orientation, value=target_value)

    def _on_pan_request(self, step: QtCore.QPoint, /) -> None:
        # Pan moves the viewport opposite to the cursor delta so the image
        # tracks the grabbed point one-for-one in widget pixels.
        self._move_canvas_view(step=QtCore.QPointF(step), constrain_to_center=True)

    def _move_canvas_view(
        self, *, step: QtCore.QPointF, constrain_to_center: bool
    ) -> None:
        requested_by_axis = (
            (Qt.Orientation.Horizontal, step.x()),
            (Qt.Orientation.Vertical, step.y()),
        )
        applied_by_axis: dict[Qt.Orientation, float] = {}
        for orientation, requested_delta in requested_by_axis:
            bar = self._canvas_widgets.scroll_bars[orientation]
            value_before = bar.value()
            self.set_scroll_value(
                orientation=orientation, value=value_before - requested_delta
            )
            # Scrollbars take the movement they can; whatever they clamped
            # away is carried by the render offset below instead of being
            # lost, so the canvas geometry never has to change to compensate.
            applied_by_axis[orientation] = requested_delta + (
                bar.value() - value_before
            )
        self._canvas_widgets.canvas.pan_view(
            step=QtCore.QPointF(
                applied_by_axis[Qt.Orientation.Horizontal],
                applied_by_axis[Qt.Orientation.Vertical],
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
        scroll_area = self._canvas_widgets.scroll_area
        viewport = scroll_area.viewport()
        image_pos = canvas.transform_widget_point_to_image(pos)
        viewport_pos = canvas.mapTo(viewport, pos)

        self._sync_zoom_mode_actions()
        # Setting the value fires valueChanged, which rescales the canvas.
        self._canvas_widgets.zoom_widget.setValue(value)

        target = canvas.transform_image_point_to_widget(
            image_pos, area=canvas.sizeHint()
        )
        current = canvas.mapFrom(viewport, viewport_pos)
        shift = target - current
        self._move_canvas_view(step=-shift, constrain_to_center=False)

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

    def set_fit_width_mode(self, value: bool = True, /) -> None:  # noqa: FBT001, FBT002 -- QAction.triggered slot
        target = _ZoomMode.FIT_WIDTH if value else _ZoomMode.MANUAL_ZOOM
        self._switch_zoom_mode(target)

    def _switch_zoom_mode(self, mode: _ZoomMode, /) -> None:
        self._zoom_mode = mode
        self._adjust_scale()

    def _sync_zoom_mode_actions(self) -> None:
        self._actions.fit_window.setChecked(self._zoom_mode == _ZoomMode.FIT_WINDOW)
        self._actions.fit_width.setChecked(self._zoom_mode == _ZoomMode.FIT_WIDTH)

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
        label_list = self._docks.label_list
        for index in range(len(label_list)):
            item = label_list[index]
            target = (
                item.checkState() == Qt.CheckState.Unchecked if value is None else value
            )
            item.setCheckState(
                Qt.CheckState.Checked if target else Qt.CheckState.Unchecked
            )

    def _restore_file_selection(
        self, *, item: QtWidgets.QListWidgetItem | None
    ) -> None:
        with QtCore.QSignalBlocker(self._docks.file_list):
            if item is None:
                self._docks.file_list.setCurrentRow(-1)
            else:
                self._docks.file_list.setCurrentItem(item)
        self._docks.file_list.repaint()
        self.setWindowTitle(self._get_window_title(dirty=self._is_changed))

    def _stage_file_session(self, *, requested_path: str) -> _FileSession | None:
        if not QtCore.QFile.exists(requested_path):
            self.show_error_message(
                title=self.tr("Cannot open file"),
                message=self.tr("The path does not exist:\n%s") % requested_path,
            )
            self.show_status_message(
                self.tr("Failed to load %s") % Path(requested_path).name
            )
            return None
        label_path: str = _resolve_label_path(
            image_or_label_path=requested_path,
            output_dir=self._output_dir,
        )
        has_label_file = QtCore.QFile.exists(label_path)
        try:
            if has_label_file:
                annotation = read_label_file(filename=label_path)
                image_path = os.path.normpath(
                    str(Path(label_path).parent / annotation.image_path)
                )
                shapes = _shapes_from_dicts(
                    shape_dicts=annotation.shapes,
                    label_flags=self._config["label_flags"],
                )
            else:
                image_path = requested_path
                annotation = Annotation(
                    image_path=os.path.basename(image_path),
                    image_data=read_image_file(filename=image_path),
                    shapes=[],
                    flags={},
                    other_data={},
                )
                shapes = []
        except (LabelFileError, OSError, TypeError, ValueError) as e:
            self._show_file_open_error(
                path=label_path if has_label_file else requested_path,
                file_kind="label" if has_label_file else "image",
                exc=e,
                extra=None,
            )
            return None

        started_at = time.time()
        image = QtGui.QImage.fromData(annotation.image_data)
        logger.debug("Decoded image in {:.0f}ms", (time.time() - started_at) * 1000)
        if image.isNull():
            detail = _make_image_too_large_message(image_data=annotation.image_data)
            if detail is None:
                patterns = ", ".join(
                    f"*.{fmt.toStdString()}"
                    for fmt in QtGui.QImageReader.supportedImageFormats()
                )
                detail = self.tr("Supported files: {patterns}").format(
                    patterns=patterns
                )
            self._show_file_open_error(
                path=requested_path,
                file_kind="image",
                exc=None,
                extra=detail,
            )
            return None

        return _FileSession(
            image_path=image_path,
            file_list_image_path=(
                None if is_label_file_path(filename=requested_path) else requested_path
            ),
            label_file_path=label_path if has_label_file else None,
            annotation=annotation,
            image=image,
            shapes=shapes,
        )

    def _install_file_session(self, *, session: _FileSession) -> None:
        canvas = self._canvas_widgets.canvas
        should_carry_shapes = (
            not session.shapes
            and bool(canvas.shapes)
            and (
                self._config["keep_prev"]
                or QtWidgets.QApplication.keyboardModifiers()
                == (
                    Qt.KeyboardModifier.ControlModifier
                    | Qt.KeyboardModifier.ShiftModifier
                )
            )
        )
        shapes = canvas.shapes[:] if should_carry_shapes else session.shapes

        self._remember_current_viewport()
        is_first_session = not self._viewport_states
        self.reset_state()
        canvas.setEnabled(False)
        self._annotation = session.annotation
        self._image_path = session.image_path
        self._file_list_image_path = session.file_list_image_path
        self._label_file_path = session.label_file_path
        self._image = session.image
        started_at = time.time()
        canvas.load_pixmap(pixmap=QtGui.QPixmap.fromImage(session.image))
        self._canvas_widgets.surface.setCurrentWidget(self._canvas_widgets.scroll_area)
        logger.debug("Prepared canvas in {:.0f}ms", (time.time() - started_at) * 1000)

        flags = dict.fromkeys(self._config["flags"] or [], False)
        flags.update(session.annotation.flags)
        self._load_shapes(shapes, replace=True)
        self._load_flags(flags=flags, widget=self._docks.flag_list)
        if should_carry_shapes:
            self.mark_dirty()
        else:
            self.mark_clean()
        self._reset_label_file_actions()
        canvas.setEnabled(True)

        viewport = self._viewport_states.get(session.image_path)
        if self._config["keep_prev_scale"] and self._prev_image_path is not None:
            viewport = self._viewport_states.get(self._prev_image_path)
        if viewport is not None:
            self._zoom_mode = viewport.zoom_mode
            if self._zoom_mode == _ZoomMode.MANUAL_ZOOM:
                self._set_zoom(value=viewport.zoom_value, pos=None)
            else:
                self._adjust_scale()
        elif is_first_session or not self._config["keep_prev_scale"]:
            self._zoom_mode = _ZoomMode.FIT_WINDOW
            self._adjust_scale()
        self._apply_zoom_to_canvas()
        if viewport is not None:
            for orientation, value in viewport.scroll_values.items():
                self.set_scroll_value(orientation=orientation, value=value)
            canvas.reset_view_offset()
            canvas.pan_view(step=viewport.view_offset, constrain_to_center=False)
        self.open_brightness_contrast_dialog(
            False,  # noqa: FBT003 -- placeholder for the Qt triggered flag
            is_initial_load=True,
        )
        self.update_action_states(value=True)
        if not self._docks.file_list.hasFocus():
            canvas.setFocus()

    def _load_file(self, *, image_or_label_path: str) -> bool:
        requested_path = os.path.normpath(image_or_label_path)
        self.show_status_message(self.tr("Reading %s…") % Path(requested_path).name)
        started_at = time.time()
        session = self._stage_file_session(requested_path=requested_path)
        if session is None:
            return False

        self._install_file_session(session=session)
        self.show_status_message(
            self.tr("Loaded and ready: %s") % Path(requested_path).name
        )
        logger.info(
            "Opened {!r} in {:.0f}ms", requested_path, (time.time() - started_at) * 1000
        )
        return True

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent, /) -> bool:
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
        if self._zoom_mode == _ZoomMode.FIT_WINDOW:
            scale = self._fit_window_scale()
        elif self._zoom_mode == _ZoomMode.FIT_WIDTH:
            scale = self._fit_width_scale()
        else:
            scale = 1.0
        self._set_zoom(value=scale * 100, pos=None)

    def _fit_window_scale(self) -> float:
        FIT_WINDOW_SCROLLBAR_MARGIN: Final[float] = 2.0
        viewport = self._canvas_widgets.scroll_area
        pixmap = self._canvas_widgets.canvas.pixmap
        available_w = viewport.width() - FIT_WINDOW_SCROLLBAR_MARGIN
        available_h = viewport.height() - FIT_WINDOW_SCROLLBAR_MARGIN
        scale_by_width = available_w / pixmap.width()
        scale_by_height = available_h / pixmap.height()
        return min(scale_by_width, scale_by_height)

    def _fit_width_scale(self) -> float:
        scroll_area = self._canvas_widgets.scroll_area
        viewport_size = scroll_area.maximumViewportSize()
        pixmap = self._canvas_widgets.canvas.pixmap
        precision = 10 ** self._canvas_widgets.zoom_widget.decimals()
        available_w = viewport_size.width()
        scale_percent = available_w / pixmap.width() * 100
        # The zoom control rounds on assignment; fitting must never round up
        # far enough to create horizontal overflow.
        scale_percent = math.floor(scale_percent * precision) / precision
        if int(pixmap.height() * scale_percent / 100) > viewport_size.height():
            available_w -= scroll_area.verticalScrollBar().sizeHint().width()
            scale_percent = available_w / pixmap.width() * 100
            scale_percent = math.floor(scale_percent * precision) / precision
        return scale_percent / 100

    def _reset_layout(self) -> None:
        self._window_state.remove(WINDOW_LAYOUT_KEY)
        self.restoreState(self._default_state)

    def closeEvent(self, a0: QtGui.QCloseEvent, /) -> None:
        if not self._can_continue():
            a0.ignore()
            return
        self._persist_window_state()

    def _persist_window_state(self) -> None:
        # Only reached once the close is accepted: a cancelled close must
        # leave whatever was persisted at the previous accepted close intact.
        values_by_key = {
            WINDOW_SIZE_KEY: self.size(),
            WINDOW_POSITION_KEY: self.pos(),
            WINDOW_LAYOUT_KEY: self.saveState(),
        }
        for key, value in values_by_key.items():
            self._window_state.setValue(key, value)

    def dragEnterEvent(self, a0: QtGui.QDragEnterEvent, /) -> None:
        a0.ignore()
        if _extract_dropped_image_paths(mime=a0.mimeData()):
            a0.acceptProposedAction()

    def dropEvent(self, a0: QtGui.QDropEvent, /) -> None:
        a0.ignore()
        image_files = _extract_dropped_image_paths(mime=a0.mimeData())
        if not image_files or not self._can_continue():
            return
        self.import_dropped_image_files(image_files=image_files)
        a0.acceptProposedAction()

    def _open_prev_image(self) -> None:
        row_prev: int = self._docks.file_list.currentRow() - 1
        if row_prev < 0:
            logger.debug("there is no prev image")
            return

        logger.debug("setting current row to {:d}", row_prev)
        self._docks.file_list.setCurrentRow(row_prev)
        self._docks.file_list.repaint()

    def _open_next_image(self) -> None:
        row_next: int = self._docks.file_list.currentRow() + 1
        if row_next >= self._docks.file_list.count():
            logger.debug("there is no next image")
            return

        logger.debug("setting current row to {:d}", row_next)
        self._docks.file_list.setCurrentRow(row_next)
        self._docks.file_list.repaint()

    def _open_file_with_dialog(self) -> None:
        if not self._can_continue():
            return
        formats = [
            f"*.{fmt.toStdString()}"
            for fmt in QtGui.QImageReader.supportedImageFormats()
        ]
        filters = self.tr("&Images and annotations (%s)") % " ".join(
            formats + [f"*{LABEL_FILE_SUFFIX}"]
        )
        image_or_label_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            self.tr("%s — Select an image or annotation") % __appname__,
            self.current_path(),
            filters,
        )
        if image_or_label_path:
            self._load_from_file_or_dir(file_or_dir=image_or_label_path)

    def prompt_output_dir(self, _value: bool = False, /) -> None:  # noqa: FBT001, FBT002 -- QAction.triggered slot
        default_output_dir: str
        if self._output_dir is not None:
            default_output_dir = str(self._output_dir)
        elif self._image_path:
            default_output_dir = str(Path(self._image_path).parent)
        else:
            default_output_dir = self.current_path()

        output_dir = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            self.tr("%s — Select the annotation folder") % __appname__,
            default_output_dir,
            QtWidgets.QFileDialog.Option.ShowDirsOnly
            | QtWidgets.QFileDialog.Option.DontResolveSymlinks,
        )
        output_dir = str(output_dir)

        if not output_dir:
            return

        if not self._can_continue():
            return

        # Reload the current image against the candidate directory and keep
        # the previous directory when that reload fails, so a bad candidate
        # never becomes the autosave target.
        previous_output_dir = self._output_dir
        self._output_dir = Path(output_dir)
        if self._file_list_image_path is not None and not self._load_file(
            image_or_label_path=self._file_list_image_path
        ):
            self._output_dir = previous_output_dir
            return

        self.show_status_message(
            self.tr("%s to %s") % ("Changed annotation folder", self._output_dir),
            delay=5000,
        )

        self._refresh_file_list()

    def _save_label_file(self, *, save_as: bool) -> None:
        assert not self._image.isNull(), "cannot save empty image"

        label_path: str | None = None
        if not save_as and self._label_file_path is not None:
            label_path = self._label_file_path
        if label_path is None:
            label_path = self.prompt_save_file_path()

        if not label_path:
            logger.warning("label_path={!r} is empty, so cannot save", label_path)
            return

        if self.save_labels(label_path=label_path):
            self.mark_clean()
            self._reset_label_file_actions()

    def prompt_save_file_path(self) -> str:
        assert self._image_path is not None
        label_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            parent=self,
            caption=self.tr("Save annotations as"),
            dir=_resolve_label_path(
                image_or_label_path=self._image_path,
                output_dir=self._output_dir,
            ),
            filter=self.tr("Label files (*%s)") % LABEL_FILE_SUFFIX,
        )
        if label_path and not is_label_file_path(filename=label_path):
            label_path += LABEL_FILE_SUFFIX
        return label_path

    def close_file(self, _value: bool = False, /) -> None:  # noqa: FBT001, FBT002 -- QAction.triggered slot
        if not self._can_continue():
            return
        self._remember_current_viewport()
        self.reset_state()
        self._docks.file_list.setCurrentRow(-1)
        self.mark_clean()
        self._reset_label_file_actions()
        self.update_action_states(value=False)
        self._canvas_widgets.canvas.setEnabled(False)
        self._canvas_widgets.surface.setCurrentWidget(self._canvas_widgets.empty_state)
        self._docks.file_list.setFocus()
        self._actions.save_as.setEnabled(False)

    def current_label_file_path(self) -> str:
        assert self._image_path is not None
        if self._label_file_path is not None:
            return self._label_file_path
        return _resolve_label_path(
            image_or_label_path=self._image_path, output_dir=self._output_dir
        )

    def _confirm_deletion(self, *, message: str) -> bool:
        msg_box = QtWidgets.QMessageBox(self)
        msg_box.setIcon(QtWidgets.QMessageBox.Icon.Warning)
        msg_box.setWindowTitle(self.tr("Confirm Deletion"))
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
        annotation_path = Path(self.current_label_file_path())
        msg = self.tr("Delete this annotation file permanently?")
        if not self._confirm_deletion(message=msg):
            return

        try:
            annotation_path.unlink()
        except FileNotFoundError:
            pass
        except OSError as e:
            logger.warning(
                "Could not delete annotation file '{}': {}", annotation_path, e
            )
            self.show_error_message(
                title=self.tr("Delete failed"),
                message=self.tr(
                    "Could not delete annotation file:\n{path}\n\n{error}"
                ).format(
                    path=annotation_path,
                    error=e,
                ),
            )
            return
        else:
            logger.info("Deleted annotation file: {}", annotation_path)

        item = self._docks.file_list.currentItem()
        if item:
            item.setCheckState(Qt.CheckState.Unchecked)

        self._docks.label_list.clear()
        self._load_flags(
            flags=dict.fromkeys(self._config["flags"] or [], False),
            widget=self._docks.flag_list,
        )
        self._canvas_widgets.canvas.shape_backups.clear()
        self._canvas_widgets.canvas.load_shapes(shapes=[], replace=True)
        self._sync_shapes_present_actions()
        self._actions.undo.setEnabled(self._canvas_widgets.canvas.can_restore_shape)
        self.mark_clean()
        self._reset_label_file_actions()

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

    def _set_point_prompt_mode(self, *, enabled: bool) -> None:
        self._ai_annotation.set_point_prompt_mode(enabled=enabled)
        if self._settings_dialog is None:
            return
        disabled_reason = self.tr(
            "Unavailable in AI-Points mode because this model does not support "
            "point prompts."
        )
        for option in _ai_models.AI_ASSIST_MODEL_OPTIONS:
            self._settings_dialog.set_choice_enabled(
                key_path=("ai", "default"),
                value=option.display_name,
                enabled=not enabled or option.supports_point_prompts,
                disabled_reason=disabled_reason,
            )

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
        elif key_path[0] == "flags":
            # The flag dock otherwise only repopulates on the next image load.
            # Refresh it now additively: add newly predefined flags (unchecked) and
            # keep every flag already in the dock with its checked state. Like the
            # label docks, a flag removed from the config lingers until the next
            # image load, so the edit never drops a flag the current image carries.
            current = self._read_flag_dock_states()
            flags = {key: False for key in self._config["flags"] or []}
            flags.update(current)
            self._load_flags(flags=flags, widget=self._docks.flag_list)
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
                model_display=self._config["ai"]["default"]
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

    def _open_settings(self) -> None:
        if not self._is_settings_editable:
            return
        # Keep a single dialog instance; it edits self._config by reference, so
        # reopening it shows the current values without rebuilding.
        if self._settings_dialog is None:
            self._settings_dialog = SettingsDialog(
                config=self._config,
                apply_setting=self._apply_setting_change,
                preview_shape_color=self._preview_shape_color,
                open_as_text=self._open_config_file,
                parent=self,
            )
        self._set_point_prompt_mode(enabled=self._ai_annotation.is_point_prompt_mode)
        self._settings_dialog.show()
        self._settings_dialog.raise_()
        self._settings_dialog.activateWindow()

    def _open_config_file(self) -> None:
        # Only reachable from the Settings dialog, which opens solely when the
        # config is an editable file (see _is_settings_editable).
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

        label_file = self.current_label_file_path()
        return Path(label_file).exists()

    def _can_continue(self) -> bool:
        if not self._is_changed:
            return True
        prompt_text = self.tr('Save annotations to "{}" before closing?').format(
            self._image_path
        )
        user_choice = QtWidgets.QMessageBox.question(
            self,
            self.tr("Save changes to the annotations?"),
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
        # The dialog's own title bar already carries the title, so the body
        # only needs the message, and as plain text rather than HTML.
        return QtWidgets.QMessageBox.critical(self, title, message)

    def _show_file_open_error(
        self,
        *,
        path: str,
        file_kind: Literal["label", "image"],
        exc: BaseException | None,
        extra: str | None,
    ) -> None:
        summary_by_kind = {
            "label": self.tr("Could not read annotation data from:\n{path}"),
            "image": self.tr("Could not decode the image at:\n{path}"),
        }
        message_parts = [summary_by_kind[file_kind].format(path=path)]
        if exc is not None:
            message_parts.append(str(exc))
        if extra:
            message_parts.append(extra)
        message = "\n\n".join(message_parts)
        self.show_error_message(title=self.tr("Open failed"), message=message)
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
        msg = self.tr("Delete {} shapes? You can restore them with Undo.").format(
            len(self._canvas_widgets.canvas.selected_shapes)
        )
        if not self._confirm_deletion(message=msg):
            return
        self.remove_labels(shapes=self._canvas_widgets.canvas.delete_selected())
        self.mark_dirty()

    def copy_shape(self) -> None:
        self._canvas_widgets.canvas.end_move(copy=True)
        for shape in self._canvas_widgets.canvas.selected_shapes:
            self.add_label(shape=shape)
        self._docks.label_list.clearSelection()
        self.mark_dirty()

    def move_shape(self) -> None:
        self._canvas_widgets.canvas.end_move(copy=False)
        self.mark_dirty()

    def _load_from_file_or_dir(self, *, file_or_dir: str) -> None:
        if not file_or_dir:
            raise ValueError("file_or_dir cannot be empty")
        file_or_dir = os.path.normpath(file_or_dir)

        if is_label_file_path(filename=file_or_dir):
            if not self._load_file(image_or_label_path=file_or_dir):
                return
            self._loaded_image_paths = []
            self._refresh_file_list()
            self._docks.file_dock.setEnabled(False)
            self._docks.file_dock.setToolTip(
                self.tr("File list is disabled when a label file is opened")
            )
        elif Path(file_or_dir).is_dir():
            self._import_images_from_dir(root_dir=file_or_dir)
            if self.image_list:
                file_list = self._docks.file_list
                previous_item = file_list.currentItem()
                with QtCore.QSignalBlocker(file_list):
                    file_list.setCurrentRow(0)
                self._load_selected_image(file_list.currentItem(), previous_item)
                file_list.repaint()
        else:
            if not self._load_file(image_or_label_path=file_or_dir):
                return
            self._import_images_from_dir(root_dir=str(Path(file_or_dir).parent))

    def _open_dir_with_dialog(self) -> None:
        if not self._can_continue():
            return

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
                self.tr("%s — Select an image folder") % __appname__,
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
            lst.append(item.text())
        return lst

    def import_dropped_image_files(self, *, image_files: list[str]) -> None:
        extensions = _list_supported_image_extensions()
        already_loaded = set(self._loaded_image_paths)
        new_files = [
            normalized_path
            for path in image_files
            if (normalized_path := os.path.normpath(path)) not in already_loaded
            and normalized_path.lower().endswith(extensions)
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

        root_dir = os.path.normpath(root_dir)
        self._prev_opened_dir = root_dir
        self._loaded_image_paths = _scan_image_files(root_dir=root_dir)
        self._refresh_file_list()

    def _refresh_file_list(self) -> None:
        image_paths = _filter_image_paths(
            image_paths=self._loaded_image_paths,
            pattern=self._docks.file_search.text(),
        )

        file_list = self._docks.file_list
        with QtCore.QSignalBlocker(file_list):
            file_list.clear()
            for image_path in image_paths:
                file_list.addItem(
                    _make_image_list_item(
                        image_path=image_path, output_dir=self._output_dir
                    )
                )
            if self._file_list_image_path in image_paths:
                file_list.setCurrentRow(image_paths.index(self._file_list_image_path))

        for action in (self._actions.open_next_img, self._actions.open_prev_img):
            action.setEnabled(bool(image_paths))

        self.setWindowTitle(self._get_window_title(dirty=self._is_changed))

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
    compiled_label_flags = compile_label_flags(label_flags=label_flags)

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

        default_flags: dict[str, bool] = {}
        if isinstance(shape.label, str):
            for pattern, keys in compiled_label_flags.items():
                if pattern.match(shape.label):
                    for key in keys:
                        default_flags[key] = False
        else:
            logger.warning("shape.label is not str: {}", shape.label)
        shape.flags = default_flags
        shape.flags.update(shape_dict["flags"])
        shape.other_data = shape_dict["other_data"]

        shapes.append(shape)
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


def _natural_scroll_target(*, current: float, single_step: float, delta: int) -> float:
    # Natural scrolling: the wheel delta pushes the bar the opposite way, by
    # a tenth of a single step for every delta unit.
    NATURAL_SCROLL_FRACTION: Final = 0.1
    return current - delta * single_step * NATURAL_SCROLL_FRACTION


def _format_window_title(
    *,
    image_path: str | None,
    file_index: int | None,
    file_count: int,
    dirty: bool,
) -> str:
    # Leads with the file being edited (rather than the app name) so the
    # most useful information wins when the title is truncated in a narrow
    # taskbar entry; the dirty marker is a leading bullet, not a trailing "*".
    if image_path:
        location = image_path
        if file_count and file_index is not None:
            location = f"{location} ({file_index + 1} of {file_count})"
        title = f"{location} — {__appname__}"
    else:
        title = __appname__
    return f"● {title}" if dirty else title


def _resolve_label_path(*, image_or_label_path: str, output_dir: Path | None) -> str:
    if is_label_file_path(filename=image_or_label_path):
        return image_or_label_path
    image_path = Path(image_or_label_path)
    parent = output_dir if output_dir is not None else image_path.parent
    return str(parent / f"{image_path.stem}{LABEL_FILE_SUFFIX}")


def _resolve_stored_image_path(*, image_path: str, label_dir: Path) -> str:
    try:
        return os.path.relpath(image_path, label_dir)
    except ValueError:
        # Windows drives have no relative path between them; an absolute path
        # costs portability but beats failing the save.
        return os.path.abspath(image_path)


def _make_image_list_item(
    *, image_path: str, output_dir: Path | None
) -> QtWidgets.QListWidgetItem:
    item = QtWidgets.QListWidgetItem(image_path)
    item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
    label_path = _resolve_label_path(
        image_or_label_path=image_path, output_dir=output_dir
    )
    has_label = QtCore.QFile.exists(label_path)
    item.setCheckState(Qt.CheckState.Checked if has_label else Qt.CheckState.Unchecked)
    return item


def _shape_to_dict(shape: Shape, /) -> ShapeDict:
    assert shape.label is not None
    return ShapeDict(
        label=shape.label,
        points=shape.points.tolist(),
        shape_type=shape.shape_type,
        flags=shape.flags or {},
        description="" if shape.description is None else shape.description,
        group_id=shape.group_id,
        mask=shape.mask,
        other_data=shape.other_data,
    )


def _make_image_too_large_message(*, image_data: bytes) -> str | None:
    # None means the failure is not explained by image size, so the caller
    # falls back to the generic unsupported-format message.

    # Qt's raster paint engine cannot handle an image whose width or height
    # exceeds this, regardless of how high allocationLimit() is raised.
    RASTER_MAX_SIDE: Final = 32767

    buffer = QtCore.QBuffer()
    buffer.setData(image_data)
    buffer.open(QtCore.QIODevice.OpenModeFlag.ReadOnly)
    reader = QtGui.QImageReader(buffer)
    size = reader.size()
    if not size.isValid():
        return None
    width = size.width()
    height = size.height()

    if max(width, height) > RASTER_MAX_SIDE:
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

    limit_mb = QtGui.QImageReader.allocationLimit()
    if limit_mb <= 0:  # 0 disables the limit
        return None

    bits_per_pixel = QtGui.QImage.toPixelFormat(
        reader.imageFormat()  # ty: ignore[no-matching-overload]
    ).bitsPerPixel()
    if bits_per_pixel <= 0:  # unknown decode format: cannot estimate the need
        return None

    required_mb = width * height * bits_per_pixel / 8 / 1024 / 1024
    if required_mb <= limit_mb:
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
        required=math.ceil(required_mb),
        limit=limit_mb,
    )


def _list_supported_image_extensions() -> tuple[str, ...]:
    return tuple(
        f".{fmt.toStdString().lower()}"
        for fmt in QtGui.QImageReader.supportedImageFormats()
    )


def _filter_image_paths(*, image_paths: list[str], pattern: str) -> list[str]:
    if not pattern:
        return image_paths[:]
    try:
        regex = re.compile(pattern)
    except re.error:
        return image_paths[:]
    return [path for path in image_paths if regex.search(path)]


def _extract_dropped_image_paths(*, mime: QtCore.QMimeData) -> list[str]:
    extensions = _list_supported_image_extensions()
    # QUrl separates with forward slashes even on Windows, while the file
    # list holds the separator of the platform, so an unnormalized drop
    # would list an image the directory scan already listed a second time.
    local_paths = (os.path.normpath(url.toLocalFile()) for url in mime.urls())
    return [path for path in local_paths if path.lower().endswith(extensions)]


def _scan_image_files(*, root_dir: str) -> list[str]:
    extensions = _list_supported_image_extensions()
    root_dir = os.path.normpath(root_dir)

    images: list[str] = []
    for root, _dirs, files in os.walk(root_dir, followlinks=False):
        for file in files:
            if file.lower().endswith(extensions):
                relative_path = os.path.normpath(os.path.join(root, file))
                images.append(relative_path)

    logger.debug("found {:d} images in {!r}", len(images), root_dir)
    try:
        return natsort.os_sorted(images)
    except OSError:
        logger.warning(
            "natsort.os_sorted failed (known macOS strxfrm bug), "
            "falling back to locale-unaware natural sort"
        )
        return natsort.natsorted(images)
