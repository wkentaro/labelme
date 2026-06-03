from __future__ import annotations

import os.path as osp
import typing
from collections.abc import Callable
from typing import Final

from PyQt5 import QtCore
from PyQt5 import QtGui
from PyQt5 import QtWidgets

from labelme._config.schema import SETTINGS
from labelme._config.schema import Section
from labelme._config.schema import Setting

ApplySetting = Callable[[tuple[str, ...], object], None]

# Cool-tinted neutral palette (no pure black/white) with one intentional accent.
_ACCENT: Final = "#2f6bf0"
_BACKDROP: Final = "#eceef2"
_SURFACE: Final = "#fcfcfe"
_BORDER: Final = "#e2e6ec"
_BORDER_STRONG: Final = "#cfd5de"
_TEXT: Final = "#1f2733"
_TOGGLE_OFF: Final = "#ccd2db"
_KNOB: Final = "#fdfdff"

_ICONS_DIR: Final = osp.join(osp.dirname(osp.dirname(osp.abspath(__file__))), "icons")
_CARET_ICON: Final = osp.join(_ICONS_DIR, "phosphor", "caret-down.svg").replace(
    osp.sep, "/"
)

_STYLESHEET: Final = f"""
QDialog {{ background: {_BACKDROP}; }}
QListWidget#sectionList {{
    background: transparent;
    border: none;
    outline: none;
    padding: 8px;
    font-size: 13px;
    color: {_TEXT};
}}
QListWidget#sectionList::item {{
    padding: 9px 12px;
    border-radius: 8px;
    margin: 2px 0;
}}
QListWidget#sectionList::item:selected {{ background: {_ACCENT}; color: #ffffff; }}
QListWidget#sectionList::item:!selected:hover {{ background: rgba(31, 39, 51, 0.06); }}
QWidget#contentPanel {{
    background: {_SURFACE};
    border-radius: 14px;
    border: 1px solid {_BORDER};
}}
QLabel#sectionTitle {{ font-size: 16px; font-weight: 600; color: {_TEXT}; }}
QLabel#settingLabel {{ font-size: 13px; color: {_TEXT}; }}
QLineEdit, QComboBox, QPlainTextEdit, QSpinBox, QDoubleSpinBox {{
    background: {_SURFACE};
    border: 1px solid {_BORDER};
    border-radius: 8px;
    padding: 6px 9px;
    font-size: 13px;
    color: {_TEXT};
    selection-background-color: {_ACCENT};
    selection-color: #ffffff;
}}
QLineEdit:hover, QComboBox:hover, QPlainTextEdit:hover,
QSpinBox:hover, QDoubleSpinBox:hover {{ border: 1px solid {_BORDER_STRONG}; }}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus {{ border: 1px solid {_ACCENT}; }}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    border: none;
    width: 22px;
}}
QComboBox::down-arrow {{ image: url("{_CARET_ICON}"); width: 11px; height: 11px; }}
QPushButton {{
    background: {_SURFACE};
    border: 1px solid {_BORDER};
    border-radius: 8px;
    padding: 7px 16px;
    font-size: 13px;
    color: {_TEXT};
}}
QPushButton:hover {{ background: #f3f5f9; border: 1px solid {_BORDER_STRONG}; }}
QPushButton:pressed {{ background: #e9edf3; }}
QPushButton:focus {{ border: 1px solid {_ACCENT}; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 11px; margin: 2px 2px 2px 0; }}
QScrollBar::handle:vertical {{
    background: rgba(31, 39, 51, 0.20);
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: rgba(31, 39, 51, 0.34); }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {{ background: transparent; }}
"""


