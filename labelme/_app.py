from __future__ import annotations

import enum
import functools
import json
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

import imgviz
import natsort
import numpy as np
import osam
from loguru import logger
from numpy.typing import NDArray
from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from labelme import __appname__
from labelme import __version__

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
from ._shape import Shape
from ._shape import ShapeType
from ._shape_clipboard import ShapeClipboard
from ._widgets import AiAssistedAnnotationWidget
from ._widgets import AiTextToAnnotationWidget
from ._widgets import BrightnessContrastDialog
from ._widgets import Canvas
from ._widgets import LabelDialog
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

LABEL_COLORMAP: NDArray[np.uint8] = imgviz.label_colormap()


class _ZoomMode(enum.Enum):
    FIT_WINDOW = enum.auto()
    FIT_WIDTH = enum.auto()
    MANUAL_ZOOM = enum.auto()


_TextToAnnotationCreateMode: TypeAlias = Literal["polygon", "rectangle"]
_AI_CREATE_MODES: tuple[str, ...] = (
    "ai_points_to_shape",
    "ai_box_to_shape",
)
_AI_MODELS_WITHOUT_POINT_SUPPORT: tuple[str, ...] = ("sam3:latest",)


class _StatusBarWidgets(NamedTuple):
    message: QtWidgets.QLabel
    stats: StatusStats


