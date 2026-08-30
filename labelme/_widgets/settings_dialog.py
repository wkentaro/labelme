from __future__ import annotations

import typing
from collections.abc import Callable
from collections.abc import Sequence

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from .. import _locale
from .._config import _schema as schema
from .._config._shape_color import RGB_CHANNEL_COUNT
from .._utils.qt import new_icon
from ._integer_slider import IntegerSlider

ApplySetting = Callable[[tuple[str, ...], object], bool]
PreviewShapeColor = Callable[[tuple[str, ...], list[int] | None], None]


class _PlainTextEdit(QtWidgets.QPlainTextEdit):
    editing_finished = QtCore.Signal()

    _committed_text: str = ""

    def mark_committed(self) -> None:
        self._committed_text = self.toPlainText()

    def commit(self) -> None:
        # Emit only on a real change so re-focusing or closing the dialog does
        # not rewrite the config file with an identical value.
        if self.toPlainText() == self._committed_text:
            return
        self.mark_committed()
        self.editing_finished.emit()

    def focusOutEvent(self, e: QtGui.QFocusEvent) -> None:
        super().focusOutEvent(e)
        self.commit()


class _ColorSwatchButton(QtWidgets.QPushButton):
    _rgb: tuple[int, int, int] = (0, 0, 0)

    def __init__(self) -> None:
        super().__init__()
        self._accessible_note = ""
        self.setFixedSize(48, 24)

    def get_rgb(self) -> tuple[int, int, int]:
        return self._rgb

    def set_rgb(self, rgb: tuple[int, int, int]) -> None:
        self._rgb = rgb
        r, g, b = rgb
        self.setToolTip(
            self.tr("RGB: {red}, {green}, {blue}").format(red=r, green=g, blue=b)
        )
        self._update_accessible_description()
        swatch = QtGui.QPixmap(32, 16)
        swatch.fill(QtGui.QColor(r, g, b))
        self.setIcon(QtGui.QIcon(swatch))
        self.setIconSize(swatch.size())

    def set_accessible_note(self, note: str) -> None:
        self._accessible_note = note
        self._update_accessible_description()

    def _update_accessible_description(self) -> None:
        description = self.toolTip()
        if self._accessible_note:
            description = f"{description}. {self._accessible_note}"
        self.setAccessibleDescription(description)


