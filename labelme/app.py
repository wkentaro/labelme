from __future__ import annotations

import enum
import functools
import html
import math
import os
import platform
import re
import subprocess
import time
import webbrowser
from collections.abc import Callable
from pathlib import Path
from typing import Any
from typing import Final
from typing import Literal
from typing import NamedTuple
from typing import TypeAlias
from typing import cast
from typing import get_args

import imgviz
import natsort
import numpy as np
import osam
from loguru import logger
from numpy.typing import NDArray
from PyQt5 import QtCore
from PyQt5 import QtGui
from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QMessageBox

from labelme import __appname__
from labelme import __version__
from labelme._automation import bbox_from_text
from labelme._automation._osam_session import OsamSession
from labelme._label_file import LabelFile
from labelme._label_file import LabelFileError
from labelme._label_file import ShapeDict
from labelme.config import load_config
from labelme.shape import Shape
from labelme.widgets import AiAssistedAnnotationWidget
from labelme.widgets import AiTextToAnnotationWidget
from labelme.widgets import BrightnessContrastDialog
from labelme.widgets import Canvas
from labelme.widgets import FileDialogPreview
from labelme.widgets import LabelDialog
from labelme.widgets import LabelListWidget
from labelme.widgets import LabelListWidgetItem
from labelme.widgets import StatusStats
from labelme.widgets import ToolBar
from labelme.widgets import UniqueLabelQListWidget
from labelme.widgets import ZoomWidget
from labelme.widgets import download_ai_model

from . import utils

# handle high-dpi scaling issue
# https://leomoon.com/journal/python/high-dpi-scaling-in-pyqt5
if hasattr(QtCore.Qt, "AA_EnableHighDpiScaling"):
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
if hasattr(QtCore.Qt, "AA_UseHighDpiPixmaps"):
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)


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
    about: QtWidgets.QAction
    save: QtWidgets.QAction
    save_as: QtWidgets.QAction
    save_auto: QtWidgets.QAction
    save_with_image_data: QtWidgets.QAction
    change_output_dir: QtWidgets.QAction
    open: QtWidgets.QAction
    close: QtWidgets.QAction
    delete_file: QtWidgets.QAction
    toggle_keep_prev_mode: QtWidgets.QAction
    toggle_keep_prev_brightness_contrast: QtWidgets.QAction
    delete: QtWidgets.QAction
    edit: QtWidgets.QAction
    duplicate: QtWidgets.QAction
    copy: QtWidgets.QAction
    paste: QtWidgets.QAction
    undo_last_point: QtWidgets.QAction
    undo: QtWidgets.QAction
    remove_point: QtWidgets.QAction
    create_mode: QtWidgets.QAction
    edit_mode: QtWidgets.QAction
    create_rectangle_mode: QtWidgets.QAction
    create_circle_mode: QtWidgets.QAction
    create_line_mode: QtWidgets.QAction
    create_point_mode: QtWidgets.QAction
    create_line_strip_mode: QtWidgets.QAction
    create_ai_points_to_shape_mode: QtWidgets.QAction
    create_ai_box_to_shape_mode: QtWidgets.QAction
    open_next_img: QtWidgets.QAction
    open_prev_img: QtWidgets.QAction
    keep_prev_scale: QtWidgets.QAction
    fit_window: QtWidgets.QAction
    fit_width: QtWidgets.QAction
    brightness_contrast: QtWidgets.QAction
    zoom_in: QtWidgets.QAction
    zoom_out: QtWidgets.QAction
    zoom_org: QtWidgets.QAction
    reset_layout: QtWidgets.QAction
    fill_drawing: QtWidgets.QAction
    hide_all: QtWidgets.QAction
    show_all: QtWidgets.QAction
    toggle_all: QtWidgets.QAction
    open_dir: QtWidgets.QAction
    zoom_widget_action: QtWidgets.QWidgetAction
    draw: list[tuple[str, QtWidgets.QAction]]
    zoom: tuple[ZoomWidget | QtWidgets.QAction, ...]
    on_load_active: tuple[QtWidgets.QAction, ...]
    on_shapes_present: tuple[QtWidgets.QAction, ...]
    context_menu: tuple[QtWidgets.QAction, ...]
    edit_menu: tuple[QtWidgets.QAction | None, ...]


class _Menus(NamedTuple):
    file: QtWidgets.QMenu
    edit: QtWidgets.QMenu
    view: QtWidgets.QMenu
    help: QtWidgets.QMenu
    label_list: QtWidgets.QMenu