class _CanvasWidgets(NamedTuple):
    canvas: Canvas
    zoom_widget: ZoomWidget
    scroll_bars: dict[Qt.Orientation, QtWidgets.QScrollBar]


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
    duplicate: QtGui.QAction
    copy: QtGui.QAction
    paste: QtGui.QAction
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
    edit_menu: tuple[QtGui.QAction | None, ...]


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
    _docks: _DockWidgets
    _actions: _Actions
    _menus: _Menus
    _label_dialog: LabelDialog
    _settings_dialog: SettingsDialog | None = None
    _ai_annotation: AiAssistedAnnotationWidget
    _ai_text: AiTextToAnnotationWidget

    _output_dir: Path | None
    _image: QtGui.QImage
    _annotation: Annotation | None
    _label_file_path: str | None
    _image_path: str | None
    _prev_image_path: str | None
    _zoom_values: dict[str, tuple[_ZoomMode, float]]
    _brightness_contrast_values: dict[str, tuple[int | None, int | None]]
    _scroll_values: dict[Qt.Orientation, dict[str, float]]
    _default_state: QtCore.QByteArray

    def __init__(
        self,
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

        self._shape_clipboard = ShapeClipboard(self)

        self._label_dialog = self._make_label_dialog()

        self._prev_opened_dir = None
        self._label_list_menu_origin: QtCore.QPoint | None = None
        self._docks = self._setup_dock_widgets()

        self.setAcceptDrops(True)
        self._canvas_widgets = self._setup_canvas()

        self._actions = self._setup_actions()
        self._shape_clipboard.availability_changed.connect(
            self._actions.paste.setEnabled
        )
        self._menus = self._setup_menus()

        self._ai_annotation = AiAssistedAnnotationWidget(
            default_model=self._config["ai"]["default"],
            on_model_changed=self._canvas_widgets.canvas.set_ai_model_name,
            on_output_format_changed=self._canvas_widgets.canvas.set_ai_output_format,
            parent=self,
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

        self._canvas_widgets.zoom_widget.valueChanged.connect(self._paint_canvas)

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
        save = action(
            text=self.tr("&Save\n"),
            slot=self._save_label_file,
            shortcut=shortcuts["save"],
            icon="phosphor/floppy-disk.svg",
            tip=self.tr("Save labels to file"),
            enabled=False,
        )
        save_as = action(
            text=self.tr("&Save As"),
            slot=lambda: self._save_label_file(save_as=True),
            shortcut=shortcuts["save_as"],
            icon="phosphor/floppy-disk.svg",
            tip=self.tr("Save labels to a different file"),
            enabled=False,
        )
        save_auto = action(
            text=self.tr("Save &Automatically"),
            tip=self.tr("Save automatically"),
            checkable=True,
            enabled=True,
        )
        save_auto.setChecked(self._config["auto_save"])
        save_with_image_data = action(
            text=self.tr("Save With Image Data"),
            slot=self.set_save_image_with_data,
            tip=self.tr("Save image data in label file"),
            checkable=True,
            checked=self._config["with_image_data"],
        )
        change_output_dir = action(
            text=self.tr("&Change Output Dir"),
            slot=self.prompt_output_dir,
            shortcut=shortcuts["save_to"],
            icon="phosphor/folders.svg",
            tip=self.tr("Change where annotations are loaded/saved"),
        )
        open_ = action(
            text=self.tr("&Open\n"),
            slot=self._open_file_with_dialog,
            shortcut=shortcuts["open"],
            icon="phosphor/folder-open.svg",
            tip=self.tr("Open image or label file"),
        )
        open_dir = action(
            text=self.tr("Open Dir"),
            slot=self._open_dir_with_dialog,
            shortcut=shortcuts["open_dir"],
            icon="phosphor/folder-open.svg",
            tip=self.tr("Open Dir"),
        )
        close = action(
            text=self.tr("&Close"),
            slot=self.close_file,
            shortcut=shortcuts["close"],
            icon="phosphor/x-circle.svg",
            tip=self.tr("Close current file"),
        )
        delete_file = action(
            text=self.tr("&Delete File"),
            slot=self.delete_file,
            shortcut=shortcuts["delete_file"],
            icon="phosphor/file-x.svg",
            tip=self.tr("Delete current label file"),
            enabled=False,
        )
        keep_prev_action = action(
            text=self.tr("Keep Previous Annotation"),
            slot=lambda: self._config.__setitem__(
                "keep_prev", not self._config["keep_prev"]
            ),
            shortcut=shortcuts["toggle_keep_prev_mode"],
            tip=self.tr('Toggle "keep previous annotation" mode'),
            checkable=True,
            checked=self._config["keep_prev"],
        )
        toggle_keep_prev_brightness_contrast = action(
            text=self.tr("Keep Previous Brightness/Contrast"),
            slot=lambda: self._config.__setitem__(
                "keep_prev_brightness_contrast",
                not self._config["keep_prev_brightness_contrast"],
            ),
            checkable=True,
            checked=self._config["keep_prev_brightness_contrast"],
        )
        delete = action(
            self.tr("Delete Shapes"),
            self.delete_selected_shapes,
            shortcuts["delete_shape"],
            icon="phosphor/trash.svg",
            tip=self.tr("Delete the selected shapes"),
            enabled=False,
        )
        edit = action(
            self.tr("&Edit Label"),
            self._edit_label,
            shortcuts["edit_label"],
            icon="phosphor/note-pencil.svg",
            tip=self.tr("Modify the label of the selected shape"),
            enabled=False,
        )
        duplicate = action(
            self.tr("Duplicate Shapes"),
            lambda: self._insert_shapes(
                [s.copy() for s in self._canvas_widgets.canvas.selected_shapes]
            ),
            shortcuts["duplicate_shape"],
            icon="phosphor/copy.svg",
            tip=self.tr("Create a duplicate of the selected shapes"),
            enabled=False,
        )
        copy = action(
            self.tr("Copy Shapes"),
            lambda: self._shape_clipboard.store(
                self._canvas_widgets.canvas.selected_shapes
            ),
            shortcuts["copy_shape"],
            "copy_clipboard",
            self.tr("Copy selected shapes to clipboard"),
            enabled=False,
        )
        paste = action(
            self.tr("Paste Shapes"),
            lambda: self._insert_shapes(self._shape_clipboard.paste()),
            shortcuts["paste_shape"],
            "paste",
            self.tr("Paste copied shapes"),
            enabled=False,
        )
        undo_last_point = action(
            self.tr("Undo last point"),
            self._canvas_widgets.canvas.undo_last_point,
            shortcuts["undo_last_point"],
            icon="phosphor/arrow-u-up-left.svg",
            tip=self.tr("Undo last drawn point"),
            enabled=False,
        )
        undo = action(
            self.tr("Undo\n"),
            self.undo_shape_edit,
            shortcuts["undo"],
            icon="phosphor/arrow-u-up-left.svg",
            tip=self.tr("Undo last add and edit of shape"),
            enabled=False,
        )
        remove_point = action(
            text=self.tr("Remove Selected Point"),
            slot=self.remove_selected_point,
            shortcut=shortcuts["remove_selected_point"],
            icon="phosphor/trash.svg",
            tip=self.tr("Remove selected point from polygon"),
            enabled=False,
        )
        add_point_to_edge = action(
            text=self.tr("Add Point to Edge"),
            slot=self._canvas_widgets.canvas.add_point_to_edge,
            tip=self.tr("Insert a new point at the hovered polygon edge"),
            enabled=False,
        )
        create_mode = action(
            text=self.tr("Polygon"),
            slot=lambda: self._switch_canvas_mode(edit=False, create_mode="polygon"),
            shortcut=shortcuts["create_polygon"],
            icon="phosphor/polygon.svg",
            tip=self.tr("Start drawing polygons"),
            enabled=False,
        )
        edit_mode = action(
            self.tr("Edit Shapes"),
            lambda: self._switch_canvas_mode(edit=True),
            shortcuts["edit_shape"],
            icon="phosphor/note-pencil.svg",
            tip=self.tr("Move and edit the selected shapes"),
            enabled=False,
        )
        create_rectangle_mode = action(
            text=self.tr("Rectangle"),
            slot=lambda: self._switch_canvas_mode(edit=False, create_mode="rectangle"),
            shortcut=shortcuts["create_rectangle"],
            icon="phosphor/rectangle.svg",
            tip=self.tr("Start drawing rectangles"),
            enabled=False,
        )
        create_oriented_rectangle_mode = action(
            text=self.tr("Oriented Rectangle"),
            slot=lambda: self._switch_canvas_mode(
                edit=False, create_mode="oriented_rectangle"
            ),
            shortcut=shortcuts["create_oriented_rectangle"],
            icon="oriented_rectangle.svg",
            tip=self.tr("Start drawing oriented rectangles"),
            enabled=False,
        )
        create_circle_mode = action(
            text=self.tr("Circle"),
            slot=lambda: self._switch_canvas_mode(edit=False, create_mode="circle"),
            shortcut=shortcuts["create_circle"],
            icon="phosphor/circle.svg",
            tip=self.tr("Start drawing circles"),
            enabled=False,
        )
        create_line_mode = action(
            text=self.tr("Line"),
            slot=lambda: self._switch_canvas_mode(edit=False, create_mode="line"),
            shortcut=shortcuts["create_line"],
            icon="phosphor/line-segment.svg",
            tip=self.tr("Start drawing lines"),
            enabled=False,
        )
        create_point_mode = action(
            text=self.tr("Point"),
            slot=lambda: self._switch_canvas_mode(edit=False, create_mode="point"),
            shortcut=shortcuts["create_point"],
            icon="phosphor/circles-four.svg",
            tip=self.tr("Start drawing points"),
            enabled=False,
        )
        create_line_strip_mode = action(
            text=self.tr("LineStrip"),
            slot=lambda: self._switch_canvas_mode(edit=False, create_mode="linestrip"),
            shortcut=shortcuts["create_linestrip"],
            icon="phosphor/line-segments.svg",
            tip=self.tr("Start drawing linestrip. Ctrl+LeftClick ends creation."),
            enabled=False,
        )
        create_ai_points_to_shape_mode = action(
            self.tr("AI-Points"),
            lambda: self._switch_canvas_mode(
                edit=False, create_mode="ai_points_to_shape"
            ),
            None,
            "ai-points.svg",
            self.tr("Click points to segment object. Ctrl+LeftClick ends creation."),
            enabled=False,
        )
        create_ai_box_to_shape_mode = action(
            self.tr("AI-Box"),
            lambda: self._switch_canvas_mode(edit=False, create_mode="ai_box_to_shape"),
            None,
            "ai-box.svg",
            self.tr("Draw a bounding box to segment object."),
            enabled=False,
        )
        open_next_img = action(
            text=self.tr("&Next Image"),
            slot=self._open_next_image,
            shortcut=shortcuts["open_next"],
            icon="phosphor/arrow-fat-right.svg",
            tip=self.tr("Open next (hold Ctl+Shift to copy labels)"),
            enabled=False,
        )
        open_prev_img = action(
            text=self.tr("&Prev Image"),
            slot=self._open_prev_image,
            shortcut=shortcuts["open_prev"],
            icon="phosphor/arrow-fat-left.svg",
            tip=self.tr("Open prev (hold Ctl+Shift to copy labels)"),
            enabled=False,
        )
        keep_prev_zoom = action(
            text=self.tr("&Keep Previous Zoom"),
            slot=lambda: self._config.__setitem__(
                "keep_prev_scale",
                not self._config["keep_prev_scale"],
            ),
            checkable=True,
            checked=self._config["keep_prev_scale"],
        )
        fit_window = action(
            self.tr("&Fit Window"),
            self.set_fit_window_mode,
            shortcuts["fit_window"],
            icon="phosphor/frame-corners.svg",
            tip=self.tr("Zoom follows window size"),
            checkable=True,
            enabled=False,
        )
        fit_width = action(
            self.tr("Fit &Width"),
            self.set_fit_width_mode,
            shortcuts["fit_width"],
            icon="frame-arrows-horizontal.svg",
            tip=self.tr("Zoom follows window width"),
            checkable=True,
            enabled=False,
        )
        brightness_contrast = action(
            self.tr("&Brightness Contrast"),
            self.open_brightness_contrast_dialog,
            None,
            "brightness-contrast.svg",
            self.tr("Adjust brightness and contrast"),
            enabled=False,
        )
        zoom_in = action(
            self.tr("Zoom &In"),
            lambda _: self._add_zoom(increment=1.1),
            shortcuts["zoom_in"],
            icon="phosphor/magnifying-glass-minus.svg",
            tip=self.tr("Increase zoom level"),
            enabled=False,
        )
        zoom_out = action(
            self.tr("&Zoom Out"),
            lambda _: self._add_zoom(increment=0.9),
            shortcuts["zoom_out"],
            icon="phosphor/magnifying-glass-plus.svg",
            tip=self.tr("Decrease zoom level"),
            enabled=False,
        )
        zoom_org = action(
            self.tr("&Original size"),
            self._set_zoom_to_original,
            shortcuts["zoom_to_original"],
            icon="phosphor/image-square.svg",
            tip=self.tr("Zoom to original size"),
            enabled=False,
        )
        reset_layout = action(
            text=self.tr("Reset Layout"),
            slot=self._reset_layout,
            icon="phosphor/layout-duotone.svg",
        )
        fill_drawing = action(
            self.tr("Fill Drawing Polygon"),
            self._canvas_widgets.canvas.set_fill_drawing,
            None,
            icon="phosphor/paint-bucket.svg",
            tip=self.tr("Fill polygon while drawing"),
            checkable=True,
            enabled=True,
        )
        if self._config["canvas"]["fill_drawing"]:
            fill_drawing.trigger()
        hide_all = action(
            self.tr("&Hide\nShapes"),
            functools.partial(self.toggle_shape_visibility, False),
            shortcuts["hide_all_shapes"],
            icon="phosphor/eye.svg",
            tip=self.tr("Hide all shapes"),
            enabled=False,
        )
        show_all = action(
            self.tr("&Show\nShapes"),
            functools.partial(self.toggle_shape_visibility, True),
            shortcuts["show_all_shapes"],
            icon="phosphor/eye.svg",
            tip=self.tr("Show all shapes"),
            enabled=False,
        )
        toggle_all = action(
            self.tr("&Toggle\nShapes"),
            functools.partial(self.toggle_shape_visibility, None),
            shortcuts["toggle_all_shapes"],
            icon="phosphor/eye.svg",
            tip=self.tr("Toggle all shapes"),
            enabled=False,
        )

        zoom_widget_action = QtWidgets.QWidgetAction(self)
        zoom_box_layout = QtWidgets.QVBoxLayout()
        zoom_label = QtWidgets.QLabel(self.tr("Zoom"))
        zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        zoom_box_layout.addWidget(zoom_label)
        zoom_box_layout.addWidget(self._canvas_widgets.zoom_widget)
        zoom_widget_action.setDefaultWidget(QtWidgets.QWidget())
        zoom_widget_action.defaultWidget().setLayout(zoom_box_layout)
        self._canvas_widgets.zoom_widget.setWhatsThis(
            str(
                self.tr(
                    "Zoom the image in or out. The shortcuts "
                    "{} and {} also work on the canvas."
                )
            ).format(
                _utils.format_shortcut(
                    f"{shortcuts['zoom_in']},{shortcuts['zoom_out']}"
                ),
                _utils.format_shortcut(self.tr("Ctrl+Wheel")),
            )
        )
        self._canvas_widgets.zoom_widget.setEnabled(False)

        self._zoom_mode = _ZoomMode.FIT_WINDOW
        fit_window.setChecked(True)

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
        zoom = (
            self._canvas_widgets.zoom_widget,
            zoom_in,
            zoom_out,
            zoom_org,
            fit_window,
            fit_width,
        )
        on_load_active = (
            close,
            create_mode,
            create_rectangle_mode,
            create_oriented_rectangle_mode,
            create_circle_mode,
            create_line_mode,
            create_point_mode,
            create_line_strip_mode,
            create_ai_points_to_shape_mode,
            create_ai_box_to_shape_mode,
            brightness_contrast,
        )
        on_shapes_present = (save_as, hide_all, show_all, toggle_all)
        context_menu = (
            *[draw_action for _, draw_action in draw],
            edit_mode,
            edit,
            duplicate,
            copy,
            paste,
            delete,
            undo,
            undo_last_point,
            add_point_to_edge,
            remove_point,
        )
        edit_menu = (
            edit,
            duplicate,
            copy,
            paste,
            delete,
            None,
            undo,
            undo_last_point,
            None,
            remove_point,
            None,
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
            duplicate=duplicate,
            copy=copy,
            paste=paste,
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
        shortcuts = self._config["shortcuts"]

        quit_ = action(
            text=self.tr("&Quit"),
            slot=self.close,
            shortcut=shortcuts["quit"],
            icon=None,
            tip=self.tr("Quit application"),
        )
        settings_editable = self._is_settings_editable
        open_config = action(
            text=self.tr("Settings…"),
            slot=self._open_settings,
            shortcut="Ctrl+," if platform.system() == "Darwin" else "Ctrl+Shift+,",
            icon=None,
            tip=(
                self.tr("Edit settings")
                if settings_editable
                else self.tr("Settings are managed via --config for this session")
            ),
            enabled=settings_editable,
        )
        open_config.setMenuRole(QtGui.QAction.MenuRole.PreferencesRole)
        help_ = action(
            self.tr("&Tutorial"),
            self.tutorial,
            icon="phosphor/question.svg",
            tip=self.tr("Show tutorial page"),
        )

        file_menu = self.menu(self.tr("&File"))
        edit_menu = self.menu(self.tr("&Edit"))
        view_menu = self.menu(self.tr("&View"))
        help_menu = self.menu(self.tr("&Help"))
        label_menu = QtWidgets.QMenu()
        _utils.add_actions(label_menu, (self._actions.edit, self._actions.delete))
        self._docks.label_list.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self._docks.label_list.customContextMenuRequested.connect(
            self.show_label_list_menu
        )

        _utils.add_actions(
            file_menu,
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
                None,
                open_config,
                None,
                quit_,
            ),
        )
        _utils.add_actions(help_menu, (help_, self._actions.about))
        _utils.add_actions(
            view_menu,
            (
                self._docks.flag_dock.toggleViewAction(),
                self._docks.label_dock.toggleViewAction(),
                self._docks.shape_dock.toggleViewAction(),
                self._docks.file_dock.toggleViewAction(),
                None,
                self._actions.reset_layout,
                None,
                self._actions.fill_drawing,
                None,
                self._actions.hide_all,
                self._actions.show_all,
                self._actions.toggle_all,
                None,
                self._actions.zoom_in,
                self._actions.zoom_out,
                self._actions.zoom_org,
                self._actions.keep_prev_zoom,
                None,
                self._actions.fit_window,
                self._actions.fit_width,
                None,
                self._actions.brightness_contrast,
                self._actions.toggle_keep_prev_brightness_contrast,
            ),
        )

        _utils.add_actions(
            self._canvas_widgets.canvas.context_menus.without_selection,
            self._actions.context_menu,
        )
        _utils.add_actions(
            self._canvas_widgets.canvas.context_menus.with_selection,
            (
                action("&Copy here", self.copy_shape),
                action("&Move here", self.move_shape),
            ),
        )

        return _Menus(
            file=file_menu,
            edit=edit_menu,
            view=view_menu,
            help=help_menu,
            label_list=label_menu,
        )

    def _setup_toolbars(self) -> None:
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
                    None,
                    self._actions.edit_mode,
                    self._actions.duplicate,
                    self._actions.delete,
                    self._actions.undo,
                    self._actions.brightness_contrast,
                    None,
                    self._actions.fit_window,
                    self._actions.zoom_widget_action,
                    None,
                    select_ai_model,
                    None,
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
                    None,
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
        self._image_path = None
        self._prev_image_path = None
        self._zoom_values = {}
        self._brightness_contrast_values = {}
        self._scroll_values = {
            Qt.Orientation.Horizontal: {},
            Qt.Orientation.Vertical: {},
        }

        if self._config["file_search"]:
            self._docks.file_search.setText(self._config["file_search"])

        self._default_state = self.saveState()
        #
        # XXX: Could be completely declarative.
        # Restore the window geometry and dock layout (separate from the user
        # Config; this Qt store holds only window state).
        self._window_state = QtCore.QSettings("labelme", "labelme")
        #
        # Bump this when dock/toolbar layout changes to reset window state
        # for users upgrading from an older version.
        SETTINGS_VERSION: int = 1
        if self._window_state.value("settingsVersion", 0, type=int) != SETTINGS_VERSION:
            self._reset_layout()
            self._window_state.setValue("settingsVersion", SETTINGS_VERSION)
        #
        self.resize(
            cast(
                QtCore.QSize,
                self._window_state.value("window/size", QtCore.QSize(900, 500)),
            )
        )
        self.move(
            cast(
                QtCore.QPoint,
                self._window_state.value("window/position", QtCore.QPoint(0, 0)),
            )
        )
        self.restoreState(
            cast(
                QtCore.QByteArray,
                self._window_state.value("window/state", QtCore.QByteArray()),
            )
        )
        # Recover window position when the saved screen is no longer connected.
        if not any(
            s.availableGeometry().intersects(self.frameGeometry())
            for s in QtWidgets.QApplication.screens()
        ) and (primary_screen := QtWidgets.QApplication.primaryScreen()):
            self.move(primary_screen.availableGeometry().topLeft())

        if file_or_dir:
            self._load_from_file_or_dir(file_or_dir=file_or_dir)

    def _setup_status_bar(self) -> _StatusBarWidgets:
        message = QtWidgets.QLabel(self.tr("%s started.") % __appname__)
        stats = StatusStats()
        self.statusBar().addWidget(message, 1)
        self.statusBar().addWidget(stats, 0)
        self.statusBar().show()
        return _StatusBarWidgets(message=message, stats=stats)

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
        canvas.set_point_size(self._config["shape"]["point_size"])
        canvas.set_show_labels(self._config["shape"]["show_labels"])
        canvas.set_draft_palette(
            Palette(
                line=QtGui.QColor(*self._config["shape"]["line_color"]),
                fill=QtGui.QColor(*self._config["shape"]["fill_color"]),
                select_line=QtGui.QColor(*self._config["shape"]["select_line_color"]),
                select_fill=QtGui.QColor(*self._config["shape"]["select_fill_color"]),
                vertex_fill=QtGui.QColor(*self._config["shape"]["vertex_fill_color"]),
                hvertex_fill=QtGui.QColor(*self._config["shape"]["hvertex_fill_color"]),
            )
        )
        canvas.set_color_resolver(
            lambda label: self._get_rgb_by_label(
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
                self.tr("Shape had no area; nothing created."), 5000
            )
        )
        canvas.shape_moved.connect(self.mark_dirty)
        canvas.selection_changed.connect(self._on_shape_selection_changed)
        canvas.drawing_polygon.connect(self._on_drawing_polygon_changed)

        self.setCentralWidget(scroll_area)

        return _CanvasWidgets(
            canvas=canvas,
            zoom_widget=zoom_widget,
            scroll_bars=scroll_bars,
        )

    def _setup_dock_widgets(self) -> _DockWidgets:
        flag_list = QtWidgets.QListWidget()
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
        label_list.item_selection_changed.connect(self._label_selection_changed)
        label_list.item_double_clicked.connect(self._edit_label)
        label_list.item_changed.connect(self._on_label_item_changed)
        label_list.item_dropped.connect(self._on_label_order_changed)
        shape = QtWidgets.QDockWidget(self.tr("Annotation List"), self)
        shape.setObjectName("Labels")
        shape.setWidget(label_list)

        unique_label_list = UniqueLabelQListWidget()
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
        file_search.setPlaceholderText(self.tr("Search Filename"))
        file_search.textChanged.connect(self._on_file_search_changed)
        file_list = QtWidgets.QListWidget()
        file_list.itemSelectionChanged.connect(self._file_list_item_selection_changed)
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
        self, config_file: Path | None, config_overrides: dict | None
    ) -> tuple[Path | None, dict]:
        try:
            config = _config.load_config(
                config_file=config_file, config_overrides=config_overrides or {}
            )
        except ValueError as e:
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

    def menu(
        self,
        title: str,
        actions: tuple[QtGui.QAction | QtWidgets.QMenu | None, ...] | None = None,
    ) -> QtWidgets.QMenu:
        menu = self.menuBar().addMenu(title)
        if actions:
            _utils.add_actions(menu, actions)
        return menu

    # Support Functions

    def has_no_shapes(self) -> bool:
        return not len(self._docks.label_list)

    def populate_mode_actions(self) -> None:
        self._canvas_widgets.canvas.context_menus.without_selection.clear()
        _utils.add_actions(
            self._canvas_widgets.canvas.context_menus.without_selection,
            self._actions.context_menu,
        )
        self._menus.edit.clear()
        actions = (
            *[draw_action for _, draw_action in self._actions.draw],
            self._actions.edit_mode,
            *self._actions.edit_menu,
        )
        _utils.add_actions(self._menus.edit, actions)

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
        # Autosave does not clear the undo stack; keep the undo action available.
        self._actions.undo.setEnabled(self._canvas_widgets.canvas.can_restore_shape)

        if self._actions.save_auto.isChecked():
            assert self._image_path is not None
            self.save_labels(
                label_path=_resolve_label_path(
                    image_or_label_path=self._image_path,
                    output_dir=self._output_dir,
                )
            )
            return
        self._is_changed = True
        self._actions.save.setEnabled(True)
        self.setWindowTitle(self._get_window_title(dirty=True))

    def mark_clean(self) -> None:
        self._is_changed = False
        self._actions.save.setEnabled(False)
        for _, action in self._actions.draw:
            action.setEnabled(True)
        self.setWindowTitle(self._get_window_title(dirty=False))

        if self.has_label_file():
            self._actions.delete_file.setEnabled(True)
        else:
            self._actions.delete_file.setEnabled(False)

    def update_action_states(self, value: bool = True) -> None:
        for action in (*self._actions.zoom, *self._actions.on_load_active):
            action.setEnabled(value)

    def show_status_message(self, message: str, delay: int = 500) -> None:
        self.statusBar().showMessage(message, delay)

    def _submit_ai_prompt(self, _: bool) -> None:
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
        model_type = osam.apis.get_model_type_by_name(model_name)
        if not (_is_already_downloaded := model_type.get_size() is not None):
            if not download_ai_model(model_name=model_name, parent=self):
                return
        if (
            self._text_osam_session is None
            or self._text_osam_session.model_name != model_name
        ):
            self._text_osam_session = _automation.OsamSession(model_name=model_name)

        try:
            boxes, scores, labels, masks = _automation.get_bboxes_from_texts(
                session=self._text_osam_session,
                image=_utils.img_qt_to_arr(self._image)[:, :, :3],
                image_id=str(hash(self._image_path)),
                texts=texts,
            )
        except Exception as e:
            logger.opt(exception=e).error("AI text inference failed")
            self._on_inference_failed(message=f"{type(e).__name__}: {e}")
            return

        if (
            masks is None
            and len(boxes) > 0
            and shape_type in _automation.MASK_REQUIRED_SHAPE_TYPES
        ):
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

        SCORE_FOR_EXISTING_SHAPE: Final[float] = 1.01
        for shape in self._canvas_widgets.canvas.shapes:
            if shape.shape_type != shape_type or shape.label not in texts:
                continue
            shape_bbox = _automation.shape_to_xyxy_bbox(shape=shape)
            if shape_bbox is None:
                continue
            boxes = np.r_[boxes, [shape_bbox]]
            scores = np.r_[scores, [SCORE_FOR_EXISTING_SHAPE]]
            labels = np.r_[labels, [texts.index(shape.label)]]

        boxes, scores, labels, indices = _automation.nms_bboxes(
            boxes=boxes,
            scores=scores,
            labels=labels,
            iou_threshold=self._ai_text.get_iou_threshold(),
            score_threshold=self._ai_text.get_score_threshold(),
            max_num_detections=100,
        )

        is_new = scores != SCORE_FOR_EXISTING_SHAPE
        boxes = boxes[is_new]
        scores = scores[is_new]
        labels = labels[is_new]
        indices = indices[is_new]

        if masks is None:
            masks = [None] * len(boxes)
        else:
            masks = [masks[i] for i in indices]
        del indices

        detections: list[_automation.Detection] = []
        for box, score, label, mask in zip(boxes, scores, labels, masks):
            text: str = texts[label]
            detections.append(
                _automation.Detection(
                    bbox=(
                        float(box[0]),
                        float(box[1]),
                        float(box[2]),
                        float(box[3]),
                    ),
                    mask=mask,
                    label=text,
                    description=json.dumps(dict(score=score.item(), text=text)),
                )
            )
        detections = _automation.suppress_detections_greedy(
            detections=detections,
            iou_threshold=self._ai_text.get_iou_threshold(),
        )
        shapes: list[Shape] = _automation.shapes_from_detections(
            detections=detections, shape_type=shape_type
        )

        self._canvas_widgets.canvas.backup_shapes()
        self._load_shapes(shapes, replace=False)
        self.mark_dirty()

    def reset_state(self) -> None:
        self._docks.label_list.clear()
        self._annotation = None
        self._image_path = None
        self._label_file_path = None
        self._canvas_widgets.canvas.reset_state()

    # Callbacks

    def undo_shape_edit(self) -> None:
        self._canvas_widgets.canvas.restore_last_shape()
        self._docks.label_list.clear()
        self._load_shapes(self._canvas_widgets.canvas.shapes)
        self._actions.undo.setEnabled(self._canvas_widgets.canvas.can_restore_shape)

    def tutorial(self) -> None:
        url = "https://github.com/labelmeai/labelme/tree/main/examples/tutorial"  # NOQA
        webbrowser.open(url)

    def _on_drawing_polygon_changed(self, drawing: bool = True) -> None:
        # In the middle of drawing, toggling between modes should be disabled.
        self._actions.edit_mode.setEnabled(not drawing)
        self._actions.undo_last_point.setEnabled(drawing)
        self._actions.undo.setEnabled(not drawing)
        self._actions.delete.setEnabled(not drawing)

    def _switch_canvas_mode(
        self, edit: bool = True, create_mode: str | None = None
    ) -> None:
        if create_mode == "ai_points_to_shape":
            model_name = self._canvas_widgets.canvas.get_ai_model_name()
            if model_name in _AI_MODELS_WITHOUT_POINT_SUPPORT:
                QtWidgets.QMessageBox.warning(
                    self,
                    self.tr("AI-Points Unavailable"),
                    self.tr(
                        "%s does not support point prompts.\n"
                        "Please select a different model or use AI-Box mode."
                    )
                    % model_name,
                )
                return
        self._canvas_widgets.canvas.set_editing(edit)
        if create_mode is not None:
            self._canvas_widgets.canvas.create_mode = create_mode
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
        if create_mode == "ai_points_to_shape":
            self._ai_annotation.set_disabled_models(_AI_MODELS_WITHOUT_POINT_SUPPORT)
        else:
            self._ai_annotation.set_disabled_models(())

    def _highlight_ai_buttons(self, highlight: bool) -> None:
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
            if mode in _AI_CREATE_MODES:
                for widget in action.associatedObjects():
                    if isinstance(widget, QtWidgets.QToolButton):
                        widget.setStyleSheet(style)

    def show_label_list_menu(self, point: QtCore.QPoint) -> None:
        self._label_list_menu_origin = self._docks.label_list.mapToGlobal(point)
        try:
            # PySide6 type QMenu.exec() argument too narrowly
            self._menus.label_list.exec(self._label_list_menu_origin)  # ty: ignore[invalid-argument-type]
        finally:
            self._label_list_menu_origin = None

    def validate_label(self, label: str) -> bool:
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

    def _edit_label(self, value: object | None = None) -> None:
        items = self._docks.label_list.selected_items()
        if not items:
            logger.warning("No label is selected, so cannot edit label.")
            return

        shapes = [cast(Shape, item.shape()) for item in items]
        first_shape = shapes[0]

        if len(items) == 1:
            edit_text = True
            edit_flags = True
            edit_group_id = True
            edit_description = True
        else:
            edit_text = all(shape.label == first_shape.label for shape in shapes[1:])
            edit_flags = all(shape.flags == first_shape.flags for shape in shapes[1:])
            edit_group_id = all(
                shape.group_id == first_shape.group_id for shape in shapes[1:]
            )
            edit_description = all(
                shape.description == first_shape.description for shape in shapes[1:]
            )

        if not edit_text:
            self._label_dialog.edit.setDisabled(True)
            self._label_dialog.label_list.setDisabled(True)
        if not edit_group_id:
            self._label_dialog.edit_group_id.setDisabled(True)
        if not edit_description:
            self._label_dialog.edit_description.setDisabled(True)

        canvas_menu_origin = self._canvas_widgets.canvas.context_menu_origin
        menu_origin = (
            canvas_menu_origin
            if canvas_menu_origin is not None
            else self._label_list_menu_origin
        )

        text, flags, group_id, description = self._label_dialog.popup(
            text=first_shape.label if edit_text else "",
            position=menu_origin,
            flags=first_shape.flags if edit_flags else None,
            group_id=first_shape.group_id if edit_group_id else None,
            description=first_shape.description if edit_description else None,
            flags_disabled=not edit_flags,
        )

        if not edit_text:
            self._label_dialog.edit.setDisabled(False)
            self._label_dialog.label_list.setDisabled(False)
        if not edit_group_id:
            self._label_dialog.edit_group_id.setDisabled(False)
        if not edit_description:
            self._label_dialog.edit_description.setDisabled(False)

        if text is None:
            assert flags is None
            assert group_id is None
            assert description is None
            return

        if not self.validate_label(text):
            self.show_error_message(
                self.tr("Invalid label"),
                self.tr("Invalid label '{}' with validation type '{}'").format(
                    text, self._config["validate_label"]
                ),
            )
            return

        self._canvas_widgets.canvas.backup_shapes()
        for item in items:
            shape = item.shape()
            assert shape is not None

            if edit_text:
                shape.label = text
            if edit_flags:
                shape.flags = flags
            if edit_group_id:
                shape.group_id = group_id
            if edit_description:
                shape.description = description

            assert shape.label is not None
            item.setText(
                format_shape_label(
                    shape,
                    fill_rgb=self._get_rgb_by_label(
                        label=shape.label,
                        unique_label_list=self._docks.unique_label_list,
                    ),
                )
            )
            self.mark_dirty()
            if self._docks.unique_label_list.find_label_item(shape.label) is None:
                self._docks.unique_label_list.add_label_item(
                    label=shape.label,
                    color=self._get_rgb_by_label(
                        label=shape.label,
                        unique_label_list=self._docks.unique_label_list,
                    ),
                )

    def _on_file_search_changed(self) -> None:
        self._import_images_from_dir(
            root_dir=self._prev_opened_dir, pattern=self._docks.file_search.text()
        )

    def _file_list_item_selection_changed(self) -> None:
        if not self._can_continue():
            return
        if not (items := self._docks.file_list.selectedItems()):
            return
        self._load_file(image_or_label_path=items[0].text())

    # React to canvas signals.
    def _on_shape_selection_changed(self, selected_shapes: list[Shape]) -> None:
        self._docks.label_list.item_selection_changed.disconnect(
            self._label_selection_changed
        )
        self._docks.label_list.clearSelection()
        self._canvas_widgets.canvas.selected_shapes = selected_shapes
        for shape in self._canvas_widgets.canvas.selected_shapes:
            item = self._docks.label_list.find_item_by_shape(shape)
            self._docks.label_list.select_item(item)
            self._docks.label_list.scroll_to_item(item)
        self._docks.label_list.item_selection_changed.connect(
            self._label_selection_changed
        )
        n_selected = len(selected_shapes) > 0
        self._actions.delete.setEnabled(n_selected)
        self._actions.duplicate.setEnabled(n_selected)
        self._actions.copy.setEnabled(n_selected)
        self._actions.edit.setEnabled(n_selected)

    def add_label(self, shape: Shape) -> None:
        assert shape.label is not None
        label_list_item = LabelListWidgetItem(shape=shape)
        self._docks.label_list.add_item(label_list_item)
        if self._docks.unique_label_list.find_label_item(shape.label) is None:
            self._docks.unique_label_list.add_label_item(
                label=shape.label,
                color=self._get_rgb_by_label(
                    label=shape.label,
                    unique_label_list=self._docks.unique_label_list,
                ),
            )
        self._label_dialog.add_label_history(shape.label)
        for action in self._actions.on_shapes_present:
            action.setEnabled(True)

        label_list_item.setText(
            format_shape_label(
                shape,
                fill_rgb=self._get_rgb_by_label(
                    label=shape.label,
                    unique_label_list=self._docks.unique_label_list,
                ),
            )
        )

    def _get_rgb_by_label(
        self,
        label: str,
        unique_label_list: UniqueLabelQListWidget,
    ) -> tuple[int, int, int]:
        if self._config["shape_color"] == "auto":
            item = unique_label_list.find_label_item(label)
            item_index: int = (
                unique_label_list.indexFromItem(item).row()
                if item
                else unique_label_list.count()
            )
            label_id: int = (
                1  # skip black color by default
                + item_index
                + self._config["shift_auto_shape_color"]
            )
            return _rgb_from_colormap_id(label_id=label_id)
        if self._config["shape_color"] == "manual":
            rgb = _rgb_from_label_colors(
                label=label, label_colors=self._config["label_colors"]
            )
            if rgb is not None:
                return rgb
        if self._config["default_shape_color"]:
            return self._config["default_shape_color"]
        return (0, 255, 0)

    def remove_labels(self, shapes: list[Shape]) -> None:
        self._docks.label_list.item_dropped.disconnect(self._on_label_order_changed)
        for shape in shapes:
            item = self._docks.label_list.find_item_by_shape(shape)
            self._docks.label_list.remove_item(item)
        self._docks.label_list.item_dropped.connect(self._on_label_order_changed)

    def _load_shapes(self, shapes: list[Shape], replace: bool = True) -> None:
        self._docks.label_list.item_selection_changed.disconnect(
            self._label_selection_changed
        )
        shape: Shape
        for shape in shapes:
            self.add_label(shape)
        self._docks.label_list.clearSelection()
        self._docks.label_list.item_selection_changed.connect(
            self._label_selection_changed
        )
        self._canvas_widgets.canvas.load_shapes(shapes=shapes, replace=replace)

    def _load_flags(
        self,
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

    def save_labels(self, label_path: str) -> bool:
        shapes = [
            _shape_to_dict(s)
            for item in self._docks.label_list
            if (s := item.shape()) is not None
        ]
        flags = self._read_flag_dock_states()
        try:
            assert self._image_path
            assert self._annotation is not None
            label_dir = Path(label_path).parent
            label_dir.mkdir(parents=True, exist_ok=True)
            annotation = Annotation(
                image_path=os.path.relpath(self._image_path, label_dir),
                image_data=self._annotation.image_data,
                shapes=shapes,
                flags=flags,
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
            items = self._docks.file_list.findItems(
                self._image_path, Qt.MatchFlag.MatchExactly
            )
            if len(items) > 0:
                if len(items) != 1:
                    raise RuntimeError("There are duplicate files.")
                items[0].setCheckState(Qt.CheckState.Checked)
            return True
        except LabelFileError as e:
            self.show_error_message(
                self.tr("Error saving label data"), self.tr("<b>%s</b>") % e
            )
            return False

    def _insert_shapes(self, shapes: list[Shape]) -> None:
        if not shapes:
            return
        self._load_shapes(shapes=shapes, replace=False)
        self._canvas_widgets.canvas.select_shapes(shapes)
        self.mark_dirty()

    def _label_selection_changed(self) -> None:
        selected_shapes: list[Shape] = []
        for item in self._docks.label_list.selected_items():
            shape = item.shape()
            assert shape is not None
            selected_shapes.append(shape)
        if selected_shapes:
            self._canvas_widgets.canvas.select_shapes(selected_shapes)
        else:
            if self._canvas_widgets.canvas.deselect_shape():
                self._canvas_widgets.canvas.update()

    def _on_label_item_changed(self, item: LabelListWidgetItem) -> None:
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
        self._canvas_widgets.canvas.load_shapes(shapes)

    # Callback functions:

    def _on_new_shape(self) -> None:
        items = self._docks.unique_label_list.selectedItems()
        text = None
        if items:
            text = items[0].data(Qt.ItemDataRole.UserRole)
        flags = {}
        group_id = None
        description = ""
        if self._config["display_label_popup"] or not text:
            previous_text = self._label_dialog.edit.text()
            text, flags, group_id, description = self._label_dialog.popup(text)
            if not text:
                self._label_dialog.edit.setText(previous_text)

        if text and not self.validate_label(text):
            self.show_error_message(
                self.tr("Invalid label"),
                self.tr("Invalid label '{}' with validation type '{}'").format(
                    text, self._config["validate_label"]
                ),
            )
            text = ""
        if text:
            self._docks.label_list.clearSelection()
            assert isinstance(flags, dict)
            shapes = self._canvas_widgets.canvas.set_last_label(text, flags)
            for shape in shapes:
                shape.group_id = group_id
                shape.description = description
                self.add_label(shape)
            self._actions.edit_mode.setEnabled(True)
            self._actions.undo_last_point.setEnabled(False)
            self._actions.undo.setEnabled(True)
            self.mark_dirty()
        else:
            self._canvas_widgets.canvas.undo_last_line()
            self._canvas_widgets.canvas.shape_backups.pop()

    def _on_inference_produced_no_shapes(self) -> None:
        self.show_status_message(
            self.tr("AI inference produced no new annotation."), 5000
        )

    def _on_inference_failed(self, message: str) -> None:
        self.show_status_message(self.tr("AI inference failed: %s") % message, 10000)

    def _on_scroll_request(self, delta: int, orientation: Qt.Orientation) -> None:
        units = -delta * 0.1  # natural scroll
        bar = self._canvas_widgets.scroll_bars[orientation]
        value = bar.value() + bar.singleStep() * units
        self.set_scroll_value(orientation, value)

    def _on_pan_request(self, step: QtCore.QPoint) -> None:
        # Pan moves the viewport opposite to the cursor delta so the image
        # tracks the grabbed point one-for-one in widget pixels.
        h_bar = self._canvas_widgets.scroll_bars[Qt.Orientation.Horizontal]
        v_bar = self._canvas_widgets.scroll_bars[Qt.Orientation.Vertical]
        self.set_scroll_value(Qt.Orientation.Horizontal, h_bar.value() - step.x())
        self.set_scroll_value(Qt.Orientation.Vertical, v_bar.value() - step.y())

    def set_scroll_value(self, orientation: Qt.Orientation, value: float) -> None:
        self._canvas_widgets.scroll_bars[orientation].setValue(int(value))
        if self._image_path is not None:
            self._scroll_values[orientation][self._image_path] = value

    def _set_zoom(self, value: float, pos: QtCore.QPointF | None = None) -> None:
        if self._image_path is None:
            logger.warning("image_path is None, cannot set zoom")
            return

        if pos is None:
            pos = QtCore.QPointF(
                self._canvas_widgets.canvas.visibleRegion().boundingRect().center()
            )
        canvas_width_old: int = self._canvas_widgets.canvas.width()

        self._sync_zoom_mode_actions()
        self._canvas_widgets.zoom_widget.setValue(value)  # triggers self._paint_canvas
        self._zoom_values[self._image_path] = (self._zoom_mode, value)

        canvas_width_new: int = self._canvas_widgets.canvas.width()
        if canvas_width_old == canvas_width_new:
            return
        canvas_scale_factor = canvas_width_new / canvas_width_old
        x_shift: float = pos.x() * canvas_scale_factor - pos.x()
        y_shift: float = pos.y() * canvas_scale_factor - pos.y()
        self.set_scroll_value(
            Qt.Orientation.Horizontal,
            self._canvas_widgets.scroll_bars[Qt.Orientation.Horizontal].value()
            + x_shift,
        )
        self.set_scroll_value(
            Qt.Orientation.Vertical,
            self._canvas_widgets.scroll_bars[Qt.Orientation.Vertical].value() + y_shift,
        )

    def _set_zoom_to_original(self) -> None:
        self._zoom_mode = _ZoomMode.MANUAL_ZOOM
        self._set_zoom(value=100)

    def _add_zoom(self, increment: float, pos: QtCore.QPointF | None = None) -> None:
        # Multiplicative stepping on a float widget; the QDoubleSpinBox rounds to
        # its decimal precision, so no integer ceil/floor clamping is needed.
        zoom_value = self._canvas_widgets.zoom_widget.value() * increment
        self._zoom_mode = _ZoomMode.MANUAL_ZOOM
        self._set_zoom(value=zoom_value, pos=pos)

    def _zoom_requested(self, delta: int, pos: QtCore.QPointF) -> None:
        self._add_zoom(increment=1.1 if delta > 0 else 0.9, pos=pos)

    def set_fit_window_mode(self, value: bool = True) -> None:
        target = _ZoomMode.FIT_WINDOW if value else _ZoomMode.MANUAL_ZOOM
        self._switch_zoom_mode(target)

    def set_fit_width_mode(self, value: bool = True) -> None:
        target = _ZoomMode.FIT_WIDTH if value else _ZoomMode.MANUAL_ZOOM
        self._switch_zoom_mode(target)

    def _switch_zoom_mode(self, mode: _ZoomMode) -> None:
        self._zoom_mode = mode
        self._adjust_scale()

    def _sync_zoom_mode_actions(self) -> None:
        self._actions.fit_window.setChecked(self._zoom_mode == _ZoomMode.FIT_WINDOW)
        self._actions.fit_width.setChecked(self._zoom_mode == _ZoomMode.FIT_WIDTH)

    def _on_brightness_contrast_changed(self, qimage: QtGui.QImage) -> None:
        self._canvas_widgets.canvas.load_pixmap(
            QtGui.QPixmap.fromImage(qimage), clear_shapes=False
        )

    def open_brightness_contrast_dialog(
        self, value: bool, is_initial_load: bool = False
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
            _utils.img_data_to_pil(self._annotation.image_data),
            self._on_brightness_contrast_changed,
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

    def toggle_shape_visibility(self, value: bool | None) -> None:
        for item in self._docks.label_list:
            target = (
                item.checkState() == Qt.CheckState.Unchecked if value is None else value
            )
            item.setCheckState(
                Qt.CheckState.Checked if target else Qt.CheckState.Unchecked
            )

    def _open_label_file_into_state(self, label_path: str) -> Annotation | None:
        try:
            annotation = read_label_file(filename=label_path)
        except LabelFileError as e:
            self._show_file_open_error(path=label_path, file_kind="label", exc=e)
            return None
        self._label_file_path = label_path
        self._annotation = annotation
        self._image_path = str(Path(label_path).parent / annotation.image_path)
        return annotation

    def _open_image_into_state(self, image_path: str) -> bool:
        try:
            image_data = read_image_file(filename=image_path)
        except OSError as e:
            self._show_file_open_error(path=image_path, file_kind="image", exc=e)
            return False
        self._annotation = Annotation(
            image_path=os.path.basename(image_path),
            image_data=image_data,
            shapes=[],
            flags={},
            other_data={},
        )
        self._image_path = image_path
        self._label_file_path = None
        return True

    def _load_file(self, image_or_label_path: str) -> None:
        # changing fileListWidget loads file
        if image_or_label_path in self.image_list and (
            self._docks.file_list.currentRow()
            != self.image_list.index(image_or_label_path)
        ):
            self._docks.file_list.setCurrentRow(
                self.image_list.index(image_or_label_path)
            )
            self._docks.file_list.repaint()
            return

        prev_shapes: list[Shape] = (
            self._canvas_widgets.canvas.shapes
            if self._config["keep_prev"]
            or QtWidgets.QApplication.keyboardModifiers()
            == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
            else []
        )
        self._prev_image_path = self._image_path
        self.reset_state()
        self._canvas_widgets.canvas.setEnabled(False)
        if not QtCore.QFile.exists(image_or_label_path):
            self.show_error_message(
                self.tr("Error opening file"),
                self.tr("No such file: <b>%s</b>") % image_or_label_path,
            )
            return
        # assumes same name, but json extension
        self.show_status_message(
            self.tr("Loading %s...") % Path(image_or_label_path).name
        )

        t0_load_file = time.time()
        label_path: str = _resolve_label_path(
            image_or_label_path=image_or_label_path,
            output_dir=self._output_dir,
        )
        annotation: Annotation | None = None
        if QtCore.QFile.exists(label_path):
            annotation = self._open_label_file_into_state(label_path=label_path)
            if annotation is None:
                return
        else:
            if not self._open_image_into_state(image_path=image_or_label_path):
                return
        assert self._annotation is not None
        t0 = time.time()
        image = QtGui.QImage.fromData(self._annotation.image_data)
        logger.debug("Created QImage in {:.0f}ms", (time.time() - t0) * 1000)

        if image.isNull():
            formats = ", ".join(
                f"*.{fmt.toStdString()}"
                for fmt in QtGui.QImageReader.supportedImageFormats()
            )
            extra = self.tr("Allowed formats: {formats}").format(formats=formats)
            self._show_file_open_error(
                path=image_or_label_path,
                file_kind="image",
                extra=extra,
            )
            return
        self._image = image
        t0 = time.time()
        self._canvas_widgets.canvas.load_pixmap(QtGui.QPixmap.fromImage(image))
        logger.debug("Loaded pixmap in {:.0f}ms", (time.time() - t0) * 1000)
        flags = {k: False for k in self._config["flags"] or []}
        if annotation is not None:
            self._load_shapes(
                shapes=_shapes_from_dicts(
                    shape_dicts=annotation.shapes,
                    label_flags=self._config["label_flags"],
                )
            )
            flags.update(annotation.flags)
        self._load_flags(flags=flags, widget=self._docks.flag_list)
        if prev_shapes and self.has_no_shapes():
            self._load_shapes(shapes=prev_shapes, replace=False)
            self.mark_dirty()
        else:
            self.mark_clean()
        self._canvas_widgets.canvas.setEnabled(True)
        # set zoom values
        is_initial_load = not self._zoom_values
        if self._image_path in self._zoom_values:
            self._zoom_mode = self._zoom_values[self._image_path][0]
            self._set_zoom(self._zoom_values[self._image_path][1])
        elif is_initial_load or not self._config["keep_prev_scale"]:
            self._zoom_mode = _ZoomMode.FIT_WINDOW
            self._adjust_scale()
        # set scroll values
        for orientation in self._scroll_values:
            if self._image_path in self._scroll_values[orientation]:
                self.set_scroll_value(
                    orientation, self._scroll_values[orientation][self._image_path]
                )
        self.open_brightness_contrast_dialog(value=False, is_initial_load=True)
        self._paint_canvas()
        self.update_action_states(True)
        self._canvas_widgets.canvas.setFocus()
        self.show_status_message(self.tr("Loaded %s") % Path(image_or_label_path).name)
        logger.info(
            "Loaded file: {!r} in {:.0f}ms",
            image_or_label_path,
            (time.time() - t0_load_file) * 1000,
        )

    def resizeEvent(self, a0: QtGui.QResizeEvent) -> None:
        if (
            self._canvas_widgets.canvas
            and not self._image.isNull()
            and self._zoom_mode != _ZoomMode.MANUAL_ZOOM
        ):
            self._adjust_scale()
        super().resizeEvent(a0)

    def _paint_canvas(self) -> None:
        if self._image.isNull():
            logger.warning("image is null, cannot paint canvas")
            return
        self._canvas_widgets.canvas.scale = (
            0.01 * self._canvas_widgets.zoom_widget.value()
        )
        self._canvas_widgets.canvas.adjustSize()
        self._canvas_widgets.canvas.update()

    def _adjust_scale(self) -> None:
        if self._zoom_mode == _ZoomMode.FIT_WINDOW:
            scale = self._fit_window_scale()
        elif self._zoom_mode == _ZoomMode.FIT_WIDTH:
            scale = self._fit_width_scale()
        else:
            scale = 1.0
        self._set_zoom(value=scale * 100)

    def _fit_window_scale(self) -> float:
        FIT_WINDOW_SCROLLBAR_MARGIN: Final[float] = 2.0
        viewport = self.centralWidget()
        pixmap = self._canvas_widgets.canvas.pixmap
        available_w = viewport.width() - FIT_WINDOW_SCROLLBAR_MARGIN
        available_h = viewport.height() - FIT_WINDOW_SCROLLBAR_MARGIN
        scale_by_width = available_w / pixmap.width()
        scale_by_height = available_h / pixmap.height()
        return min(scale_by_width, scale_by_height)

    def _fit_width_scale(self) -> float:
        FIT_WIDTH_SCROLLBAR_MARGIN: Final[float] = 15.0
        available_w = self.centralWidget().width() - FIT_WIDTH_SCROLLBAR_MARGIN
        return available_w / self._canvas_widgets.canvas.pixmap.width()

    def set_save_image_with_data(self, enabled: bool) -> None:
        self._config["with_image_data"] = enabled
        self._actions.save_with_image_data.setChecked(enabled)

    def _reset_layout(self) -> None:
        self._window_state.remove("window/state")
        self.restoreState(self._default_state)

    def closeEvent(self, a0: QtGui.QCloseEvent) -> None:
        if not self._can_continue():
            a0.ignore()
        self._window_state.setValue("window/size", self.size())
        self._window_state.setValue("window/position", self.pos())
        self._window_state.setValue("window/state", self.saveState())

    def dragEnterEvent(self, a0: QtGui.QDragEnterEvent) -> None:
        extensions = [
            f".{fmt.toStdString().lower()}"
            for fmt in QtGui.QImageReader.supportedImageFormats()
        ]
        if a0.mimeData().hasUrls():
            items = [i.toLocalFile() for i in a0.mimeData().urls()]
            if any([i.lower().endswith(tuple(extensions)) for i in items]):
                a0.accept()
        else:
            a0.ignore()

    def dropEvent(self, a0: QtGui.QDropEvent) -> None:
        if not self._can_continue():
            a0.ignore()
            return
        items = [i.toLocalFile() for i in a0.mimeData().urls()]
        self.import_dropped_image_files(items)

    # User Dialogs #

    def _open_prev_image(self, _value: bool = False) -> None:
        row_prev: int = self._docks.file_list.currentRow() - 1
        if row_prev < 0:
            logger.debug("there is no prev image")
            return

        logger.debug("setting current row to {:d}", row_prev)
        self._docks.file_list.setCurrentRow(row_prev)
        self._docks.file_list.repaint()

    def _open_next_image(self, _value: bool = False) -> None:
        row_next: int = self._docks.file_list.currentRow() + 1
        if row_next >= self._docks.file_list.count():
            logger.debug("there is no next image")
            return

        logger.debug("setting current row to {:d}", row_next)
        self._docks.file_list.setCurrentRow(row_next)
        self._docks.file_list.repaint()

    def _open_file_with_dialog(self, _value: bool = False) -> None:
        if not self._can_continue():
            return
        formats = [
            f"*.{fmt.toStdString()}"
            for fmt in QtGui.QImageReader.supportedImageFormats()
        ]
        filters = self.tr("Image & Label files (%s)") % " ".join(
            formats + [f"*{LABEL_FILE_SUFFIX}"]
        )
        image_or_label_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            self.tr("%s - Choose Image or Label file") % __appname__,
            self.current_path(),
            filters,
        )
        if image_or_label_path:
            self._load_from_file_or_dir(file_or_dir=image_or_label_path)

    def prompt_output_dir(self, _value: bool = False) -> None:
        default_output_dir: str
        if self._output_dir is not None:
            default_output_dir = str(self._output_dir)
        elif self._image_path:
            default_output_dir = str(Path(self._image_path).parent)
        else:
            default_output_dir = self.current_path()

        output_dir = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            self.tr("%s - Save/Load Annotations in Directory") % __appname__,
            default_output_dir,
            QtWidgets.QFileDialog.Option.ShowDirsOnly
            | QtWidgets.QFileDialog.Option.DontResolveSymlinks,
        )
        output_dir = str(output_dir)

        if not output_dir:
            return

        self._output_dir = Path(output_dir)

        self.statusBar().showMessage(
            self.tr("%s . Annotations will be saved/loaded in %s")
            % ("Change Annotations Dir", self._output_dir)
        )
        self.statusBar().show()

        current_image_path = self._image_path
        self._import_images_from_dir(root_dir=self._prev_opened_dir)

        if current_image_path in self.image_list:
            # retain currently selected file
            self._docks.file_list.setCurrentRow(
                self.image_list.index(current_image_path)
            )
            self._docks.file_list.repaint()

    def _save_label_file(self, *, save_as: bool = False) -> None:
        assert not self._image.isNull(), "cannot save empty image"

        label_path: str | None = None
        if not save_as and self._label_file_path is not None:
            label_path = self._label_file_path
        if label_path is None:
            label_path = self.prompt_save_file_path()

        if not label_path:
            logger.warning("label_path=%r is empty, so cannot save", label_path)
            return

        if self.save_labels(label_path=label_path):
            self.mark_clean()

    def prompt_save_file_path(self) -> str:
        assert self._image_path is not None
        caption = self.tr("%s - Choose File") % __appname__
        filters = self.tr("Label files (*%s)") % LABEL_FILE_SUFFIX
        dlg = QtWidgets.QFileDialog(
            parent=self,
            caption=caption,
            directory=str(self._output_dir or Path(self._image_path).parent),
            filter=filters,
        )
        dlg.setDefaultSuffix(LABEL_FILE_SUFFIX[1:])
        dlg.setAcceptMode(QtWidgets.QFileDialog.AcceptMode.AcceptSave)
        dlg.setOption(QtWidgets.QFileDialog.Option.DontConfirmOverwrite, False)
        dlg.setOption(QtWidgets.QFileDialog.Option.DontUseNativeDialog, False)
        label_path, _ = dlg.getSaveFileName(
            parent=self,
            caption=self.tr("Choose File"),
            dir=_resolve_label_path(
                image_or_label_path=self._image_path,
                output_dir=self._output_dir,
            ),
            filter=self.tr("Label files (*%s)") % LABEL_FILE_SUFFIX,
        )
        return label_path

    def close_file(self, _value: bool = False) -> None:
        if not self._can_continue():
            return
        self.reset_state()
        self.mark_clean()
        self.update_action_states(False)
        self._canvas_widgets.canvas.setEnabled(False)
        self._docks.file_list.setFocus()
        self._actions.save_as.setEnabled(False)

    def current_label_file_path(self) -> str:
        assert self._image_path is not None
        return str(Path(self._image_path).with_suffix(".json"))

    def _confirm_deletion(self, message: str) -> bool:
        msg_box = QtWidgets.QMessageBox(self)
        msg_box.setIcon(QtWidgets.QMessageBox.Icon.Warning)
        msg_box.setWindowTitle(self.tr("Attention"))
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
            "Permanently delete this label file? This action cannot be undone."
        )
        if not self._confirm_deletion(message=msg):
            return

        annotation_path = Path(self.current_label_file_path())
        if not annotation_path.exists():
            return

        annotation_path.unlink()
        logger.info(f"Label file is removed: {annotation_path}")

        item = self._docks.file_list.currentItem()
        if item:
            item.setCheckState(Qt.CheckState.Unchecked)

        # Only the label file was deleted, not the image: clear the annotations
        # but keep the image on the canvas.
        self._docks.label_list.clear()
        # Drop the pre-delete backups first so undo cannot resurrect the
        # annotations of the file we just removed; load_shapes then re-seeds the
        # stack with the empty state, keeping "top mirrors current" intact.
        self._canvas_widgets.canvas.shape_backups.clear()
        self._canvas_widgets.canvas.load_shapes(shapes=[], replace=True)
        self._actions.undo.setEnabled(self._canvas_widgets.canvas.can_restore_shape)
        self.mark_clean()

    @property
    def _is_settings_editable(self) -> bool:
        return self._config_file is not None and not self._config_overrides

    def _make_label_dialog(self) -> LabelDialog:
        return LabelDialog(
            parent=self,
            labels=self._config["labels"],
            sort_labels=self._config["sort_labels"],
            show_text_field=self._config["show_label_text_field"],
            completion=self._config["label_completion"],
            fit_to_content=self._config["fit_to_content"],
            flags=self._config["label_flags"],
        )

    def _on_setting_changed(self, key_path: tuple[str, ...], value: object) -> bool:
        # The dialog only opens with an editable config file (see _open_settings),
        # so there is always a file to persist to.
        if self._config_file is None:
            return False
        try:
            _config.set_override(
                config_file=self._config_file, key_path=key_path, value=value
            )
        except (OSError, ValueError) as e:
            QtWidgets.QMessageBox.warning(self, self.tr("Configuration Error"), str(e))
            return False

        node: dict = self._config
        for key in key_path[:-1]:
            node = node[key]
        node[key_path[-1]] = value
        self._apply_to_live_widgets(key_path=key_path)
        return True

    def _apply_to_live_widgets(self, key_path: tuple[str, ...]) -> None:
        if key_path == ("color_theme",):
            # apply_color_theme -> setColorScheme emits colorSchemeChanged, which
            # drives _retheme; no explicit refresh needed here.
            _utils.apply_color_theme(theme=self._config["color_theme"])
        elif key_path == ("shape", "show_labels"):
            canvas = self._canvas_widgets.canvas
            canvas.set_show_labels(self._config["shape"]["show_labels"])
            canvas.update()
        elif key_path == ("canvas", "allow_out_of_bounds_points"):
            canvas = self._canvas_widgets.canvas
            canvas.set_allow_out_of_bounds_points(
                self._config["canvas"]["allow_out_of_bounds_points"]
            )
            canvas.update()
        elif key_path[0] == "labels":
            # Update predefined labels in place so session history (labels learned
            # from loaded/created shapes via add_label_history) is preserved, while
            # a removed predefined label drops from suggestions unless it was used
            # this session.
            self._label_dialog.set_predefined_labels(self._config["labels"] or [])
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
                apply_setting=self._on_setting_changed,
                open_as_text=self._open_config_file,
                parent=self,
            )
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
            self.tr("Save annotations?"),
            prompt_text,
            QtWidgets.QMessageBox.StandardButton.Save
            | QtWidgets.QMessageBox.StandardButton.Discard
            | QtWidgets.QMessageBox.StandardButton.Cancel,
            QtWidgets.QMessageBox.StandardButton.Save,
        )
        if user_choice == QtWidgets.QMessageBox.StandardButton.Save:
            self._save_label_file()
            return True
        return user_choice == QtWidgets.QMessageBox.StandardButton.Discard

    def show_error_message(self, title: str, message: str) -> int:
        return QtWidgets.QMessageBox.critical(
            self, title, f"<p><b>{title}</b></p>{message}"
        )

    def _show_file_open_error(
        self,
        *,
        path: str,
        file_kind: Literal["label", "image"],
        exc: BaseException | None = None,
        extra: str | None = None,
    ) -> None:
        if file_kind == "label":
            message = self.tr(
                "The selected label file could not be opened: {path}"
            ).format(path=path)
        else:
            message = self.tr(
                "The selected image file could not be opened: {path}"
            ).format(path=path)
        if exc is not None:
            message = f"{message}\n\n{exc}"
        if extra:
            message = f"{message}\n\n{extra}"
        QtWidgets.QMessageBox.critical(self, self.tr("Error opening file"), message)
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
                self._canvas_widgets.canvas.hovered_shape
            )
            self.remove_labels([self._canvas_widgets.canvas.hovered_shape])
            if self.has_no_shapes():
                for action in self._actions.on_shapes_present:
                    action.setEnabled(False)
        self.mark_dirty()

    def delete_selected_shapes(self) -> None:
        msg = self.tr(
            "Permanently delete {} shapes? This action cannot be undone."
        ).format(len(self._canvas_widgets.canvas.selected_shapes))
        if not self._confirm_deletion(message=msg):
            return
        self.remove_labels(self._canvas_widgets.canvas.delete_selected())
        self.mark_dirty()
        if self.has_no_shapes():
            for action in self._actions.on_shapes_present:
                action.setEnabled(False)

    def copy_shape(self) -> None:
        self._canvas_widgets.canvas.end_move(copy=True)
        for shape in self._canvas_widgets.canvas.selected_shapes:
            self.add_label(shape)
        self._docks.label_list.clearSelection()
        self.mark_dirty()

    def move_shape(self) -> None:
        self._canvas_widgets.canvas.end_move(copy=False)
        self.mark_dirty()

    def _load_from_file_or_dir(self, file_or_dir: str) -> None:
        if not file_or_dir:
            raise ValueError("file_or_dir cannot be empty")

        if is_label_file_path(filename=file_or_dir):
            self._docks.file_list.clear()
            self._docks.file_dock.setEnabled(False)
            self._docks.file_dock.setToolTip(
                self.tr("File list is disabled when a label file is opened")
            )
            self._load_file(image_or_label_path=file_or_dir)
        elif Path(file_or_dir).is_dir():
            self._import_images_from_dir(
                root_dir=file_or_dir, pattern=self._docks.file_search.text()
            )
            self._open_next_image()
        else:
            self._import_images_from_dir(
                root_dir=str(Path(file_or_dir).parent),
                pattern=self._docks.file_search.text(),
            )
            self._load_file(image_or_label_path=file_or_dir)

    def _open_dir_with_dialog(self, _value: bool = False) -> None:
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
                self.tr("%s - Open Directory") % __appname__,
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

    def import_dropped_image_files(self, image_files: list[str]) -> None:
        extensions = tuple(
            f".{fmt.toStdString().lower()}"
            for fmt in QtGui.QImageReader.supportedImageFormats()
        )
        already_loaded = set(self.image_list)
        new_files = [
            path
            for path in image_files
            if path not in already_loaded and path.lower().endswith(extensions)
        ]

        self._image_path = None
        for path in new_files:
            self._docks.file_list.addItem(
                _make_image_list_item(image_path=path, output_dir=self._output_dir)
            )

        if len(self.image_list) > 1:
            self._actions.open_next_img.setEnabled(True)
            self._actions.open_prev_img.setEnabled(True)

        self._open_next_image()

    def _import_images_from_dir(
        self, root_dir: str | None, pattern: str | None = None
    ) -> None:
        self._actions.open_next_img.setEnabled(True)
        self._actions.open_prev_img.setEnabled(True)

        if not self._can_continue() or not root_dir:
            return

        self._docks.file_dock.setEnabled(True)
        self._docks.file_dock.setToolTip("")

        self._prev_opened_dir = root_dir
        self._image_path = None
        self._docks.file_list.clear()

        image_paths = _scan_image_files(root_dir=root_dir)
        if pattern:
            try:
                image_paths = [x for x in image_paths if re.search(pattern, x)]
            except re.error:
                pass
        for image_path in image_paths:
            item = QtWidgets.QListWidgetItem(image_path)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            if QtCore.QFile.exists(
                _resolve_label_path(
                    image_or_label_path=image_path, output_dir=self._output_dir
                )
            ):
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)
            self._docks.file_list.addItem(item)

    def _update_status_stats(self, mouse_pos: QtCore.QPointF) -> None:
        stats: list[str] = []
        stats.append(f"mode={self._canvas_widgets.canvas.mode.name}")
        stats.append(f"x={mouse_pos.x():6.1f}, y={mouse_pos.y():6.1f}")
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

        default_flags: dict[str, bool] = {}
        if label_flags:
            for pattern, keys in label_flags.items():
                if not isinstance(shape.label, str):
                    logger.warning("shape.label is not str: {}", shape.label)
                    continue
                if re.match(pattern, shape.label):
                    for key in keys:
                        default_flags[key] = False
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


