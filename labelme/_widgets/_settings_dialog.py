from __future__ import annotations

import re
import typing
from collections.abc import Callable
from collections.abc import Sequence
from itertools import pairwise

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from .. import _locale
from .._config import _schema as schema
from .._config._shape_color import RGB_CHANNEL_COUNT
from .._utils._qt import new_icon
from ._integer_slider import IntegerSlider

ApplySetting = Callable[[tuple[str, ...], object], bool]
PreviewShapeColor = Callable[[tuple[str, ...], list[int] | None], None]

_SOURCE_LABEL_ROLE: typing.Final = QtCore.Qt.ItemDataRole.UserRole + 1
_CONTEXT_FONT_SCALE: typing.Final = 0.85


class _SearchResultDelegate(QtWidgets.QStyledItemDelegate):
    # Search results carry "name\nsection" as their text; the section is drawn
    # smaller and muted so the setting name stays primary. Section results keep
    # the default single-line rendering.
    def paint(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
        /,
    ) -> None:
        if not isinstance(index.data(QtCore.Qt.ItemDataRole.UserRole), list | tuple):
            super().paint(painter, option, index)
            return
        opt = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        # PySide6 leaves the copied option's text empty, so read the model.
        title, section = index.data(QtCore.Qt.ItemDataRole.DisplayRole).split(
            "\n", maxsplit=1
        )
        style = opt.widget.style()
        text_rect = style.subElementRect(
            QtWidgets.QStyle.SubElement.SE_ItemViewItemText, opt, opt.widget
        )
        opt.text = ""
        style.drawControl(
            QtWidgets.QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget
        )
        margin = (
            style.pixelMetric(
                QtWidgets.QStyle.PixelMetric.PM_FocusFrameHMargin, None, opt.widget
            )
            + 1
        )
        text_rect.adjust(margin, 0, -margin, 0)
        section_font = QtGui.QFont(opt.font)
        section_font.setPointSizeF(opt.font.pointSizeF() * _CONTEXT_FONT_SCALE)
        title_metrics = QtGui.QFontMetrics(opt.font)
        section_metrics = QtGui.QFontMetrics(section_font)
        LINE_GAP: typing.Final = 2
        height = title_metrics.height() + LINE_GAP + section_metrics.height()
        text_rect.setTop(text_rect.top() + (text_rect.height() - height) // 2)
        selected = bool(opt.state & QtWidgets.QStyle.StateFlag.State_Selected)
        opt.palette.setCurrentColorGroup(
            QtGui.QPalette.ColorGroup.Active
            if opt.state & QtWidgets.QStyle.StateFlag.State_Active
            else QtGui.QPalette.ColorGroup.Inactive
        )
        painter.save()
        painter.setClipRect(opt.rect)
        painter.setPen(
            opt.palette.color(
                QtGui.QPalette.ColorRole.HighlightedText
                if selected
                else QtGui.QPalette.ColorRole.Text
            )
        )
        flags = QtCore.Qt.AlignmentFlag.AlignLeading | QtCore.Qt.AlignmentFlag.AlignTop
        painter.setFont(opt.font)
        painter.drawText(
            text_rect,
            flags,
            title_metrics.elidedText(title, opt.textElideMode, text_rect.width()),
        )
        text_rect.setTop(text_rect.top() + title_metrics.height() + LINE_GAP)
        painter.setFont(section_font)
        if not selected:
            painter.setOpacity(0.7)
        painter.drawText(
            text_rect,
            flags,
            section_metrics.elidedText(section, opt.textElideMode, text_rect.width()),
        )
        painter.restore()


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

    def focusOutEvent(self, e: QtGui.QFocusEvent, /) -> None:
        super().focusOutEvent(e)
        self.commit()


class _LabelFlagsEditor(QtWidgets.QWidget):
    value_changed = QtCore.Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self._value: dict[str, list[str]] | None = None
        self._accessible_note = ""
        self._rows: list[
            tuple[QtWidgets.QLineEdit, _PlainTextEdit, QtWidgets.QPushButton]
        ] = []
        self._grid = QtWidgets.QGridLayout()
        self._grid.setColumnStretch(0, 1)
        self._grid.setColumnStretch(1, 2)
        self._grid.addWidget(QtWidgets.QLabel(self.tr("Label pattern")), 0, 0)
        self._grid.addWidget(QtWidgets.QLabel(self.tr("Shape flags")), 0, 1)
        self._error = QtWidgets.QLabel()
        self._error.setWordWrap(True)
        self._error.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self._error.hide()
        self._add_button = QtWidgets.QPushButton(self.tr("Add rule"))
        self._add_button.setAutoDefault(False)
        self._add_button.clicked.connect(self._add_empty_rule)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self._grid)
        layout.addWidget(self._error)
        layout.addWidget(self._add_button, alignment=QtCore.Qt.AlignmentFlag.AlignLeft)
        self.setFocusProxy(self._add_button)

    def set_accessible_note(self, note: str, /) -> None:
        self._accessible_note = note
        self._validate()

    def set_value(self, *, value: dict[str, list[str]] | None) -> None:
        # A successful write syncs back into this control while it has focus.
        # Keep the current fields alive so typing and cursor position survive.
        if value == self._value:
            return
        self._value = value
        for row in self._rows:
            for widget in row:
                self._grid.removeWidget(widget)
                widget.deleteLater()
        self._rows.clear()
        for pattern, names in (value or {}).items():
            self._add_rule(pattern=pattern, names=names)
        self.setFocusProxy(self._rows[0][0] if self._rows else self._add_button)
        self._validate()

    def _add_empty_rule(self) -> None:
        self._add_rule(pattern="", names=[])
        self._validate()
        self._rows[-1][0].setFocus()

    def _add_rule(self, *, pattern: str, names: list[str]) -> None:
        pattern_edit = QtWidgets.QLineEdit(pattern)
        pattern_edit.setAccessibleName(self.tr("Label pattern"))
        flags_edit = _PlainTextEdit()
        flags_edit.setAccessibleName(self.tr("Shape flags"))
        flags_edit.setPlaceholderText(self.tr("One name per line"))
        flags_edit.setPlainText("\n".join(names))
        flags_edit.mark_committed()
        flags_edit.setFixedHeight(72)
        flags_edit.setTabChangesFocus(True)
        remove = QtWidgets.QPushButton(self.tr("Remove"))
        remove.setAutoDefault(False)
        remove.setAccessibleName(self.tr("Remove rule"))
        row = (pattern_edit, flags_edit, remove)
        self._rows.append(row)
        for column, widget in enumerate(row):
            self._grid.addWidget(
                widget,
                len(self._rows),
                column,
                alignment=QtCore.Qt.AlignmentFlag.AlignTop,
            )
        pattern_edit.textChanged.connect(self._validate)
        flags_edit.textChanged.connect(self._validate)
        pattern_edit.editingFinished.connect(self.commit)
        flags_edit.editing_finished.connect(self.commit)
        remove.clicked.connect(lambda: self._remove_rule(row=row))
        previous = self._rows[-2][2] if len(self._rows) > 1 else self
        for widget in (*row, self._add_button):
            QtWidgets.QWidget.setTabOrder(previous, widget)
            previous = widget
        self.setFocusProxy(self._rows[0][0])

    def _remove_rule(
        self, *, row: tuple[QtWidgets.QLineEdit, _PlainTextEdit, QtWidgets.QPushButton]
    ) -> None:
        self._rows.remove(row)
        for widget in row:
            self._grid.removeWidget(widget)
            widget.deleteLater()
        for index, remaining in enumerate(self._rows, start=1):
            for column, widget in enumerate(remaining):
                self._grid.addWidget(
                    widget,
                    index,
                    column,
                    alignment=QtCore.Qt.AlignmentFlag.AlignTop,
                )
        self.setFocusProxy(self._rows[0][0] if self._rows else self._add_button)
        self._add_button.setFocus()
        self.commit()

    def _validate(self) -> dict[str, list[str]] | None:
        rules: dict[str, list[str]] = {}
        error = ""
        for index, (pattern_edit, flags_edit, _) in enumerate(self._rows, start=1):
            pattern = pattern_edit.text()
            names = _parse_str_list(edit=flags_edit)
            if not pattern or not names:
                error = self.tr("Enter a pattern and at least one flag name.")
            elif pattern in rules:
                error = self.tr("Duplicate label pattern.")
            else:
                try:
                    re.compile(pattern)
                except re.error:
                    error = self.tr("Invalid regular expression.")
            if error:
                error = self.tr(
                    "Row {row}: {error} Changes have not been applied."
                ).format(row=index, error=error)
                break
            assert names is not None
            rules[pattern] = names
        self._error.setText(error)
        self._error.setVisible(bool(error))
        self.setAccessibleDescription(
            " ".join(part for part in (self._accessible_note, error) if part)
        )
        return None if error else rules

    def commit(self) -> None:
        rules = self._validate()
        if rules is None:
            return
        value = rules or None
        if value != self._value:
            self._value = value
            self.value_changed.emit(value)