class MainWindow(QtWidgets.QMainWindow):
    _config_file: Path | None
    _config: dict

    _text_osam_session: OsamSession | None = None
    _is_changed: bool = False
    _copied_shapes: list[Shape]
    _zoom_mode: _ZoomMode
    _prev_opened_dir: str | None
    _canvas_widgets: _CanvasWidgets
    _status_bar: _StatusBarWidgets
    _docks: _DockWidgets
    _actions: _Actions
    _menus: _Menus
    _scalers: dict[_ZoomMode, Callable[[], float]]
    _label_dialog: LabelDialog
    _ai_annotation: AiAssistedAnnotationWidget
    _ai_text: AiTextToAnnotationWidget

    _output_dir: Path | None
    _image: QtGui.QImage
    _label_file: LabelFile | None
    _image_path: str | None
    _prev_image_path: str | None
    _other_data: dict | None
    _zoom_values: dict[str, tuple[_ZoomMode, int]]
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

        # set default shape colors
        Shape.line_color = QtGui.QColor(*self._config["shape"]["line_color"])
        Shape.fill_color = QtGui.QColor(*self._config["shape"]["fill_color"])
        Shape.select_line_color = QtGui.QColor(
            *self._config["shape"]["select_line_color"]
        )
        Shape.select_fill_color = QtGui.QColor(
            *self._config["shape"]["select_fill_color"]
        )
        Shape.vertex_fill_color = QtGui.QColor(
            *self._config["shape"]["vertex_fill_color"]
        )
        Shape.hvertex_fill_color = QtGui.QColor(
            *self._config["shape"]["hvertex_fill_color"]
        )

        # Set point size from config file
        Shape.point_size = self._config["shape"]["point_size"]

        self._copied_shapes = []

        self._label_dialog = LabelDialog(
            parent=self,
            labels=self._config["labels"],
            sort_labels=self._config["sort_labels"],
            show_text_field=self._config["show_label_text_field"],
            completion=self._config["label_completion"],
            fit_to_content=self._config["fit_to_content"],
            flags=self._config["label_flags"],
        )

        self._prev_opened_dir = None
        self._docks = self._setup_dock_widgets()

        self.setAcceptDrops(True)
        self._canvas_widgets = self._setup_canvas()

        self._actions = self._setup_actions()
        self._scalers = {
            _ZoomMode.FIT_WINDOW: self.scaleFitWindow,
            _ZoomMode.FIT_WIDTH: self.scaleFitWidth,
            _ZoomMode.MANUAL_ZOOM: lambda: 1,
        }
        self._menus = self._setup_menus()

        self._ai_annotation = AiAssistedAnnotationWidget(
            default_model=self._config["ai"]["default"],
            on_model_changed=self._canvas_widgets.canvas.set_ai_model_name,
            on_output_format_changed=self._canvas_widgets.canvas.set_ai_output_format,
            parent=self,
        )
        self._ai_annotation.setEnabled(False)

        self._ai_text = AiTextToAnnotationWidget(
            on_submit=self._submit_ai_prompt, parent=self
        )
        self._ai_text.setEnabled(False)

        self._setup_toolbars()

        self._status_bar = self._setup_status_bar()

        self._setup_app_state(file_or_dir=file_or_dir, output_dir=output_dir)

        self._canvas_widgets.zoom_widget.valueChanged.connect(self._paint_canvas)

        self.populateModeActions()

    def _setup_actions(self) -> _Actions:
        action = functools.partial(utils.newAction, self)
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
            slot=self.enableSaveImageWithData,
            tip=self.tr("Save image data in label file"),
            checkable=True,
            checked=self._config["with_image_data"],
        )
        change_output_dir = action(
            text=self.tr("&Change Output Dir"),
            slot=self.changeOutputDirDialog,
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
            slot=self.closeFile,
            shortcut=shortcuts["close"],
            icon="phosphor/x-circle.svg",
            tip=self.tr("Close current file"),
        )
        delete_file = action(
            text=self.tr("&Delete File"),
            slot=self.deleteFile,
            shortcut=shortcuts["delete_file"],
            icon="phosphor/file-x.svg",
            tip=self.tr("Delete current label file"),
            enabled=False,
        )
        toggle_keep_prev_mode = action(
            text=self.tr("Keep Previous Annotation"),
            slot=self.toggleKeepPrevMode,
            shortcut=shortcuts["toggle_keep_prev_mode"],
            icon=None,
            tip=self.tr('Toggle "keep previous annotation" mode'),
            checkable=True,
        )
        toggle_keep_prev_mode.setChecked(self._config["keep_prev"])
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
            self.deleteSelectedShape,
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
            self.duplicateSelectedShape,
            shortcuts["duplicate_shape"],
            icon="phosphor/copy.svg",
            tip=self.tr("Create a duplicate of the selected shapes"),
            enabled=False,
        )
        copy = action(
            self.tr("Copy Shapes"),
            self.copySelectedShape,
            shortcuts["copy_shape"],
            "copy_clipboard",
            self.tr("Copy selected shapes to clipboard"),
            enabled=False,
        )
        paste = action(
            self.tr("Paste Shapes"),
            self.pasteSelectedShape,
            shortcuts["paste_shape"],
            "paste",
            self.tr("Paste copied shapes"),
            enabled=False,
        )
        undo_last_point = action(
            self.tr("Undo last point"),
            self._canvas_widgets.canvas.undoLastPoint,
            shortcuts["undo_last_point"],
            icon="phosphor/arrow-u-up-left.svg",
            tip=self.tr("Undo last drawn point"),
            enabled=False,
        )
        undo = action(
            self.tr("Undo\n"),
            self.undoShapeEdit,
            shortcuts["undo"],
            icon="phosphor/arrow-u-up-left.svg",
            tip=self.tr("Undo last add and edit of shape"),
            enabled=False,
        )
        remove_point = action(
            text=self.tr("Remove Selected Point"),
            slot=self.removeSelectedPoint,
            shortcut=shortcuts["remove_selected_point"],
            icon="phosphor/trash.svg",
            tip=self.tr("Remove selected point from polygon"),
            enabled=False,
        )
        create_mode = action(
            text=self.tr("Polygon"),
            slot=lambda: self._switch_canvas_mode(edit=False, createMode="polygon"),
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
            slot=lambda: self._switch_canvas_mode(edit=False, createMode="rectangle"),
            shortcut=shortcuts["create_rectangle"],
            icon="phosphor/rectangle.svg",
            tip=self.tr("Start drawing rectangles"),
            enabled=False,
        )
        create_circle_mode = action(
            text=self.tr("Circle"),
            slot=lambda: self._switch_canvas_mode(edit=False, createMode="circle"),
            shortcut=shortcuts["create_circle"],
            icon="phosphor/circle.svg",
            tip=self.tr("Start drawing circles"),
            enabled=False,
        )
        create_line_mode = action(
            text=self.tr("Line"),
            slot=lambda: self._switch_canvas_mode(edit=False, createMode="line"),
            shortcut=shortcuts["create_line"],
            icon="phosphor/line-segment.svg",
            tip=self.tr("Start drawing lines"),
            enabled=False,
        )
        create_point_mode = action(
            text=self.tr("Point"),
            slot=lambda: self._switch_canvas_mode(edit=False, createMode="point"),
            shortcut=shortcuts["create_point"],
            icon="phosphor/circles-four.svg",
            tip=self.tr("Start drawing points"),
            enabled=False,
        )
        create_line_strip_mode = action(
            text=self.tr("LineStrip"),
            slot=lambda: self._switch_canvas_mode(edit=False, createMode="linestrip"),
            shortcut=shortcuts["create_linestrip"],
            icon="phosphor/line-segments.svg",
            tip=self.tr("Start drawing linestrip. Ctrl+LeftClick ends creation."),
            enabled=False,
        )
        create_ai_points_to_shape_mode = action(
            self.tr("AI-Points"),
            lambda: self._switch_canvas_mode(
                edit=False, createMode="ai_points_to_shape"
            ),
            None,
            "ai-points.svg",
            self.tr("Click points to segment object. Ctrl+LeftClick ends creation."),
            enabled=False,
        )
        create_ai_box_to_shape_mode = action(
            self.tr("AI-Box"),
            lambda: self._switch_canvas_mode(edit=False, createMode="ai_box_to_shape"),
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
        keep_prev_scale = action(
            self.tr("&Keep Previous Scale"),
            self.enableKeepPrevScale,
            tip=self.tr("Keep previous zoom scale"),
            checkable=True,
            checked=self._config["keep_prev_scale"],
            enabled=True,
        )
        fit_window = action(
            self.tr("&Fit Window"),
            self.setFitWindow,
            shortcuts["fit_window"],
            icon="phosphor/frame-corners.svg",
            tip=self.tr("Zoom follows window size"),
            checkable=True,
            enabled=False,
        )
        fit_width = action(
            self.tr("Fit &Width"),
            self.setFitWidth,
            shortcuts["fit_width"],
            icon="frame-arrows-horizontal.svg",
            tip=self.tr("Zoom follows window width"),
            checkable=True,
            enabled=False,
        )
        brightness_contrast = action(
            self.tr("&Brightness Contrast"),
            self.brightnessContrast,
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
            self._canvas_widgets.canvas.setFillDrawing,
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
            functools.partial(self.toggleShapes, False),
            shortcuts["hide_all_shapes"],
            icon="phosphor/eye.svg",
            tip=self.tr("Hide all shapes"),
            enabled=False,
        )
        show_all = action(
            self.tr("&Show\nShapes"),
            functools.partial(self.toggleShapes, True),
            shortcuts["show_all_shapes"],
            icon="phosphor/eye.svg",
            tip=self.tr("Show all shapes"),
            enabled=False,
        )
        toggle_all = action(
            self.tr("&Toggle\nShapes"),
            functools.partial(self.toggleShapes, None),
            shortcuts["toggle_all_shapes"],
            icon="phosphor/eye.svg",
            tip=self.tr("Toggle all shapes"),
            enabled=False,
        )

        zoom_widget_action = QtWidgets.QWidgetAction(self)
        zoom_box_layout = QtWidgets.QVBoxLayout()
        zoom_label = QtWidgets.QLabel(self.tr("Zoom"))
        zoom_label.setAlignment(Qt.AlignCenter)
        zoom_box_layout.addWidget(zoom_label)
        zoom_box_layout.addWidget(self._canvas_widgets.zoom_widget)
        zoom_widget_action.setDefaultWidget(QtWidgets.QWidget())
        zoom_widget_action.defaultWidget().setLayout(zoom_box_layout)
        self._canvas_widgets.zoom_widget.setWhatsThis(
            str(
                self.tr(
                    "Zoom in or out of the image. Also accessible with "
                    "{} and {} from the canvas."
                )
            ).format(
                utils.fmtShortcut(f"{shortcuts['zoom_in']},{shortcuts['zoom_out']}"),
                utils.fmtShortcut(self.tr("Ctrl+Wheel")),
            )
        )
        self._canvas_widgets.zoom_widget.setEnabled(False)

        self._zoom_mode = _ZoomMode.FIT_WINDOW
        fit_window.setChecked(Qt.Checked)

        self._canvas_widgets.canvas.vertexSelected.connect(remove_point.setEnabled)

        draw = [
            ("polygon", create_mode),
            ("rectangle", create_rectangle_mode),
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
            toggle_keep_prev_mode,
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
            toggle_keep_prev_mode=toggle_keep_prev_mode,
            toggle_keep_prev_brightness_contrast=toggle_keep_prev_brightness_contrast,
            delete=delete,
            edit=edit,
            duplicate=duplicate,
            copy=copy,
            paste=paste,
            undo_last_point=undo_last_point,
            undo=undo,
            remove_point=remove_point,
            create_mode=create_mode,
            edit_mode=edit_mode,
            create_rectangle_mode=create_rectangle_mode,
            create_circle_mode=create_circle_mode,
            create_line_mode=create_line_mode,
            create_point_mode=create_point_mode,
            create_line_strip_mode=create_line_strip_mode,
            create_ai_points_to_shape_mode=create_ai_points_to_shape_mode,
            create_ai_box_to_shape_mode=create_ai_box_to_shape_mode,
            open_next_img=open_next_img,
            open_prev_img=open_prev_img,
            keep_prev_scale=keep_prev_scale,
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
        action = functools.partial(utils.newAction, self)
        shortcuts = self._config["shortcuts"]

        quit_ = action(
            text=self.tr("&Quit"),
            slot=self.close,
            shortcut=shortcuts["quit"],
            icon=None,
            tip=self.tr("Quit application"),
        )
        open_config = action(
            text=self.tr("Preferences…"),
            slot=self._open_config_file,
            shortcut="Ctrl+," if platform.system() == "Darwin" else "Ctrl+Shift+,",
            icon=None,
            tip=self.tr("Open config file in text editor"),
        )
        open_config.setMenuRole(QtWidgets.QAction.PreferencesRole)
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
        utils.addActions(label_menu, (self._actions.edit, self._actions.delete))
        self._docks.label_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._docks.label_list.customContextMenuRequested.connect(self.popLabelListMenu)

        utils.addActions(
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
        utils.addActions(help_menu, (help_, self._actions.about))
        utils.addActions(
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
                self._actions.keep_prev_scale,
                None,
                self._actions.fit_window,
                self._actions.fit_width,
                None,
                self._actions.brightness_contrast,
                self._actions.toggle_keep_prev_brightness_contrast,
            ),
        )

        utils.addActions(
            self._canvas_widgets.canvas.menus[0], self._actions.context_menu
        )
        utils.addActions(
            self._canvas_widgets.canvas.menus[1],
            (
                action("&Copy here", self.copyShape),
                action("&Move here", self.moveShape),
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
            Qt.TopToolBarArea,
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
            Qt.LeftToolBarArea,
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
                orientation=Qt.Vertical,
                button_style=Qt.ToolButtonTextUnderIcon,
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
        self._label_file = None
        self._image_path = None
        self._prev_image_path = None
        self._other_data = None
        self._zoom_values = {}
        self._brightness_contrast_values = {}
        self._scroll_values = {
            Qt.Horizontal: {},
            Qt.Vertical: {},
        }

        if self._config["file_search"]:
            self._docks.file_search.setText(self._config["file_search"])

        self._default_state = self.saveState()
        #
        # XXX: Could be completely declarative.
        # Restore application settings.
        self.settings = QtCore.QSettings("labelme", "labelme")
        #
        # Bump this when dock/toolbar layout changes to reset window state
        # for users upgrading from an older version.
        SETTINGS_VERSION: int = 1
        if self.settings.value("settingsVersion", 0, type=int) != SETTINGS_VERSION:
            self._reset_layout()
            self.settings.setValue("settingsVersion", SETTINGS_VERSION)
        #
        self.resize(self.settings.value("window/size", QtCore.QSize(900, 500)))
        self.move(self.settings.value("window/position", QtCore.QPoint(0, 0)))
        self.restoreState(self.settings.value("window/state", QtCore.QByteArray()))
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
        )
        canvas.zoomRequest.connect(self._zoom_requested)
        canvas.mouseMoved.connect(self._update_status_stats)
        canvas.statusUpdated.connect(
            lambda text: self._status_bar.message.setText(text)
        )

        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidget(canvas)
        scroll_area.setWidgetResizable(True)
        scroll_bars = {
            Qt.Vertical: scroll_area.verticalScrollBar(),
            Qt.Horizontal: scroll_area.horizontalScrollBar(),
        }
        canvas.scrollRequest.connect(self.scrollRequest)

        canvas.newShape.connect(self.newShape)
        canvas.shapeMoved.connect(self.setDirty)
        canvas.selectionChanged.connect(self.shapeSelectionChanged)
        canvas.drawingPolygon.connect(self.toggleDrawingSensitive)

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
        flag_list.itemChanged.connect(self.setDirty)

        label_list = LabelListWidget()
        label_list.itemSelectionChanged.connect(self._label_selection_changed)
        label_list.itemDoubleClicked.connect(self._edit_label)
        label_list.itemChanged.connect(self.labelItemChanged)
        label_list.itemDropped.connect(self.labelOrderChanged)
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
        file_search.textChanged.connect(self.fileSearchChanged)
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
            features = QtWidgets.QDockWidget.DockWidgetFeatures()
            if self._config[config_key]["closable"]:
                features = features | QtWidgets.QDockWidget.DockWidgetClosable
            if self._config[config_key]["floatable"]:
                features = features | QtWidgets.QDockWidget.DockWidgetFloatable
            if self._config[config_key]["movable"]:
                features = features | QtWidgets.QDockWidget.DockWidgetMovable
            dock_widget.setFeatures(features)
            if self._config[config_key]["show"] is False:
                dock_widget.setVisible(False)
            self.addDockWidget(Qt.RightDockWidgetArea, dock_widget)

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
            config = load_config(
                config_file=config_file, config_overrides=config_overrides or {}
            )
        except ValueError as e:
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Warning)
            msg_box.setWindowTitle(self.tr("Configuration Errors"))
            msg_box.setText(
                self.tr(
                    "Errors were found while loading the configuration. "
                    "Please review the errors below and reload your configuration or "
                    "ignore the erroneous lines."
                )
            )
            msg_box.setInformativeText(str(e))
            msg_box.setStandardButtons(QMessageBox.Ignore)
            msg_box.setModal(False)
            msg_box.show()

            config_file = None
            config_overrides = {}
            config = load_config(
                config_file=config_file, config_overrides=config_overrides
            )
        return config_file, config

    def menu(
        self,
        title: str,
        actions: tuple[QtWidgets.QAction | QtWidgets.QMenu | None, ...] | None = None,
    ) -> QtWidgets.QMenu:
        menu = self.menuBar().addMenu(title)
        if actions:
            utils.addActions(menu, actions)
        return menu

    # Support Functions

    def noShapes(self) -> bool:
        return not len(self._docks.label_list)

    def populateModeActions(self) -> None:
        self._canvas_widgets.canvas.menus[0].clear()
        utils.addActions(
            self._canvas_widgets.canvas.menus[0], self._actions.context_menu
        )
        self._menus.edit.clear()
        actions = (
            *[draw_action for _, draw_action in self._actions.draw],
            self._actions.edit_mode,
            *self._actions.edit_menu,
        )
        utils.addActions(self._menus.edit, actions)

    def _get_window_title(self, dirty: bool) -> str:
        window_title: str = __appname__
        if self._image_path:
            window_title = f"{window_title} - {self._image_path}"
            if self._docks.file_list.count() and self._docks.file_list.currentItem():
                window_title = (
                    f"{window_title} "
                    f"[{self._docks.file_list.currentRow() + 1}"
                    f"/{self._docks.file_list.count()}]"
                )
        if dirty:
            window_title = f"{window_title}*"
        return window_title

    def setDirty(self) -> None:
        # Even if we autosave the file, we keep the ability to undo
        self._actions.undo.setEnabled(self._canvas_widgets.canvas.isShapeRestorable)

        if self._actions.save_auto.isChecked():
            assert self._image_path is not None
            self.saveLabels(
                label_path=_resolve_label_path(
                    image_or_label_path=self._image_path,
                    output_dir=self._output_dir,
                )
            )
            return
        self._is_changed = True
        self._actions.save.setEnabled(True)
        self.setWindowTitle(self._get_window_title(dirty=True))

    def setClean(self) -> None:
        self._is_changed = False
        self._actions.save.setEnabled(False)
        for _, action in self._actions.draw:
            action.setEnabled(True)
        self.setWindowTitle(self._get_window_title(dirty=False))

        if self.hasLabelFile():
            self._actions.delete_file.setEnabled(True)
        else:
            self._actions.delete_file.setEnabled(False)

    def toggleActions(self, value: bool = True) -> None:
        """Enable/Disable widgets which depend on an opened image."""
        for z in self._actions.zoom:
            z.setEnabled(value)
        for action in self._actions.on_load_active:
            action.setEnabled(value)

    def queueEvent(self, function: Callable[[], None]) -> None:
        QtCore.QTimer.singleShot(0, function)

    def show_status_message(self, message: str, delay: int = 500) -> None:
        self.statusBar().showMessage(message, delay)

    def _submit_ai_prompt(self, _: bool) -> None:
        create_mode = self._canvas_widgets.canvas.createMode
        shape_type: Literal["rectangle", "polygon", "mask"]
        if create_mode in _AI_CREATE_MODES:
            shape_type = self._ai_annotation.output_format
        elif create_mode in get_args(_TextToAnnotationCreateMode):
            shape_type = cast(_TextToAnnotationCreateMode, create_mode)
        else:
            logger.warning("Unsupported createMode={!r}", create_mode)
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
            self._text_osam_session = OsamSession(model_name=model_name)

        boxes, scores, labels, masks = bbox_from_text.get_bboxes_from_texts(
            session=self._text_osam_session,
            image=utils.img_qt_to_arr(self._image)[:, :, :3],
            image_id=str(hash(self._image_path)),
            texts=texts,
        )

        SCORE_FOR_EXISTING_SHAPE: float = 1.01
        for shape in self._canvas_widgets.canvas.shapes:
            if shape.shape_type != shape_type or shape.label not in texts:
                continue
            points: NDArray[np.float64] = np.array(
                [[p.x(), p.y()] for p in shape.points]
            )
            xmin, ymin = points.min(axis=0)
            xmax, ymax = points.max(axis=0)
            box = np.array([xmin, ymin, xmax, ymax], dtype=np.float32)
            boxes = np.r_[boxes, [box]]
            scores = np.r_[scores, [SCORE_FOR_EXISTING_SHAPE]]
            labels = np.r_[labels, [texts.index(shape.label)]]

        boxes, scores, labels, indices = bbox_from_text.nms_bboxes(
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

        if masks is not None:
            masks = [masks[i] for i in indices]
        del indices

        shapes: list[Shape] = bbox_from_text.get_shapes_from_bboxes(
            boxes=boxes,
            scores=scores,
            labels=labels,
            texts=texts,
            masks=masks,
            shape_type=shape_type,
        )

        self._canvas_widgets.canvas.storeShapes()
        self._load_shapes(shapes, replace=False)
        self.setDirty()

    def resetState(self) -> None:
        self._docks.label_list.clear()
        self._image_path = None
        self.imageData = None
        self._label_file = None
        self._other_data = None
        self._canvas_widgets.canvas.resetState()

    def currentItem(self) -> LabelListWidgetItem | None:
        items = self._docks.label_list.selectedItems()
        if items:
            return items[0]
        return None

    # Callbacks

    def undoShapeEdit(self) -> None:
        self._canvas_widgets.canvas.restoreShape()
        self._docks.label_list.clear()
        self._load_shapes(self._canvas_widgets.canvas.shapes)
        self._actions.undo.setEnabled(self._canvas_widgets.canvas.isShapeRestorable)

    def tutorial(self) -> None:
        url = "https://github.com/labelmeai/labelme/tree/main/examples/tutorial"  # NOQA
        webbrowser.open(url)

    def toggleDrawingSensitive(self, drawing: bool = True) -> None:
        """Toggle drawing sensitive.

        In the middle of drawing, toggling between modes should be disabled.
        """
        self._actions.edit_mode.setEnabled(not drawing)
        self._actions.undo_last_point.setEnabled(drawing)
        self._actions.undo.setEnabled(not drawing)
        self._actions.delete.setEnabled(not drawing)

    def _switch_canvas_mode(
        self, edit: bool = True, createMode: str | None = None
    ) -> None:
        if createMode == "ai_points_to_shape":
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
        self._canvas_widgets.canvas.setEditing(edit)
        if createMode is not None:
            self._canvas_widgets.canvas.createMode = createMode
        if edit:
            for _, draw_action in self._actions.draw:
                draw_action.setEnabled(True)
        else:
            for draw_mode, draw_action in self._actions.draw:
                draw_action.setEnabled(createMode != draw_mode)
        self._actions.edit_mode.setEnabled(not edit)
        self._ai_text.setEnabled(
            not edit
            and createMode
            in (*get_args(_TextToAnnotationCreateMode), *_AI_CREATE_MODES)
        )
        self._ai_annotation.setEnabled(not edit and createMode in _AI_CREATE_MODES)
        if createMode == "ai_points_to_shape":
            self._ai_annotation.set_disabled_models(_AI_MODELS_WITHOUT_POINT_SUPPORT)
        else:
            self._ai_annotation.set_disabled_models(())

    def _highlight_ai_buttons(self, highlight: bool) -> None:
        HIGHLIGHT_COLOR: Final = "#FFFFCC"
        BORDER_COLOR: Final = "#E6E6A0"
        bg = HIGHLIGHT_COLOR if highlight else "transparent"
        border = BORDER_COLOR if highlight else "transparent"
        style = (
            "QToolButton:!checked:!pressed {"
            f" background-color: {bg}; border: 1px solid {border};"
            " }"
        )
        for mode, action in self._actions.draw:
            if mode in _AI_CREATE_MODES:
                for widget in action.associatedWidgets():
                    if isinstance(widget, QtWidgets.QToolButton):
                        widget.setStyleSheet(style)

    def popLabelListMenu(self, point: QtCore.QPoint) -> None:
        # PyQt5 stubs type QMenu.exec() argument too narrowly
        self._menus.label_list.exec(self._docks.label_list.mapToGlobal(point))  # ty: ignore[invalid-argument-type]

    def validateLabel(self, label: str) -> bool:
        # no validation
        if self._config["validate_label"] is None:
            return True

        for i in range(self._docks.unique_label_list.count()):
            # PyQt5 stubs: item() typed as Optional and .data() unrecognized
            label_i = self._docks.unique_label_list.item(i).data(Qt.UserRole)  # ty: ignore[unresolved-attribute]
            if self._config["validate_label"] in ["exact"]:
                if label_i == label:
                    return True
        return False

    def _edit_label(self, value: object | None = None) -> None:
        items = self._docks.label_list.selectedItems()
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
            self._label_dialog.labelList.setDisabled(True)
        if not edit_group_id:
            self._label_dialog.edit_group_id.setDisabled(True)
        if not edit_description:
            self._label_dialog.editDescription.setDisabled(True)

        text, flags, group_id, description = self._label_dialog.popUp(
            text=first_shape.label if edit_text else "",
            flags=first_shape.flags if edit_flags else None,
            group_id=first_shape.group_id if edit_group_id else None,
            description=first_shape.description if edit_description else None,
            flags_disabled=not edit_flags,
        )

        if not edit_text:
            self._label_dialog.edit.setDisabled(False)
            self._label_dialog.labelList.setDisabled(False)
        if not edit_group_id:
            self._label_dialog.edit_group_id.setDisabled(False)
        if not edit_description:
            self._label_dialog.editDescription.setDisabled(False)

        if text is None:
            assert flags is None
            assert group_id is None
            assert description is None
            return

        if not self.validateLabel(text):
            self.errorMessage(
                self.tr("Invalid label"),
                self.tr("Invalid label '{}' with validation type '{}'").format(
                    text, self._config["validate_label"]
                ),
            )
            return

        self._canvas_widgets.canvas.storeShapes()
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

            self._update_shape_color(shape)
            assert shape.label is not None
            if shape.group_id is None:
                r, g, b = shape.fill_color.getRgb()[:3]
                item.setText(
                    f"{html.escape(shape.label)} "
                    f'<font color="#{r:02x}{g:02x}{b:02x}">●</font>'
                )
            else:
                item.setText(f"{shape.label} ({shape.group_id})")
            self.setDirty()
            if self._docks.unique_label_list.find_label_item(shape.label) is None:
                self._docks.unique_label_list.add_label_item(
                    label=shape.label,
                    color=self._get_rgb_by_label(
                        label=shape.label,
                        unique_label_list=self._docks.unique_label_list,
                    ),
                )

    def fileSearchChanged(self) -> None:
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
    def shapeSelectionChanged(self, selected_shapes: list[Shape]) -> None:
        self._docks.label_list.itemSelectionChanged.disconnect(
            self._label_selection_changed
        )
        for shape in self._canvas_widgets.canvas.selectedShapes:
            shape.selected = False
        self._docks.label_list.clearSelection()
        self._canvas_widgets.canvas.selectedShapes = selected_shapes
        for shape in self._canvas_widgets.canvas.selectedShapes:
            shape.selected = True
            item = self._docks.label_list.findItemByShape(shape)
            self._docks.label_list.selectItem(item)
            self._docks.label_list.scrollToItem(item)
        self._docks.label_list.itemSelectionChanged.connect(
            self._label_selection_changed
        )
        n_selected = len(selected_shapes) > 0
        self._actions.delete.setEnabled(n_selected)
        self._actions.duplicate.setEnabled(n_selected)
        self._actions.copy.setEnabled(n_selected)
        self._actions.edit.setEnabled(n_selected)

    def addLabel(self, shape: Shape) -> None:
        assert shape.label is not None
        if shape.group_id is None:
            text = shape.label
        else:
            text = f"{shape.label} ({shape.group_id})"
        label_list_item = LabelListWidgetItem(text, shape)
        self._docks.label_list.addItem(label_list_item)
        if self._docks.unique_label_list.find_label_item(shape.label) is None:
            self._docks.unique_label_list.add_label_item(
                label=shape.label,
                color=self._get_rgb_by_label(
                    label=shape.label,
                    unique_label_list=self._docks.unique_label_list,
                ),
            )
        self._label_dialog.addLabelHistory(shape.label)
        for action in self._actions.on_shapes_present:
            action.setEnabled(True)

        self._update_shape_color(shape)
        r, g, b = shape.fill_color.getRgb()[:3]
        label_list_item.setText(
            f'{html.escape(text)} <font color="#{r:02x}{g:02x}{b:02x}">●</font>'
        )

    def _update_shape_color(self, shape: Shape) -> None:
        assert shape.label is not None
        r, g, b = self._get_rgb_by_label(
            shape.label, unique_label_list=self._docks.unique_label_list
        )
        shape.line_color = QtGui.QColor(r, g, b)
        shape.vertex_fill_color = QtGui.QColor(r, g, b)
        shape.hvertex_fill_color = QtGui.QColor(255, 255, 255)
        shape.fill_color = QtGui.QColor(r, g, b, 128)
        shape.select_line_color = QtGui.QColor(255, 255, 255)
        shape.select_fill_color = QtGui.QColor(r, g, b, 155)

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
            rgb: tuple[int, int, int] = tuple(
                LABEL_COLORMAP[label_id % len(LABEL_COLORMAP)].tolist()
            )
            return rgb
        elif (
            self._config["shape_color"] == "manual"
            and self._config["label_colors"]
            and label in self._config["label_colors"]
        ):
            if not (
                len(self._config["label_colors"][label]) == 3
                and all(0 <= c <= 255 for c in self._config["label_colors"][label])
            ):
                raise ValueError(
                    "Color for label must be 0-255 RGB tuple, but got: "
                    f"{self._config['label_colors'][label]}"
                )
            return tuple(self._config["label_colors"][label])
        elif self._config["default_shape_color"]:
            return self._config["default_shape_color"]
        return (0, 255, 0)

    def remLabels(self, shapes: list[Shape]) -> None:
        self._docks.label_list.itemDropped.disconnect(self.labelOrderChanged)
        for shape in shapes:
            item = self._docks.label_list.findItemByShape(shape)
            self._docks.label_list.removeItem(item)
        self._docks.label_list.itemDropped.connect(self.labelOrderChanged)

    def _load_shapes(self, shapes: list[Shape], replace: bool = True) -> None:
        self._docks.label_list.itemSelectionChanged.disconnect(
            self._label_selection_changed
        )
        shape: Shape
        for shape in shapes:
            self.addLabel(shape)
        self._docks.label_list.clearSelection()
        self._docks.label_list.itemSelectionChanged.connect(
            self._label_selection_changed
        )
        self._canvas_widgets.canvas.loadShapes(shapes=shapes, replace=replace)

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
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if flag else Qt.Unchecked)
            widget.addItem(item)

    def saveLabels(self, label_path: str) -> bool:
        lf = LabelFile()

        shapes = [
            _shape_to_dict(s)
            for item in self._docks.label_list
            if (s := item.shape()) is not None
        ]
        flags = {}
        for i in range(self._docks.flag_list.count()):
            item = self._docks.flag_list.item(i)
            assert item
            key = item.text()
            flag = item.checkState() == Qt.Checked
            flags[key] = flag
        try:
            assert self._image_path
            label_dir = Path(label_path).parent
            imagePath = os.path.relpath(self._image_path, label_dir)
            imageData = self.imageData if self._config["with_image_data"] else None
            label_dir.mkdir(parents=True, exist_ok=True)
            lf.save(
                filename=label_path,
                shapes=shapes,
                imagePath=imagePath,
                imageData=imageData,
                imageHeight=self._image.height(),
                imageWidth=self._image.width(),
                otherData=self._other_data,
                flags=flags,
            )
            self._label_file = lf
            items = self._docks.file_list.findItems(self._image_path, Qt.MatchExactly)
            if len(items) > 0:
                if len(items) != 1:
                    raise RuntimeError("There are duplicate files.")
                items[0].setCheckState(Qt.Checked)
            return True
        except LabelFileError as e:
            self.errorMessage(
                self.tr("Error saving label data"), self.tr("<b>%s</b>") % e
            )
            return False

    def duplicateSelectedShape(self) -> None:
        self.copySelectedShape()
        self.pasteSelectedShape()

    def pasteSelectedShape(self) -> None:
        self._load_shapes(shapes=self._copied_shapes, replace=False)
        self._canvas_widgets.canvas.selectShapes(self._copied_shapes)
        self.setDirty()

    def copySelectedShape(self) -> None:
        self._copied_shapes = [
            s.copy() for s in self._canvas_widgets.canvas.selectedShapes
        ]
        self._actions.paste.setEnabled(len(self._copied_shapes) > 0)

    def _label_selection_changed(self) -> None:
        selected_shapes: list[Shape] = []
        for item in self._docks.label_list.selectedItems():
            shape = item.shape()
            assert shape is not None
            selected_shapes.append(shape)
        if selected_shapes:
            self._canvas_widgets.canvas.selectShapes(selected_shapes)
        else:
            if self._canvas_widgets.canvas.deSelectShape():
                self._canvas_widgets.canvas.update()

    def labelItemChanged(self, item: LabelListWidgetItem) -> None:
        shape = item.shape()
        assert shape is not None
        self._canvas_widgets.canvas.setShapeVisible(
            shape, item.checkState() == Qt.Checked
        )

    def labelOrderChanged(self) -> None:
        self.setDirty()
        shapes = [
            s for item in self._docks.label_list if (s := item.shape()) is not None
        ]
        self._canvas_widgets.canvas.loadShapes(shapes)

    # Callback functions:

    def newShape(self) -> None:
        """Pop-up and give focus to the label editor.

        position MUST be in global coordinates.
        """
        items = self._docks.unique_label_list.selectedItems()
        text = None
        if items:
            text = items[0].data(Qt.UserRole)
        flags = {}
        group_id = None
        description = ""
        if self._config["display_label_popup"] or not text:
            previous_text = self._label_dialog.edit.text()
            text, flags, group_id, description = self._label_dialog.popUp(text)
            if not text:
                self._label_dialog.edit.setText(previous_text)

        if text and not self.validateLabel(text):
            self.errorMessage(
                self.tr("Invalid label"),
                self.tr("Invalid label '{}' with validation type '{}'").format(
                    text, self._config["validate_label"]
                ),
            )
            text = ""
        if text:
            self._docks.label_list.clearSelection()
            assert isinstance(flags, dict)
            shapes = self._canvas_widgets.canvas.setLastLabel(text, flags)
            for shape in shapes:
                shape.group_id = group_id
                shape.description = description
                self.addLabel(shape)
            self._actions.edit_mode.setEnabled(True)
            self._actions.undo_last_point.setEnabled(False)
            self._actions.undo.setEnabled(True)
            self.setDirty()
        else:
            self._canvas_widgets.canvas.undoLastLine()
            self._canvas_widgets.canvas.shapesBackups.pop()

    def scrollRequest(self, delta: int, orientation: Qt.Orientation) -> None:
        units = -delta * 0.1  # natural scroll
        bar = self._canvas_widgets.scroll_bars[orientation]
        value = bar.value() + bar.singleStep() * units
        self.setScroll(orientation, value)

    def setScroll(self, orientation: Qt.Orientation, value: float) -> None:
        self._canvas_widgets.scroll_bars[orientation].setValue(int(value))
        if self._image_path is not None:
            self._scroll_values[orientation][self._image_path] = value

    def _set_zoom(self, value: int, pos: QtCore.QPointF | None = None) -> None:
        if self._image_path is None:
            logger.warning("image_path is None, cannot set zoom")
            return

        if pos is None:
            pos = QtCore.QPointF(
                self._canvas_widgets.canvas.visibleRegion().boundingRect().center()
            )
        canvas_width_old: int = self._canvas_widgets.canvas.width()

        self._actions.fit_width.setChecked(self._zoom_mode == _ZoomMode.FIT_WIDTH)
        self._actions.fit_window.setChecked(self._zoom_mode == _ZoomMode.FIT_WINDOW)
        self._canvas_widgets.canvas.enableDragging(
            enabled=value > int(self._scalers[_ZoomMode.FIT_WINDOW]() * 100)
        )
        self._canvas_widgets.zoom_widget.setValue(value)  # triggers self._paint_canvas
        self._zoom_values[self._image_path] = (self._zoom_mode, value)

        canvas_width_new: int = self._canvas_widgets.canvas.width()
        if canvas_width_old == canvas_width_new:
            return
        canvas_scale_factor = canvas_width_new / canvas_width_old
        x_shift: float = pos.x() * canvas_scale_factor - pos.x()
        y_shift: float = pos.y() * canvas_scale_factor - pos.y()
        self.setScroll(
            Qt.Horizontal,
            self._canvas_widgets.scroll_bars[Qt.Horizontal].value() + x_shift,
        )
        self.setScroll(
            Qt.Vertical,
            self._canvas_widgets.scroll_bars[Qt.Vertical].value() + y_shift,
        )

    def _set_zoom_to_original(self) -> None:
        self._zoom_mode = _ZoomMode.MANUAL_ZOOM
        self._set_zoom(value=100)

    def _add_zoom(self, increment: float, pos: QtCore.QPointF | None = None) -> None:
        zoom_value: int
        if increment > 1:
            zoom_value = math.ceil(self._canvas_widgets.zoom_widget.value() * increment)
        else:
            zoom_value = math.floor(
                self._canvas_widgets.zoom_widget.value() * increment
            )
        self._zoom_mode = _ZoomMode.MANUAL_ZOOM
        self._set_zoom(value=zoom_value, pos=pos)

    def _zoom_requested(self, delta: int, pos: QtCore.QPointF) -> None:
        self._add_zoom(increment=1.1 if delta > 0 else 0.9, pos=pos)

    def setFitWindow(self, value: bool = True) -> None:
        if value:
            self._actions.fit_width.setChecked(False)
        self._zoom_mode = _ZoomMode.FIT_WINDOW if value else _ZoomMode.MANUAL_ZOOM
        self._adjust_scale()

    def setFitWidth(self, value: bool = True) -> None:
        if value:
            self._actions.fit_window.setChecked(False)
        self._zoom_mode = _ZoomMode.FIT_WIDTH if value else _ZoomMode.MANUAL_ZOOM
        self._adjust_scale()

    def enableKeepPrevScale(self, enabled: bool) -> None:
        self._config["keep_prev_scale"] = enabled
        self._actions.keep_prev_scale.setChecked(enabled)

    def onNewBrightnessContrast(self, qimage: QtGui.QImage) -> None:
        self._canvas_widgets.canvas.loadPixmap(
            QtGui.QPixmap.fromImage(qimage), clear_shapes=False
        )

    def brightnessContrast(self, value: bool, is_initial_load: bool = False) -> None:
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
        assert self.imageData is not None
        dialog = BrightnessContrastDialog(
            utils.img_data_to_pil(self.imageData),
            self.onNewBrightnessContrast,
            parent=self,
        )

        if brightness is not None:
            dialog.slider_brightness.setValue(brightness)
        if contrast is not None:
            dialog.slider_contrast.setValue(contrast)

        if is_initial_load:
            dialog.onNewValue(None)
        else:
            dialog.exec_()
            brightness = dialog.slider_brightness.value()
            contrast = dialog.slider_contrast.value()

        self._brightness_contrast_values[self._image_path] = (brightness, contrast)
        logger.debug(
            "Updated states for {}: brightness={}, contrast={}",
            self._image_path,
            brightness,
            contrast,
        )

    def toggleShapes(self, value: bool | None) -> None:
        for item in self._docks.label_list:
            target = item.checkState() == Qt.Unchecked if value is None else value
            item.setCheckState(Qt.Checked if target else Qt.Unchecked)

    def _load_file(self, image_or_label_path: str) -> None:
        # changing fileListWidget loads file
        if image_or_label_path in self.imageList and (
            self._docks.file_list.currentRow()
            != self.imageList.index(image_or_label_path)
        ):
            self._docks.file_list.setCurrentRow(
                self.imageList.index(image_or_label_path)
            )
            self._docks.file_list.repaint()
            return

        prev_shapes: list[Shape] = (
            self._canvas_widgets.canvas.shapes
            if self._config["keep_prev"]
            or QtWidgets.QApplication.keyboardModifiers()
            == (Qt.ControlModifier | Qt.ShiftModifier)
            else []
        )
        self._prev_image_path = self._image_path
        self.resetState()
        self._canvas_widgets.canvas.setEnabled(False)
        if not QtCore.QFile.exists(image_or_label_path):
            self.errorMessage(
                self.tr("Error opening file"),
                self.tr("No such file: <b>%s</b>") % image_or_label_path,
            )
            return
        # assumes same name, but json extension
        self.show_status_message(
            self.tr("Loading %s...") % Path(image_or_label_path).name
        )

        t0_load_file = time.time()
        if QtCore.QFile.exists(
            label_path := _resolve_label_path(
                image_or_label_path=image_or_label_path,
                output_dir=self._output_dir,
            )
        ):
            try:
                self._label_file = LabelFile(label_path)
            except LabelFileError as e:
                self.errorMessage(
                    self.tr("Error opening file"),
                    self.tr(
                        "<p><b>%s</b></p>"
                        "<p>Make sure <i>%s</i> is a valid label file.</p>"
                    )
                    % (e, label_path),
                )
                self.show_status_message(self.tr("Error reading %s") % label_path)
                return
            assert self._label_file is not None
            self.imageData = self._label_file.imageData
            assert self._label_file.imagePath
            self._image_path = str(Path(label_path).parent / self._label_file.imagePath)
            self._other_data = self._label_file.otherData
        else:
            image_path: str = image_or_label_path
            try:
                self.imageData = LabelFile.load_image_file(image_path)
            except OSError as e:
                self.errorMessage(
                    self.tr("Error opening file"),
                    self.tr(
                        "<p><b>%s</b></p>"
                        "<p>Make sure <i>%s</i> is a valid image file.</p>"
                    )
                    % (e, image_path),
                )
                self.show_status_message(self.tr("Error reading %s") % image_path)
                return
            if self.imageData:
                self._image_path = image_path
            self._label_file = None
        assert self.imageData is not None
        t0 = time.time()
        image = QtGui.QImage.fromData(self.imageData)
        logger.debug("Created QImage in {:.0f}ms", (time.time() - t0) * 1000)

        if image.isNull():
            formats = [
                f"*.{fmt.data().decode()}"
                for fmt in QtGui.QImageReader.supportedImageFormats()
            ]
            self.errorMessage(
                self.tr("Error opening file"),
                self.tr(
                    "<p>Make sure <i>{0}</i> is a valid image file.<br/>"
                    "Supported image formats: {1}</p>"
                ).format(image_or_label_path, ",".join(formats)),
            )
            self.show_status_message(self.tr("Error reading %s") % image_or_label_path)
            return
        self._image = image
        t0 = time.time()
        self._canvas_widgets.canvas.loadPixmap(QtGui.QPixmap.fromImage(image))
        logger.debug("Loaded pixmap in {:.0f}ms", (time.time() - t0) * 1000)
        flags = {k: False for k in self._config["flags"] or []}
        if self._label_file:
            self._load_shapes(
                shapes=_shapes_from_dicts(
                    shape_dicts=self._label_file.shapes,
                    label_flags=self._config["label_flags"],
                )
            )
            if self._label_file.flags is not None:
                flags.update(self._label_file.flags)
        self._load_flags(flags=flags, widget=self._docks.flag_list)
        if prev_shapes and self.noShapes():
            self._load_shapes(shapes=prev_shapes, replace=False)
            self.setDirty()
        else:
            self.setClean()
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
                self.setScroll(
                    orientation, self._scroll_values[orientation][self._image_path]
                )
        self.brightnessContrast(value=False, is_initial_load=True)
        self._paint_canvas()
        self.toggleActions(True)
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
        self._set_zoom(value=int(self._scalers[self._zoom_mode]() * 100))

    def scaleFitWindow(self) -> float:
        EPSILON_TO_HIDE_SCROLLBAR: float = 2.0
        viewport_w = self.centralWidget().width() - EPSILON_TO_HIDE_SCROLLBAR
        viewport_h = self.centralWidget().height() - EPSILON_TO_HIDE_SCROLLBAR

        pixmap_w = self._canvas_widgets.canvas.pixmap.width()
        pixmap_h = self._canvas_widgets.canvas.pixmap.height()

        scale_by_width = viewport_w / pixmap_w
        scale_by_height = viewport_h / pixmap_h
        return min(scale_by_width, scale_by_height)

    def scaleFitWidth(self) -> float:
        EPSILON_TO_HIDE_SCROLLBAR: float = 15.0
        w = self.centralWidget().width() - EPSILON_TO_HIDE_SCROLLBAR
        return w / self._canvas_widgets.canvas.pixmap.width()

    def enableSaveImageWithData(self, enabled: bool) -> None:
        self._config["with_image_data"] = enabled
        self._actions.save_with_image_data.setChecked(enabled)

    def _reset_layout(self) -> None:
        self.settings.remove("window/state")
        self.restoreState(self._default_state)

    def closeEvent(self, a0: QtGui.QCloseEvent) -> None:
        if not self._can_continue():
            a0.ignore()
        self.settings.setValue("window/size", self.size())
        self.settings.setValue("window/position", self.pos())
        self.settings.setValue("window/state", self.saveState())

    def dragEnterEvent(self, a0: QtGui.QDragEnterEvent) -> None:
        extensions = [
            f".{fmt.data().decode().lower()}"
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
        self.importDroppedImageFiles(items)

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
        path = self.currentPath()
        formats = [
            f"*.{fmt.data().decode()}"
            for fmt in QtGui.QImageReader.supportedImageFormats()
        ]
        filters = self.tr("Image & Label files (%s)") % " ".join(
            formats + [f"*{LabelFile.suffix}"]
        )
        fileDialog = FileDialogPreview(self)
        fileDialog.setFileMode(FileDialogPreview.ExistingFile)
        fileDialog.setNameFilter(filters)
        fileDialog.setWindowTitle(
            self.tr("%s - Choose Image or Label file") % __appname__,
        )
        fileDialog.setWindowFilePath(path)
        fileDialog.setViewMode(FileDialogPreview.Detail)
        if fileDialog.exec_() and (
            image_or_label_path := fileDialog.selectedFiles()[0]
        ):
            self._load_from_file_or_dir(file_or_dir=image_or_label_path)

    def changeOutputDirDialog(self, _value: bool = False) -> None:
        default_output_dir: str
        if self._output_dir is not None:
            default_output_dir = str(self._output_dir)
        elif self._image_path:
            default_output_dir = str(Path(self._image_path).parent)
        else:
            default_output_dir = self.currentPath()

        output_dir = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            self.tr("%s - Save/Load Annotations in Directory") % __appname__,
            default_output_dir,
            QtWidgets.QFileDialog.ShowDirsOnly
            | QtWidgets.QFileDialog.DontResolveSymlinks,
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

        if current_image_path in self.imageList:
            # retain currently selected file
            self._docks.file_list.setCurrentRow(
                self.imageList.index(current_image_path)
            )
            self._docks.file_list.repaint()

    def _save_label_file(self, *, save_as: bool = False) -> None:
        assert not self._image.isNull(), "cannot save empty image"

        label_path: str | None = None
        if not save_as and self._label_file:
            label_path = self._label_file.filename
        if label_path is None:
            label_path = self.saveFileDialog()

        if not label_path:
            logger.warning("label_path=%r is empty, so cannot save", label_path)
            return

        if self.saveLabels(label_path=label_path):
            self.setClean()

    def saveFileDialog(self) -> str:
        assert self._image_path is not None
        caption = self.tr("%s - Choose File") % __appname__
        filters = self.tr("Label files (*%s)") % LabelFile.suffix
        dlg = QtWidgets.QFileDialog(
            parent=self,
            caption=caption,
            directory=str(self._output_dir or Path(self._image_path).parent),
            filter=filters,
        )
        dlg.setDefaultSuffix(LabelFile.suffix[1:])
        dlg.setAcceptMode(QtWidgets.QFileDialog.AcceptSave)
        dlg.setOption(QtWidgets.QFileDialog.DontConfirmOverwrite, False)
        dlg.setOption(QtWidgets.QFileDialog.DontUseNativeDialog, False)
        label_path, _ = dlg.getSaveFileName(
            parent=self,
            caption=self.tr("Choose File"),
            directory=_resolve_label_path(
                image_or_label_path=self._image_path,
                output_dir=self._output_dir,
            ),
            filter=self.tr("Label files (*%s)") % LabelFile.suffix,
        )
        return label_path

    def closeFile(self, _value: bool = False) -> None:
        if not self._can_continue():
            return
        self.resetState()
        self.setClean()
        self.toggleActions(False)
        self._canvas_widgets.canvas.setEnabled(False)
        self._docks.file_list.setFocus()
        self._actions.save_as.setEnabled(False)

    def getLabelFile(self) -> str:
        assert self._image_path is not None
        return str(Path(self._image_path).with_suffix(".json"))

    def deleteFile(self) -> None:
        msg = self.tr(
            "You are about to permanently delete this label file, proceed anyway?"
        )
        answer = QtWidgets.QMessageBox.warning(
            self,
            self.tr("Attention"),
            msg,
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return

        annotation_path = Path(self.getLabelFile())
        if not annotation_path.exists():
            return

        annotation_path.unlink()
        logger.info(f"Label file is removed: {annotation_path}")

        item = self._docks.file_list.currentItem()
        if item:
            item.setCheckState(Qt.Unchecked)

        self.resetState()

    def _open_config_file(self) -> None:
        if self._config_file is None:
            QtWidgets.QMessageBox.information(
                self,
                self.tr("No Config File"),
                self.tr(
                    "Configuration was provided as a YAML expression via "
                    "command line.\n\n"
                    "To use the preferences editor, start Labelme with a config file:\n"
                    "  labelme --config ~/.labelmerc"
                ),
            )
            return
        config_file: Path = self._config_file

        system: str = platform.system()
        if system == "Darwin":
            subprocess.Popen(["open", "-t", config_file])
        elif system == "Windows":
            os.startfile(config_file)  # ty: ignore[unresolved-attribute]  # Windows-only
        else:
            subprocess.Popen(["xdg-open", config_file])

    # Message Dialogs. #
    def hasLabels(self) -> bool:
        if self.noShapes():
            self.errorMessage(
                "No objects labeled",
                "You must label at least one object to save the file.",
            )
            return False
        return True

    def hasLabelFile(self) -> bool:
        if self._image_path is None:
            return False

        label_file = self.getLabelFile()
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
            QtWidgets.QMessageBox.Save
            | QtWidgets.QMessageBox.Discard
            | QtWidgets.QMessageBox.Cancel,
            QtWidgets.QMessageBox.Save,
        )
        if user_choice == QtWidgets.QMessageBox.Save:
            self._save_label_file()
            return True
        return user_choice == QtWidgets.QMessageBox.Discard

    def errorMessage(self, title: str, message: str) -> int:
        return QtWidgets.QMessageBox.critical(
            self, title, f"<p><b>{title}</b></p>{message}"
        )

    def currentPath(self) -> str:
        return str(Path(self._image_path).parent) if self._image_path else "."

    def toggleKeepPrevMode(self) -> None:
        self._config["keep_prev"] = not self._config["keep_prev"]

    def removeSelectedPoint(self) -> None:
        self._canvas_widgets.canvas.removeSelectedPoint()
        self._canvas_widgets.canvas.update()
        if (
            self._canvas_widgets.canvas.hShape
            and not self._canvas_widgets.canvas.hShape.points
        ):
            self._canvas_widgets.canvas.deleteShape(self._canvas_widgets.canvas.hShape)
            self.remLabels([self._canvas_widgets.canvas.hShape])
            if self.noShapes():
                for action in self._actions.on_shapes_present:
                    action.setEnabled(False)
        self.setDirty()

    def deleteSelectedShape(self) -> None:
        yes, no = QtWidgets.QMessageBox.Yes, QtWidgets.QMessageBox.No
        msg = self.tr(
            "You are about to permanently delete {} shapes, proceed anyway?"
        ).format(len(self._canvas_widgets.canvas.selectedShapes))
        if yes == QtWidgets.QMessageBox.warning(
            self, self.tr("Attention"), msg, yes | no, yes
        ):
            self.remLabels(self._canvas_widgets.canvas.deleteSelected())
            self.setDirty()
            if self.noShapes():
                for action in self._actions.on_shapes_present:
                    action.setEnabled(False)

    def copyShape(self) -> None:
        self._canvas_widgets.canvas.endMove(copy=True)
        for shape in self._canvas_widgets.canvas.selectedShapes:
            self.addLabel(shape)
        self._docks.label_list.clearSelection()
        self.setDirty()

    def moveShape(self) -> None:
        self._canvas_widgets.canvas.endMove(copy=False)
        self.setDirty()

    def _load_from_file_or_dir(self, file_or_dir: str) -> None:
        if not file_or_dir:
            raise ValueError("file_or_dir cannot be empty")

        if LabelFile.is_label_file(filename=file_or_dir):
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

        defaultOpenDirPath: str
        if self._prev_opened_dir and Path(self._prev_opened_dir).exists():
            defaultOpenDirPath = self._prev_opened_dir
        else:
            defaultOpenDirPath = (
                str(Path(self._image_path).parent) if self._image_path else "."
            )

        dir_path = str(
            QtWidgets.QFileDialog.getExistingDirectory(
                self,
                self.tr("%s - Open Directory") % __appname__,
                defaultOpenDirPath,
                QtWidgets.QFileDialog.ShowDirsOnly
                | QtWidgets.QFileDialog.DontResolveSymlinks,
            )
        )
        if dir_path:
            self._load_from_file_or_dir(file_or_dir=dir_path)

    @property
    def imageList(self) -> list[str]:
        lst = []
        for i in range(self._docks.file_list.count()):
            item = self._docks.file_list.item(i)
            assert item
            lst.append(item.text())
        return lst

    def importDroppedImageFiles(self, imageFiles: list[str]) -> None:
        extensions = [
            f".{fmt.data().decode().lower()}"
            for fmt in QtGui.QImageReader.supportedImageFormats()
        ]

        self._image_path = None
        for file in imageFiles:
            if file in self.imageList or not file.lower().endswith(tuple(extensions)):
                continue
            item = QtWidgets.QListWidgetItem(file)
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            if QtCore.QFile.exists(
                _resolve_label_path(
                    image_or_label_path=file, output_dir=self._output_dir
                )
            ):
                item.setCheckState(Qt.Checked)
            else:
                item.setCheckState(Qt.Unchecked)
            self._docks.file_list.addItem(item)

        if len(self.imageList) > 1:
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
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            if QtCore.QFile.exists(
                _resolve_label_path(
                    image_or_label_path=image_path, output_dir=self._output_dir
                )
            ):
                item.setCheckState(Qt.Checked)
            else:
                item.setCheckState(Qt.Unchecked)
            self._docks.file_list.addItem(item)

    def _update_status_stats(self, mouse_pos: QtCore.QPointF) -> None:
        stats: list[str] = []
        stats.append(f"mode={self._canvas_widgets.canvas.mode.name}")
        stats.append(f"x={mouse_pos.x():6.1f}, y={mouse_pos.y():6.1f}")
        self._status_bar.stats.setText(" | ".join(stats))


def _shapes_from_dicts(
    shape_dicts: list[ShapeDict],
    label_flags: dict[str, list[str]] | None,
) -> list[Shape]:
    shapes: list[Shape] = []
    for shape_dict in shape_dicts:
        shape = Shape(
            label=shape_dict["label"],
            shape_type=shape_dict["shape_type"],
            group_id=shape_dict["group_id"],
            description=shape_dict["description"],
            mask=shape_dict["mask"],
        )
        for x, y in shape_dict["points"]:
            shape.addPoint(QtCore.QPointF(x, y))
        shape.close()

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


def _resolve_label_path(image_or_label_path: str, output_dir: Path | None) -> str:
    if LabelFile.is_label_file(filename=image_or_label_path):
        return image_or_label_path
    image_path = Path(image_or_label_path)
    parent = output_dir if output_dir is not None else image_path.parent
    return str(parent / f"{image_path.stem}{LabelFile.suffix}")


def _shape_to_dict(shape: Shape) -> dict[str, Any]:
    data = shape.other_data.copy()
    data.update(
        label=shape.label,
        points=[(p.x(), p.y()) for p in shape.points],
        group_id=shape.group_id,
        description=shape.description,
        shape_type=shape.shape_type,
        flags=shape.flags,
        mask=None
        if shape.mask is None
        else utils.img_arr_to_b64(shape.mask.astype(np.uint8)),
    )
    return data


def _scan_image_files(root_dir: str) -> list[str]:
    extensions: list[str] = [
        f".{fmt.data().decode().lower()}"
        for fmt in QtGui.QImageReader.supportedImageFormats()
    ]

    images: list[str] = []
    for root, dirs, files in os.walk(root_dir):
        for file in files:
            if file.lower().endswith(tuple(extensions)):
                relativePath = os.path.normpath(os.path.join(root, file))
                images.append(relativePath)

    logger.debug("found {:d} images in {!r}", len(images), root_dir)
    try:
        return natsort.os_sorted(images)
    except OSError:
        logger.warning(
            "natsort.os_sorted failed (known macOS strxfrm bug), "
            "falling back to locale-unaware natural sort"
        )
        return natsort.natsorted(images)