def _rgb_from_colormap_id(*, label_id: int) -> tuple[int, int, int]:
    r, g, b = LABEL_COLORMAP[label_id % len(LABEL_COLORMAP)].tolist()
    return r, g, b


def _rgb_from_label_colors(
    *, label: str, label_colors: dict[str, list[int]] | None
) -> tuple[int, int, int] | None:
    if not label_colors or label not in label_colors:
        return None
    rgb = label_colors[label]
    if len(rgb) != 3 or not all(0 <= c <= 255 for c in rgb):
        raise ValueError(f"Color for label must be 0-255 RGB tuple, but got: {rgb}")
    r, g, b = rgb
    return r, g, b


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


def _resolve_label_path(*, image_or_label_path: str, output_dir: Path | None) -> str:
    if is_label_file_path(filename=image_or_label_path):
        return image_or_label_path
    image_path = Path(image_or_label_path)
    parent = output_dir if output_dir is not None else image_path.parent
    return str(parent / f"{image_path.stem}{LABEL_FILE_SUFFIX}")


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


def _shape_to_dict(shape: Shape) -> ShapeDict:
    assert shape.label is not None
    return ShapeDict(
        label=shape.label,
        points=shape.points.tolist(),
        shape_type=shape.shape_type,
        flags=shape.flags or {},
        description=shape.description or "",
        group_id=shape.group_id,
        mask=shape.mask,
        other_data=shape.other_data,
    )


def _scan_image_files(root_dir: str) -> list[str]:
    extensions: list[str] = [
        f".{fmt.toStdString().lower()}"
        for fmt in QtGui.QImageReader.supportedImageFormats()
    ]

    images: list[str] = []
    for root, dirs, files in os.walk(root_dir):
        for file in files:
            if file.lower().endswith(tuple(extensions)):
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