class ToggleSwitch(QtWidgets.QAbstractButton):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setFixedSize(42, 24)
        self._position = 0.0
        self._animation = QtCore.QPropertyAnimation(self, b"position", self)
        self._animation.setDuration(140)
        self.toggled.connect(self._animate)

    def _get_position(self) -> float:
        return self._position

    def _set_position(self, value: float) -> None:
        self._position = value
        self.update()

    position = QtCore.pyqtProperty(float, fget=_get_position, fset=_set_position)

    def _animate(self, checked: bool) -> None:
        end = 1.0 if checked else 0.0
        if not self.isVisible():
            self._set_position(end)
            return
        self._animation.stop()
        self._animation.setStartValue(self._position)
        self._animation.setEndValue(end)
        self._animation.start()

    def paintEvent(self, e: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setPen(QtCore.Qt.NoPen)

        off = QtGui.QColor(_TOGGLE_OFF)
        on = QtGui.QColor(_ACCENT)
        track = QtGui.QColor(
            round(off.red() + (on.red() - off.red()) * self._position),
            round(off.green() + (on.green() - off.green()) * self._position),
            round(off.blue() + (on.blue() - off.blue()) * self._position),
        )
        if not self.isEnabled():
            track.setAlpha(90)
        radius = self.height() / 2
        painter.setBrush(track)
        painter.drawRoundedRect(self.rect(), radius, radius)

        margin = 2
        diameter = self.height() - 2 * margin
        travel = self.width() - self.height()
        x = margin + self._position * travel
        painter.setBrush(QtGui.QColor(_KNOB))
        painter.drawEllipse(QtCore.QRectF(x, margin, diameter, diameter))


class _PlainTextEdit(QtWidgets.QPlainTextEdit):
    editing_finished = QtCore.pyqtSignal()

    def focusOutEvent(self, e: QtGui.QFocusEvent) -> None:
        super().focusOutEvent(e)
        self.editing_finished.emit()


class SettingsDialog(QtWidgets.QDialog):
    def __init__(
        self,
        config: dict,
        apply_setting: ApplySetting,
        open_as_text: Callable[[], None],
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setStyleSheet(_STYLESHEET)

        self._config = config
        self._apply_setting = apply_setting
        self._editors: dict[tuple[str, ...], QtWidgets.QWidget] = {}

        section_list = QtWidgets.QListWidget()
        section_list.setObjectName("sectionList")
        section_list.setFixedWidth(190)
        stack = QtWidgets.QStackedWidget()
        for section in typing.get_args(Section):
            settings = [s for s in SETTINGS if s.section == section]
            if not settings:
                continue
            section_list.addItem(section)
            stack.addWidget(self._build_page(title=section, settings=settings))
        section_list.currentRowChanged.connect(stack.setCurrentIndex)
        section_list.setCurrentRow(0)

        shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(14)
        shadow.setColor(QtGui.QColor(15, 23, 42, 40))
        shadow.setOffset(0, 2)
        stack.setGraphicsEffect(shadow)

        open_button = QtWidgets.QPushButton("Open config file as text…")
        open_button.clicked.connect(lambda: open_as_text())
        close_button = QtWidgets.QPushButton("Close")
        close_button.setDefault(True)
        close_button.clicked.connect(self.accept)

        top_layout = QtWidgets.QHBoxLayout()
        top_layout.setSpacing(16)
        top_layout.addWidget(section_list)
        top_layout.addWidget(stack, stretch=1)

        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addWidget(open_button)
        button_layout.addStretch(1)
        button_layout.addWidget(close_button)

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(16)
        layout.addLayout(top_layout, stretch=1)
        layout.addLayout(button_layout)
        self.setLayout(layout)
        self.resize(740, 560)

        self._sync_validate_label_gate(emit_apply=False)

    def accept(self) -> None:
        # Flush text editors whose edits commit on focus-out: clicking Close
        # does not always move focus first, so apply pending input explicitly.
        for editor in self._editors.values():
            if isinstance(editor, _PlainTextEdit):
                editor.editing_finished.emit()
        super().accept()

    def _read_value(self, key_path: tuple[str, ...]) -> object:
        node: object = self._config
        for key in key_path:
            assert isinstance(node, dict)
            node = node[key]
        return node

    def _apply(self, setting: Setting, value: object) -> None:
        self._apply_setting(setting.key_path, value)

    def _build_page(self, title: str, settings: list[Setting]) -> QtWidgets.QWidget:
        rows = QtWidgets.QWidget()
        rows_layout = QtWidgets.QVBoxLayout(rows)
        # Right gutter so content (and right-aligned controls) clears the
        # scrollbar instead of butting against it.
        rows_layout.setContentsMargins(0, 0, 12, 0)
        rows_layout.setSpacing(4)
        for setting in settings:
            editor = self._create_editor(setting=setting)
            self._editors[setting.key_path] = editor
            rows_layout.addWidget(self._make_row(setting=setting, editor=editor))
        rows_layout.addStretch(1)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setWidget(rows)

        header = QtWidgets.QLabel(title)
        header.setObjectName("sectionTitle")

        page = QtWidgets.QWidget()
        page.setObjectName("contentPanel")
        page.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        page_layout = QtWidgets.QVBoxLayout(page)
        page_layout.setContentsMargins(24, 20, 12, 16)
        page_layout.setSpacing(16)
        page_layout.addWidget(header)
        page_layout.addWidget(scroll, stretch=1)
        return page

    def _make_row(
        self, setting: Setting, editor: QtWidgets.QWidget
    ) -> QtWidgets.QWidget:
        label = QtWidgets.QLabel(setting.label)
        label.setObjectName("settingLabel")
        label.setWordWrap(True)

        row = QtWidgets.QWidget()
        if setting.kind == "str_list":
            vertical = QtWidgets.QVBoxLayout(row)
            vertical.setContentsMargins(0, 8, 0, 8)
            vertical.setSpacing(8)
            vertical.addWidget(label)
            vertical.addWidget(editor)
            return row

        horizontal = QtWidgets.QHBoxLayout(row)
        horizontal.setContentsMargins(0, 6, 0, 6)
        horizontal.setSpacing(12)
        horizontal.addWidget(label, stretch=1)
        horizontal.addWidget(editor)
        return row

    def _create_editor(self, setting: Setting) -> QtWidgets.QWidget:
        value = self._read_value(setting.key_path)
        if setting.kind == "bool":
            return self._create_bool_editor(setting=setting, value=value)
        if setting.kind == "enum":
            return self._create_enum_editor(setting=setting, value=value)
        if setting.kind == "str_list":
            return self._create_str_list_editor(setting=setting, value=value)
        typing.assert_never(setting.kind)

    def _create_bool_editor(self, setting: Setting, value: object) -> ToggleSwitch:
        toggle = ToggleSwitch()
        toggle.setChecked(bool(value))
        toggle.toggled.connect(
            lambda checked: self._apply(setting=setting, value=checked)
        )
        return toggle

    def _create_enum_editor(
        self, setting: Setting, value: object
    ) -> QtWidgets.QComboBox:
        assert setting.choices is not None
        combo = QtWidgets.QComboBox()
        combo.setMinimumWidth(140)
        for choice in setting.choices:
            combo.addItem("(none)" if choice is None else str(choice), choice)
        index = combo.findData(value)
        combo.setCurrentIndex(max(index, 0))
        combo.currentIndexChanged.connect(
            lambda: self._apply(setting=setting, value=combo.currentData())
        )
        return combo

    def _create_str_list_editor(
        self, setting: Setting, value: object
    ) -> _PlainTextEdit:
        edit = _PlainTextEdit()
        edit.setPlaceholderText("one item per line")
        edit.setMinimumHeight(64)
        edit.setMaximumHeight(96)
        items = value if isinstance(value, list) else []
        edit.setPlainText("\n".join(str(item) for item in items))
        edit.editing_finished.connect(
            lambda: self._apply(setting=setting, value=_parse_str_list(edit))
        )
        if setting.key_path == ("labels",):
            edit.editing_finished.connect(self._sync_validate_label_gate)
        return edit

    def _sync_validate_label_gate(self, emit_apply: bool = True) -> None:
        labels_editor = self._editors.get(("labels",))
        validate_combo = self._editors.get(("validate_label",))
        if not isinstance(labels_editor, _PlainTextEdit):
            return
        if not isinstance(validate_combo, QtWidgets.QComboBox):
            return
        exact_index = validate_combo.findData("exact")
        if exact_index < 0:
            return
        model = validate_combo.model()
        assert isinstance(model, QtGui.QStandardItemModel)

        has_labels = _parse_str_list(labels_editor) is not None
        model.item(exact_index).setEnabled(has_labels)
        if has_labels or validate_combo.currentData() != "exact":
            return

        none_index = validate_combo.findData(None)
        if emit_apply:
            validate_combo.setCurrentIndex(none_index)
            return
        # Construction-time revert must not fire apply_setting.
        blocked = validate_combo.blockSignals(True)
        validate_combo.setCurrentIndex(none_index)
        validate_combo.blockSignals(blocked)


def _parse_str_list(edit: _PlainTextEdit) -> list[str] | None:
    items: list[str] = []
    for line in edit.toPlainText().splitlines():
        item = line.strip()
        if item and item not in items:
            items.append(item)
    return items or None