class _ColorSwatchButton(QtWidgets.QPushButton):
    _rgb: tuple[int, int, int] = (0, 0, 0)

    def __init__(self) -> None:
        super().__init__()
        self._accessible_note = ""
        self.setFixedSize(48, 24)

    def get_rgb(self) -> tuple[int, int, int]:
        return self._rgb

    def set_rgb(self, rgb: tuple[int, int, int], /) -> None:
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

    def set_accessible_note(self, note: str, /) -> None:
        self._accessible_note = note
        self._update_accessible_description()

    def _update_accessible_description(self) -> None:
        description = self.toolTip()
        if self._accessible_note:
            description = f"{description}. {self._accessible_note}"
        self.setAccessibleDescription(description)


class _SettingHighlight(QtWidgets.QWidget):
    def paintEvent(self, _event: QtGui.QPaintEvent, /) -> None:
        # macOS lets users choose text-selection and accent colors independently.
        color = self.palette().color(
            QtGui.QPalette.ColorGroup.Active, QtGui.QPalette.ColorRole.Accent
        )
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        BORDER_WIDTH: typing.Final = 3
        CORNER_RADIUS: typing.Final = 6
        painter.setPen(QtGui.QPen(color, BORDER_WIDTH))
        color.setAlpha(35)
        painter.setBrush(color)
        inset = BORDER_WIDTH / 2
        painter.drawRoundedRect(
            QtCore.QRectF(self.rect()).adjusted(inset, inset, -inset, -inset),
            CORNER_RADIUS,
            CORNER_RADIUS,
        )