class _SettingsPage(QtWidgets.QWidget):
    def __init__(
        self,
        groups: Sequence[tuple[str, QtGui.QIcon, QtWidgets.QGroupBox]],
    ) -> None:
        super().__init__()

        navigation = QtWidgets.QListWidget()
        navigation.setAccessibleName(self.tr("Settings sections"))
        navigation.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        navigation.setTextElideMode(QtCore.Qt.TextElideMode.ElideRight)
        NAVIGATION_FONT_SIZE_INCREMENT: typing.Final = 1.0
        NAVIGATION_ICON_SIZE: typing.Final = QtCore.QSize(18, 18)
        NAVIGATION_TEXT_INSET: typing.Final = 8
        NAVIGATION_VERTICAL_PADDING: typing.Final = 12
        navigation_font = QtGui.QFont(navigation.font())
        navigation_font.setPointSizeF(
            navigation_font.pointSizeF() + NAVIGATION_FONT_SIZE_INCREMENT
        )
        navigation.setFont(navigation_font)
        navigation.setIconSize(NAVIGATION_ICON_SIZE)
        navigation.setStyleSheet(
            f"QListWidget::item {{ padding-left: {NAVIGATION_TEXT_INSET}px; }}"
        )
        for title, icon, _group_box in groups:
            item = QtWidgets.QListWidgetItem(icon, title)
            item.setToolTip(title)
            navigation.addItem(item)
            item_size = navigation.sizeHintForIndex(navigation.indexFromItem(item))
            item_size.setHeight(
                navigation.fontMetrics().height() + NAVIGATION_VERTICAL_PADDING
            )
            item.setSizeHint(item_size)
        MINIMUM_NAVIGATION_WIDTH: typing.Final = 160
        MAXIMUM_NAVIGATION_WIDTH: typing.Final = 240
        NAVIGATION_PADDING: typing.Final = 8
        navigation_width = max(
            MINIMUM_NAVIGATION_WIDTH,
            min(
                MAXIMUM_NAVIGATION_WIDTH,
                navigation.sizeHintForColumn(0) + NAVIGATION_PADDING,
            ),
        )
        navigation.setFixedWidth(navigation_width)

        content = QtWidgets.QWidget()
        content_layout = QtWidgets.QVBoxLayout(content)
        for _title, _icon, group_box in groups:
            content_layout.addWidget(group_box)
        content_layout.addStretch(1)

        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(content)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(navigation)
        layout.addWidget(scroll_area, stretch=1)

        self._navigation = navigation
        self._scroll_area = scroll_area
        self._content = content
        self._groups = [group_box for _title, _icon, group_box in groups]
        self._scrolling_to_group = False

        navigation.currentRowChanged.connect(self._scroll_to_group)
        navigation.itemClicked.connect(
            lambda item: self._scroll_to_group(navigation.row(item))
        )
        scroll_area.verticalScrollBar().valueChanged.connect(
            self._sync_navigation_to_scroll
        )
        navigation.setCurrentRow(0)

    @property
    def _required_width(self) -> int:
        # The width below which the settings scroll sideways. The page size hint
        # does not report it: QScrollArea caps its own hint at 36 character
        # widths and ignores how far its widget refuses to shrink, so a font
        # wider than the one the layout was tuned for would size the page too
        # narrow. Swap the scroll area's hint for what the content cannot give
        # up, and keep the rest of the page hint as measured.
        return (
            self.sizeHint().width()
            - self._scroll_area.sizeHint().width()
            + self._content.minimumSizeHint().width()
        )

    def _scroll_to_group(self, index: int, /) -> None:
        if not 0 <= index < len(self._groups):
            return
        group = self._groups[index]
        group_top = group.mapTo(self._content, QtCore.QPoint()).y()
        # Blocking the scroll bar would also cut the scroll area's own
        # valueChanged connection, moving the handle while the content stays put,
        # so gate the navigation sync instead of silencing the scroll bar.
        self._scrolling_to_group = True
        self._scroll_area.verticalScrollBar().setValue(group_top)
        self._scrolling_to_group = False
        with QtCore.QSignalBlocker(self._navigation):
            self._navigation.setCurrentRow(index)

    def _sync_navigation_to_scroll(self, value: int, /) -> None:
        if self._scrolling_to_group:
            return
        viewport = self._scroll_area.viewport()
        # Move the reading point toward the viewport center as the user leaves
        # the top, so short groups near the bottom can become active too.
        reading_position = value + min(value, viewport.height() // 2)
        active = 0
        for index, group in enumerate(self._groups):
            group_top = group.mapTo(self._content, QtCore.QPoint()).y()
            if group_top > reading_position:
                break
            active = index
        scroll_bar = self._scroll_area.verticalScrollBar()
        if scroll_bar.maximum() > 0 and value == scroll_bar.maximum():
            active = len(self._groups) - 1
        with QtCore.QSignalBlocker(self._navigation):
            self._navigation.setCurrentRow(active)


class SettingsDialog(QtWidgets.QDialog):
    def __init__(
        self,
        config: dict,
        apply_setting: ApplySetting,
        preview_shape_color: PreviewShapeColor,
        open_as_text: Callable[[], None],
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Settings"))

        self._config = config
        self._apply_setting = apply_setting
        self._preview_shape_color = preview_shape_color
        self._editors: dict[tuple[str, ...], QtWidgets.QWidget] = {}

        GROUP_ICONS: typing.Final[dict[schema.Group, str]] = {
            "Appearance and language": "phosphor/palette.svg",
            "Files and saving": "phosphor/floppy-disk-duotone.svg",
            "Drawing and canvas": "phosphor/polygon.svg",
            "Continue between images": "phosphor/images.svg",
            "Label sources": "phosphor/tag.svg",
            "Label behavior": "phosphor/sliders-horizontal.svg",
            "AI assist": "phosphor/sparkle.svg",
        }
        groups: list[tuple[str, QtGui.QIcon, QtWidgets.QGroupBox]] = []
        for group in typing.get_args(schema.Group):
            settings = [
                setting for setting in schema.SETTINGS if setting.group == group
            ]
            if not settings:
                continue
            groups.append(
                (
                    self.tr(group),
                    new_icon(GROUP_ICONS[group]),
                    self._build_group(title=self.tr(group), settings=settings),
                )
            )
        page = _SettingsPage(groups=groups)
        self._page = page

        open_button = QtWidgets.QPushButton(self.tr("Open config file as text…"))
        open_button.setToolTip(
            self.tr("Edits made in the text file apply after restart")
        )
        open_button.clicked.connect(open_as_text)
        close_button = QtWidgets.QPushButton(self.tr("Close"))
        close_button.setDefault(True)
        close_button.clicked.connect(self.accept)

        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addWidget(open_button)
        button_layout.addStretch(1)
        button_layout.addWidget(close_button)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(page, stretch=1)
        layout.addLayout(button_layout)
        self.setLayout(layout)
        DEFAULT_DIALOG_SIZE: typing.Final = QtCore.QSize(760, 590)
        scroll_bar_width = self.style().pixelMetric(
            QtWidgets.QStyle.PixelMetric.PM_ScrollBarExtent
        )
        page_width = max(page.sizeHint().width(), page._required_width)
        dialog_chrome_width = self.sizeHint().width() - page.sizeHint().width()
        preferred_dialog_size = QtCore.QSize(
            max(
                DEFAULT_DIALOG_SIZE.width(),
                page_width + dialog_chrome_width + scroll_bar_width,
            ),
            DEFAULT_DIALOG_SIZE.height(),
        )
        initial_dialog_size = preferred_dialog_size.boundedTo(
            self.screen().availableGeometry().size()
        )
        self.setMinimumWidth(initial_dialog_size.width())
        self.resize(initial_dialog_size)

        self._sync_validate_label_gate()
        self._sync_shape_color_mode()

    def accept(self) -> None:
        # Flush text editors whose edits commit on focus-out: clicking Close
        # does not always move focus first, so apply pending input explicitly.
        # commit() is a no-op when the text is unchanged.
        for editor in self._editors.values():
            if isinstance(editor, _PlainTextEdit):
                editor.commit()
        super().accept()

    def reject(self) -> None:
        # Immediate-apply dialog: Escape and the window-close button discard
        # nothing, so treat them like Close and flush pending edits.
        self.accept()

    def set_value(self, key_path: tuple[str, ...], value: object) -> None:
        editor = self._editors[key_path]
        with QtCore.QSignalBlocker(editor):
            self._set_editor_value(editor=editor, value=value)
        if key_path == ("shape_color", "mode"):
            self._sync_shape_color_mode()

    def set_choice_enabled(
        self,
        key_path: tuple[str, ...],
        value: object,
        *,
        enabled: bool,
        disabled_reason: str,
    ) -> None:
        editor = self._editors[key_path]
        assert isinstance(editor, QtWidgets.QComboBox)
        index = editor.findData(value)
        assert index >= 0
        model = editor.model()
        assert isinstance(model, QtGui.QStandardItemModel)
        item = model.item(index)
        assert item is not None
        item.setEnabled(enabled)
        item.setToolTip("" if enabled else disabled_reason)

    def _read_value(self, *, key_path: tuple[str, ...]) -> object:
        node: object = self._config
        for key in key_path:
            if not isinstance(node, dict):
                raise TypeError(f"config path {key_path} is not a mapping at {key!r}")
            node = node[key]
        return node

    def _build_group(
        self, *, title: str, settings: list[schema.Setting]
    ) -> QtWidgets.QGroupBox:
        group_box = QtWidgets.QGroupBox(title)
        group_box.setFlat(True)
        layout = QtWidgets.QVBoxLayout(group_box)
        for setting in settings:
            editor = self._create_editor(setting=setting)
            editor.setAccessibleName(self.tr(setting.label))
            if setting.note:
                note = self.tr(setting.note)
                if isinstance(editor, _ColorSwatchButton):
                    editor.set_accessible_note(note)
                else:
                    editor.setAccessibleDescription(note)
            self._editors[setting.key_path] = editor

            label_cell = self._build_label_cell(setting=setting, editor=editor)
            row = QtWidgets.QWidget()
            if setting.kind == "str_list":
                row_layout = QtWidgets.QVBoxLayout(row)
                row_layout.addWidget(label_cell)
                row_layout.addWidget(editor)
            else:
                row_layout = QtWidgets.QHBoxLayout(row)
                row_layout.addWidget(label_cell, stretch=1)
                # Top-align the control so it pairs with the label's first line
                # rather than centering against the label+note block.
                row_layout.addWidget(editor, alignment=QtCore.Qt.AlignmentFlag.AlignTop)
            layout.addWidget(row)
        return group_box

    def _build_label_cell(
        self, *, setting: schema.Setting, editor: QtWidgets.QWidget
    ) -> QtWidgets.QWidget:
        label = QtWidgets.QLabel(self.tr(setting.label))
        label.setBuddy(editor)
        label.setWordWrap(True)
        title: QtWidgets.QWidget = label
        if setting.beta:
            # Keep the label on one line so the badge hugs it instead of floating
            # past a wrap; the dialog auto-widens to fit the row.
            label.setWordWrap(False)
            title = QtWidgets.QWidget()
            title_layout = QtWidgets.QHBoxLayout(title)
            title_layout.setContentsMargins(0, 0, 0, 0)
            title_layout.setSpacing(6)
            title_layout.addWidget(label)
            title_layout.addWidget(
                _build_beta_badge(text=self.tr("BETA")),
                alignment=QtCore.Qt.AlignmentFlag.AlignVCenter,
            )
            title_layout.addStretch(1)
        if not setting.note:
            return title
        cell = QtWidgets.QWidget()
        cell_layout = QtWidgets.QVBoxLayout(cell)
        cell_layout.setContentsMargins(0, 0, 0, 0)
        cell_layout.setSpacing(2)
        cell_layout.addWidget(title)
        note = QtWidgets.QLabel(self.tr(setting.note))
        note.setWordWrap(True)
        # Secondary text color, kept enabled: a disabled label would be announced
        # as a disabled control and carry the platform's washed-out gray. The
        # foreground role (not an explicit palette) tracks live theme changes.
        note.setForegroundRole(QtGui.QPalette.ColorRole.PlaceholderText)
        cell_layout.addWidget(note)
        return cell

    def _create_editor(self, *, setting: schema.Setting) -> QtWidgets.QWidget:
        value = self._read_value(key_path=setting.key_path)
        if setting.kind == "bool":
            check = QtWidgets.QCheckBox()
            self._set_editor_value(editor=check, value=value)
            check.toggled.connect(
                lambda checked: self._apply(setting.key_path, checked)
            )
            return check
        if setting.kind == "enum":
            assert setting.choices is not None
            enum_items: list[tuple[str, object]] = []
            for index, choice in enumerate(setting.choices):
                if setting.choice_labels is not None:
                    label = self.tr(setting.choice_labels[index])
                elif choice is None:
                    label = self.tr("(none)")
                else:
                    label = str(choice)
                enum_items.append((label, choice))
            return self._create_combo(
                setting=setting, value=value, items=enum_items, min_width=140
            )
        if setting.kind == "int":
            assert isinstance(value, int)
            if setting.minimum is None and setting.maximum is None:
                # Qt's integer widgets are 32-bit, but Config Files accept Python ints.
                integer_edit = QtWidgets.QLineEdit()
                integer_edit.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
                self._set_editor_value(editor=integer_edit, value=value)
                integer_edit.editingFinished.connect(
                    lambda: self._apply_integer_edit(
                        key_path=setting.key_path, edit=integer_edit
                    )
                )
                return integer_edit
            assert setting.minimum is not None
            assert setting.maximum is not None
            slider = IntegerSlider(
                minimum=setting.minimum,
                maximum=setting.maximum,
                value=value,
            )
            slider.setMinimumWidth(180)
            slider.value_changed.connect(
                lambda new_value: self._apply(setting.key_path, new_value)
            )
            return slider
        if setting.kind == "language":
            languages = sorted(
                (
                    (QtCore.QLocale(code).nativeLanguageName() or code, code)
                    for code in _locale.available_translation_locales()
                ),
                key=lambda name_and_code: name_and_code[0].casefold(),
            )
            items = [
                (self.tr("System default"), None),
                ("English", _locale.SOURCE_LOCALE),
                *languages,
            ]
            return self._create_combo(
                setting=setting, value=value, items=items, min_width=160
            )
        if setting.kind == "color":
            swatch = _ColorSwatchButton()
            self._set_editor_value(editor=swatch, value=value)
            swatch.clicked.connect(
                lambda: self._pick_color(key_path=setting.key_path, swatch=swatch)
            )
            return swatch
        if setting.kind == "str_list":
            edit = _PlainTextEdit()
            edit.setPlaceholderText(self.tr("one item per line"))
            edit.setMinimumHeight(64)
            edit.setMaximumHeight(96)
            self._set_editor_value(editor=edit, value=value)
            if setting.key_path == ("labels",):
                edit.editing_finished.connect(lambda: self._on_labels_edited(edit=edit))
            else:
                edit.editing_finished.connect(
                    lambda: self._apply(setting.key_path, _parse_str_list(edit=edit))
                )
            return edit
        typing.assert_never(setting.kind)

    def _create_combo(
        self,
        *,
        setting: schema.Setting,
        value: object,
        items: Sequence[tuple[str, object]],
        min_width: int,
    ) -> QtWidgets.QComboBox:
        combo = QtWidgets.QComboBox()
        combo.setMinimumWidth(min_width)
        for label, data in items:
            combo.addItem(label, data)
        self._set_editor_value(editor=combo, value=value)
        combo.currentIndexChanged.connect(
            lambda: self._apply_combo(setting=setting, combo=combo)
        )
        return combo

    def _apply_combo(
        self, *, setting: schema.Setting, combo: QtWidgets.QComboBox
    ) -> None:
        self._apply(setting.key_path, combo.currentData())
        if setting.key_path == ("shape_color", "mode"):
            self._sync_shape_color_mode()

    def _apply_integer_edit(
        self, *, key_path: tuple[str, ...], edit: QtWidgets.QLineEdit
    ) -> None:
        try:
            value = int(edit.text())
        except ValueError:
            self._revert_editor(key_path=key_path)
            return
        edit.setText(str(value))
        self._apply(key_path, value)

    def _pick_color(
        self, *, key_path: tuple[str, ...], swatch: _ColorSwatchButton
    ) -> None:
        picker = QtWidgets.QColorDialog(
            parent=self, currentColor=QtGui.QColor(*swatch.get_rgb())
        )
        picker.currentColorChanged.connect(
            lambda color: self._preview_color(
                key_path=key_path, swatch=swatch, color=color
            )
        )
        accepted = picker.exec() == QtWidgets.QDialog.DialogCode.Accepted
        if accepted:
            self._apply(key_path, list(swatch.get_rgb()))
        else:
            self._revert_editor(key_path=key_path)
        self._preview_shape_color(key_path, None)

    def _preview_color(
        self,
        *,
        key_path: tuple[str, ...],
        swatch: _ColorSwatchButton,
        color: QtGui.QColor,
    ) -> None:
        rgb = (color.red(), color.green(), color.blue())
        swatch.set_rgb(rgb)
        self._preview_shape_color(key_path, list(rgb))

    def _set_editor_value(self, *, editor: QtWidgets.QWidget, value: object) -> None:
        if isinstance(editor, QtWidgets.QCheckBox):
            editor.setChecked(bool(value))
        elif isinstance(editor, QtWidgets.QComboBox):
            editor.setCurrentIndex(max(editor.findData(value), 0))
        elif isinstance(editor, IntegerSlider):
            assert isinstance(value, int)
            editor.set_value(value)
        elif isinstance(editor, QtWidgets.QLineEdit):
            assert isinstance(value, int)
            editor.setText(str(value))
        elif isinstance(editor, _PlainTextEdit):
            items = value if isinstance(value, list) else []
            editor.setPlainText("\n".join(str(item) for item in items))
            editor.mark_committed()
        elif isinstance(editor, _ColorSwatchButton):
            editor.set_rgb(_parse_rgb(value=value))

    def _apply(self, key_path: tuple[str, ...], value: object, /) -> bool:
        editor = self._editors[key_path]
        if isinstance(editor, QtWidgets.QComboBox):
            model = editor.model()
            assert isinstance(model, QtGui.QStandardItemModel)
            item = model.item(editor.findData(value))
            assert item is not None
            if not item.isEnabled():
                self._revert_editor(key_path=key_path)
                return False
        if self._apply_setting(key_path, value):
            return True
        # The write failed and the in-memory config was left unchanged, so reset
        # the editor to the last-saved value rather than show a phantom edit that
        # never persisted.
        self._revert_editor(key_path=key_path)
        return False

    def _revert_editor(self, *, key_path: tuple[str, ...]) -> None:
        self.set_value(key_path=key_path, value=self._read_value(key_path=key_path))

    def _on_labels_edited(self, *, edit: _PlainTextEdit) -> None:
        labels = _parse_str_list(edit=edit)
        validate_combo = self._editors.get(("validate_label",))
        if (
            not labels
            and isinstance(validate_combo, QtWidgets.QComboBox)
            and validate_combo.currentData() == "exact"
        ):
            QtWidgets.QMessageBox.warning(
                self,
                self.tr("Configuration Error"),
                self.tr(
                    "Predefined labels cannot be empty while Label validation is set "
                    "to exact. Disable exact validation first."
                ),
            )
            self._revert_editor(key_path=("labels",))
            return
        self._apply(("labels",), labels)
        self._sync_validate_label_gate()

    def _sync_validate_label_gate(self) -> None:
        labels_editor = self._editors.get(("labels",))
        validate_combo = self._editors.get(("validate_label",))
        if not isinstance(labels_editor, _PlainTextEdit) or not isinstance(
            validate_combo, QtWidgets.QComboBox
        ):
            return
        exact_index = validate_combo.findData("exact")
        model = validate_combo.model()
        if exact_index < 0 or not isinstance(model, QtGui.QStandardItemModel):
            return

        allowed = bool(_parse_str_list(edit=labels_editor))
        model.item(exact_index).setEnabled(allowed)
        if not allowed and validate_combo.currentData() == "exact":
            validate_combo.setCurrentIndex(validate_combo.findData(None))

    def _sync_shape_color_mode(self) -> None:
        mode = self._editors.get(("shape_color", "mode"))
        if not isinstance(mode, QtWidgets.QComboBox):
            return
        active_path = {
            "auto": ("shape_color", "auto", "shift"),
            "uniform": ("shape_color", "uniform", "color"),
            "by_label": ("shape_color", "by_label", "fallback"),
        }[mode.currentData()]
        for key_path in (
            ("shape_color", "auto", "shift"),
            ("shape_color", "uniform", "color"),
            ("shape_color", "by_label", "fallback"),
        ):
            row = self._editors[key_path].parentWidget()
            assert row is not None
            row.setEnabled(key_path == active_path)


def _build_beta_badge(*, text: str) -> QtWidgets.QLabel:
    badge = QtWidgets.QLabel(text)
    badge.setSizePolicy(
        QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed
    )
    # palette() refs (not literal hex) so the app's theme switch re-resolves them
    # via _retheme; a muted outline reads as a status tag, not an accent-colored
    # control, and text-on-window keeps the body-text contrast in both themes.
    badge.setStyleSheet(
        "QLabel {"
        "  color: palette(text);"
        "  border: 1px solid palette(mid);"
        "  border-radius: 7px;"
        "  padding: 0px 6px;"
        "  font-size: 10px;"
        "  font-weight: 600;"
        "}"
    )
    return badge


def _parse_rgb(*, value: object) -> tuple[int, int, int]:
    assert isinstance(value, list) and len(value) == RGB_CHANNEL_COUNT
    r, g, b = value
    assert isinstance(r, int) and isinstance(g, int) and isinstance(b, int)
    return r, g, b


def _parse_str_list(*, edit: _PlainTextEdit) -> list[str] | None:
    items: list[str] = []
    for line in edit.toPlainText().splitlines():
        item = line.strip()
        if item and item not in items:
            items.append(item)
    return items or None