class _SettingsPage(QtWidgets.QWidget):
    def __init__(
        self,
        *,
        groups: Sequence[tuple[str, QtGui.QIcon, QtWidgets.QGroupBox]],
        editors: dict[tuple[str, ...], QtWidgets.QWidget],
    ) -> None:
        super().__init__()

        navigation = QtWidgets.QListWidget()
        navigation.setItemDelegate(_SearchResultDelegate(navigation))
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
        self._navigation = navigation
        self._sections = [(title, icon) for title, icon, _ in groups]
        self._navigation_padding = NAVIGATION_VERTICAL_PADDING
        self._show_sections()
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

        self._search = QtWidgets.QLineEdit()
        self._search.setPlaceholderText(self.tr("Search settings"))
        self._search.setAccessibleName(self.tr("Search settings"))
        self._search.setClearButtonEnabled(True)
        self._status = QtWidgets.QLabel()
        self._status.setWordWrap(True)
        self._status.hide()
        sidebar = QtWidgets.QWidget()
        sidebar.setFixedWidth(navigation_width)
        sidebar_layout = QtWidgets.QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.addWidget(self._search)
        sidebar_layout.addWidget(navigation, stretch=1)
        sidebar_layout.addWidget(self._status)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(sidebar)
        layout.addWidget(scroll_area, stretch=1)

        self._scroll_area = scroll_area
        self._content = content
        self._groups = [group_box for _title, _icon, group_box in groups]
        self._scrolling_to_group = False
        self._editors = editors
        self._search_index: list[tuple[schema.Setting, tuple[str, ...], str]] = []
        settings_by_path = {setting.key_path: setting for setting in schema.SETTINGS}
        for key_path, editor in editors.items():
            setting = settings_by_path[key_path]
            names = (
                setting.label,
                QtCore.QCoreApplication.translate("SettingsDialog", setting.label),
                ".".join(key_path),
            )
            metadata = [
                *names,
                setting.group,
                setting.note or "",
                setting.search_aliases,
            ]
            metadata += [
                QtCore.QCoreApplication.translate("SettingsDialog", text)
                for text in metadata
            ]
            if isinstance(editor, QtWidgets.QComboBox):
                for i in range(editor.count()):
                    metadata += [
                        editor.itemText(i),
                        str(editor.itemData(i)),
                        editor.itemData(i, _SOURCE_LABEL_ROLE),
                    ]
            self._search_index.append(
                (
                    setting,
                    tuple(name.casefold() for name in names),
                    " ".join(metadata).casefold(),
                )
            )
        # The editor the last activated search result led to, or None.
        self._destination: QtWidgets.QWidget | None = None
        self._highlight = _SettingHighlight(content)
        self._highlight.hide()
        self._highlight.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )
        content.installEventFilter(self)
        self._announcement_timer = QtCore.QTimer(self)
        self._announcement_timer.setSingleShot(True)
        self._announcement_timer.timeout.connect(self._announce_status)
        self._search.textChanged.connect(self._update_search)
        self._search.installEventFilter(self)
        navigation.installEventFilter(self)
        for widget in content.findChildren(QtWidgets.QWidget):
            widget.installEventFilter(self)

        self.setFocusProxy(self._search)
        for before, after in pairwise([self._search, navigation, *editors.values()]):
            QtWidgets.QWidget.setTabOrder(before, after)

        navigation.currentRowChanged.connect(self._scroll_to_group)
        navigation.itemClicked.connect(self._activate_item)
        scroll_area.verticalScrollBar().valueChanged.connect(
            self._sync_navigation_to_scroll
        )
        navigation.setCurrentRow(0)

    def showEvent(self, event: QtGui.QShowEvent, /) -> None:
        super().showEvent(event)
        self._search.clear()
        self.focus_search()

    def focus_search(self) -> None:
        self._search.setFocus(QtCore.Qt.FocusReason.ShortcutFocusReason)
        self._search.selectAll()

    def clear_search(self) -> bool:
        if not self._search.text().strip():
            return False
        self._search.clear()
        self.focus_search()
        return True

    def _show_sections(self) -> None:
        self._navigation.clear()
        self._navigation.setAccessibleName(self.tr("Settings sections"))
        for title, icon in self._sections:
            item = QtWidgets.QListWidgetItem(icon, title)
            item.setToolTip(title)
            self._navigation.addItem(item)
            size = self._navigation.sizeHintForIndex(
                self._navigation.indexFromItem(item)
            )
            size.setHeight(
                self._navigation.fontMetrics().height() + self._navigation_padding
            )
            item.setSizeHint(size)

    def _update_search(self, text: str, /) -> None:
        self._destination = None
        self._highlight.hide()
        with QtCore.QSignalBlocker(self._navigation):
            if not text.strip():
                self._show_sections()
                self._status.hide()
                self._announcement_timer.stop()
                self._sync_navigation_to_scroll(
                    self._scroll_area.verticalScrollBar().value()
                )
                return
            self._navigation.clear()
            self._navigation.setAccessibleName(self.tr("Matching settings"))
            matches = _find_settings(index=self._search_index, query=text)
            for setting in matches:
                title = QtCore.QCoreApplication.translate(
                    "SettingsDialog", setting.label
                )
                section = QtCore.QCoreApplication.translate(
                    "SettingsDialog", setting.group
                )
                item = QtWidgets.QListWidgetItem(f"{title}\n{section}")
                item.setData(QtCore.Qt.ItemDataRole.UserRole, setting.key_path)
                item.setData(
                    QtCore.Qt.ItemDataRole.AccessibleTextRole, f"{title}, {section}"
                )
                item.setToolTip(item.text())
                item.setSizeHint(
                    QtCore.QSize(
                        0,
                        self._navigation.fontMetrics().lineSpacing() * 2
                        + self._navigation_padding,
                    )
                )
                self._navigation.addItem(item)
            for index, group in enumerate(self._groups):
                if any(group.isAncestorOf(editor) for editor in self._editors.values()):
                    continue
                text = " ".join(
                    [
                        group.title(),
                        *(
                            label.text()
                            for label in group.findChildren(QtWidgets.QLabel)
                        ),
                    ]
                ).casefold()
                if all(term in text for term in self._search.text().casefold().split()):
                    item = QtWidgets.QListWidgetItem(group.title())
                    item.setData(QtCore.Qt.ItemDataRole.UserRole, index)
                    item.setData(
                        QtCore.Qt.ItemDataRole.AccessibleTextRole, group.title()
                    )
                    self._navigation.addItem(item)
        message = (
            self.tr("{count} matching settings").format(count=self._navigation.count())
            if self._navigation.count()
            else self.tr(
                "No matching settings in this dialog. Try another term or clear search."
            )
        )
        self._set_status(message)

    def _set_status(self, message: str, /) -> None:
        self._status.setText(message)
        self._status.show()
        self._queue_announcement(message)

    def _queue_announcement(self, message: str, /) -> None:
        self._announcement_message = message
        # Results update immediately; speech waits for a typing pause.
        ANNOUNCEMENT_DELAY_MS: typing.Final = 350
        self._announcement_timer.start(ANNOUNCEMENT_DELAY_MS)

    def _announce_status(self) -> None:
        if (
            self.isVisible()
            and self._search.text().strip()
            and QtGui.QAccessible.isActive()
        ):
            event = QtGui.QAccessibleAnnouncementEvent(
                self._status, self._announcement_message
            )
            event.setPoliteness(QtGui.QAccessible.AnnouncementPoliteness.Polite)
            QtGui.QAccessible.updateAccessibility(event)

    def _activate_item(self, item: QtWidgets.QListWidgetItem, /) -> None:
        if not self._search.text().strip():
            self._scroll_to_group(self._navigation.row(item))
            return
        destination = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if isinstance(destination, int):
            self.clear_search()
            self._scroll_to_group(destination)
            self._navigation.setFocus(QtCore.Qt.FocusReason.OtherFocusReason)
            return
        key_path = tuple(destination)
        editor = self._editors[key_path]
        row = editor.parentWidget()
        assert row is not None
        TOP_INSET: typing.Final = 16
        row_top = row.mapTo(self._content, QtCore.QPoint()).y()
        # Leave room below the final settings so they can also land near the top.
        self._content.setMinimumHeight(
            max(
                self._content.minimumSizeHint().height(),
                row_top + self._scroll_area.viewport().height() - TOP_INSET,
            )
        )
        self._scroll_area.ensureWidgetVisible(editor)
        group = row.parentWidget()
        assert group is not None
        group_layout = group.layout()
        assert group_layout is not None
        # Keep the section heading intact when its first setting is the destination.
        target = group if group_layout.indexOf(row) == 0 else row
        target_top = target.mapTo(self._content, QtCore.QPoint()).y()
        self._scroll_area.verticalScrollBar().setValue(target_top - TOP_INSET)
        self._navigation.setFocus(QtCore.Qt.FocusReason.OtherFocusReason)
        if editor.isEnabled():
            self._announcement_timer.stop()
            item.setData(QtCore.Qt.ItemDataRole.AccessibleDescriptionRole, "")
            self._status.setText(
                self.tr("{count} matching settings").format(
                    count=self._navigation.count()
                )
            )
        else:
            reason = row.toolTip()
            item.setData(QtCore.Qt.ItemDataRole.AccessibleDescriptionRole, reason)
            self._set_status(reason)
        self._destination = editor
        self._place_highlight()
        self._highlight.show()
        self._highlight.lower()

    def _place_highlight(self) -> None:
        if self._destination is None:
            return
        row = self._destination.parentWidget()
        assert row is not None
        self._highlight.setGeometry(
            QtCore.QRect(row.mapTo(self._content, QtCore.QPoint()), row.size())
        )

    def focusNextPrevChild(self, next: bool, /) -> bool:  # noqa: FBT001 -- QWidget override
        # Tab from an activated result enters that setting rather than the
        # first editor on the page. A disabled setting refuses focus, so
        # consuming Tab for it would strand focus in the result list.
        if (
            next
            and self._destination is not None
            and self._destination.isEnabled()
            and self._navigation.hasFocus()
        ):
            self._destination.setFocus(QtCore.Qt.FocusReason.TabFocusReason)
            return True
        return super().focusNextPrevChild(next)

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent, /) -> bool:
        if watched is self._content and event.type() == QtCore.QEvent.Type.Resize:
            self._place_highlight()
        if (
            event.type() == QtCore.QEvent.Type.FocusIn
            and isinstance(watched, QtWidgets.QWidget)
            and self._content.isAncestorOf(watched)
        ):
            self._scroll_area.ensureWidgetVisible(watched)
        # Editors that ignore Return propagate it up through the content widget,
        # so key handling is limited to the sidebar to keep the default button
        # and editor focus intact.
        if (
            watched in (self._search, self._navigation)
            and isinstance(event, QtGui.QKeyEvent)
            and event.type() == QtCore.QEvent.Type.KeyPress
        ):
            key = event.key()
            searching = bool(self._search.text().strip())
            if (
                watched is self._navigation
                and key == QtCore.Qt.Key.Key_Tab
                and not searching
                and self._navigation.currentRow() >= 0
            ):
                group = self._groups[self._navigation.currentRow()]
                for widget in group.findChildren(QtWidgets.QWidget):
                    if (
                        widget.isEnabled()
                        and widget.isVisible()
                        and widget.focusPolicy() & QtCore.Qt.FocusPolicy.TabFocus
                    ):
                        widget.setFocus(QtCore.Qt.FocusReason.TabFocusReason)
                        return True
            if (
                watched is self._search
                and searching
                and key in (QtCore.Qt.Key.Key_Up, QtCore.Qt.Key.Key_Down)
            ):
                # Browse results without leaving the search field; the list is
                # not focused, so announce the selection ourselves.
                QtWidgets.QApplication.sendEvent(self._navigation, event)
                item = self._navigation.currentItem()
                if item is not None:
                    self._queue_announcement(
                        item.data(QtCore.Qt.ItemDataRole.AccessibleTextRole)
                    )
                return True
            if key in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
                if searching and self._navigation.currentItem() is None:
                    self._navigation.setCurrentRow(0)
                item = self._navigation.currentItem()
                if item is not None and (watched is self._navigation or searching):
                    self._activate_item(item)
                # Consumed either way so Enter never reaches the default button.
                return True
        return super().eventFilter(watched, event)

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
        if self._search.text().strip() or not 0 <= index < len(self._groups):
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
        if self._scrolling_to_group or self._search.text().strip():
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
        *,
        config: dict,
        apply_setting: ApplySetting,
        preview_shape_color: PreviewShapeColor,
        open_as_text: Callable[[], None],
        models_widget: QtWidgets.QWidget | None = None,
        settings_editable: bool = True,  # noqa: FBT001 -- controls config editing
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
        for _, _, group_box in groups:
            group_box.setEnabled(settings_editable)
        self._models_index = len(groups)
        if models_widget is not None:
            model_group = QtWidgets.QGroupBox(self.tr("AI Models"))
            QtWidgets.QVBoxLayout(model_group).addWidget(models_widget)
            groups.append(
                (self.tr("AI Models"), new_icon("phosphor/sparkle.svg"), model_group)
            )
        page = _SettingsPage(groups=groups, editors=self._editors)
        self._page = page
        find_shortcut = QtGui.QShortcut(QtGui.QKeySequence.StandardKey.Find, self)
        find_shortcut.activated.connect(page.focus_search)

        open_button = QtWidgets.QPushButton(self.tr("Open config file as text…"))
        open_button.setToolTip(
            self.tr("Edits made in the text file apply after restart")
        )
        open_button.clicked.connect(open_as_text)
        open_button.setEnabled(settings_editable)
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

        QtWidgets.QWidget.setTabOrder(page, open_button)
        QtWidgets.QWidget.setTabOrder(open_button, close_button)

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

    def keyPressEvent(self, event: QtGui.QKeyEvent, /) -> None:
        if event.key() == QtCore.Qt.Key.Key_Escape and self._page.clear_search():
            event.accept()
            return
        super().keyPressEvent(event)

    def show_models(self) -> None:
        self._page.clear_search()
        self._page._navigation.setCurrentRow(self._models_index)

    def accept(self) -> None:
        # Flush text editors whose edits commit on focus-out: clicking Close
        # does not always move focus first, so apply pending input explicitly.
        # commit() is a no-op when the text is unchanged.
        for editor in self._editors.values():
            if isinstance(editor, _PlainTextEdit | _LabelFlagsEditor):
                editor.commit()
        super().accept()

    def reject(self) -> None:
        # Immediate-apply dialog: Escape and the window-close button discard
        # nothing, so treat them like Close and flush pending edits.
        self.accept()

    def set_value(self, *, key_path: tuple[str, ...], value: object) -> None:
        editor = self._editors[key_path]
        with QtCore.QSignalBlocker(editor):
            self._set_editor_value(editor=editor, value=value)
        if key_path == ("shape_color", "mode"):
            self._sync_shape_color_mode()

    def set_choice_enabled(
        self,
        *,
        key_path: tuple[str, ...],
        value: object,
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
        # Section headings are secondary to setting names, so they use the
        # same smaller size as the section line in search results.
        section_font = QtGui.QFont(self.font())
        section_font.setPointSizeF(section_font.pointSizeF() * _CONTEXT_FONT_SCALE)
        group_box.setFont(section_font)
        layout = QtWidgets.QVBoxLayout(group_box)
        for setting in settings:
            editor = self._create_editor(setting=setting)
            editor.setAccessibleName(self.tr(setting.label))
            if setting.note:
                note = self.tr(setting.note)
                if isinstance(editor, _ColorSwatchButton | _LabelFlagsEditor):
                    editor.set_accessible_note(note)
                else:
                    editor.setAccessibleDescription(note)
            self._editors[setting.key_path] = editor

            label_cell = self._build_label_cell(setting=setting, editor=editor)
            row = QtWidgets.QWidget()
            # Rows must not inherit the heading's smaller font. Re-setting the
            # size marks it as explicitly resolved; copying the dialog font
            # alone would resolve back to the group box.
            row_font = QtGui.QFont(self.font())
            row_font.setPointSizeF(row_font.pointSizeF())
            row.setFont(row_font)
            if setting.kind in ("str_list", "label_flags"):
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
                    label = setting.choice_labels[index]
                elif choice is None:
                    label = typing.cast(
                        str, QtCore.QT_TRANSLATE_NOOP("SettingsDialog", "(none)")
                    )
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
                (
                    typing.cast(
                        str,
                        QtCore.QT_TRANSLATE_NOOP("SettingsDialog", "System default"),
                    ),
                    None,
                ),
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
        if setting.kind == "label_flags":
            flags_editor = _LabelFlagsEditor()
            self._set_editor_value(editor=flags_editor, value=value)
            flags_editor.value_changed.connect(
                lambda rules: self._apply(setting.key_path, rules)
            )
            return flags_editor
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
        for index, (label, data) in enumerate(items):
            combo.addItem(self.tr(label), data)
            combo.setItemData(index, label, _SOURCE_LABEL_ROLE)
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
        elif isinstance(editor, _LabelFlagsEditor):
            assert value is None or isinstance(value, dict)
            editor.set_value(value=typing.cast(dict[str, list[str]] | None, value))
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
            row.setToolTip(
                ""
                if key_path == active_path
                else self.tr(
                    "Select {mode} in Shape Color Mode to edit this setting."
                ).format(mode=mode.itemText(mode.findData(key_path[1])))
            )


def _find_settings(
    *, index: Sequence[tuple[schema.Setting, tuple[str, ...], str]], query: str
) -> list[schema.Setting]:
    query = " ".join(query.casefold().split())
    if not query:
        return []
    terms = query.split()
    matches = [
        (
            0
            if query in names
            else 1
            if all(any(term in name for name in names) for term in terms)
            else 2,
            setting,
        )
        for setting, names, metadata in index
        if all(term in metadata for term in terms)
    ]
    return [setting for _, setting in sorted(matches, key=lambda match: match[0])]


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
