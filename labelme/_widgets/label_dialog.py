from __future__ import annotations

import dataclasses
from collections.abc import Collection
from typing import Final
from typing import Literal

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from .._label_flags import compile_label_flags

LabelDialogField = Literal["label", "flags", "group_id", "description"]


@dataclasses.dataclass(frozen=True)
class LabelDialogEntry:
    label: str
    flags: dict[str, bool]
    group_id: int | None
    description: str


_PLACEHOLDER_TEXT: Final[str] = "Enter object label"


class LabelDialog(QtWidgets.QDialog):
    """Dialog for entering label, group id, description, and flags."""

    def __init__(
        self,
        *,
        text: str = _PLACEHOLDER_TEXT,
        parent: QtWidgets.QWidget | None = None,
        labels: list[str] | None = None,
        sort_labels: bool = True,
        show_text_field: bool = True,
        completion: str = "startswith",
        fit_to_content: dict[str, bool] | None = None,
        flags: dict[str, list[str]] | None = None,
        label_history: list[str] | None = None,
    ) -> None:
        LABEL_LIST_HEIGHT: Final[int] = 150

        super().__init__(parent)
        dialog_name = self.tr("Shape Label")
        self.setWindowTitle(dialog_name)
        self.setAccessibleName(dialog_name)

        self._sort_labels = sort_labels
        self._flags_spec = compile_label_flags(label_flags=flags)
        self._label_history = label_history[:] if label_history is not None else []
        # Fields the current popup shows read-only because the caller has no
        # single value for them (a mixed multi-selection).
        self._locked: frozenset[LabelDialogField] = frozenset()
        # A popup opened without a label starts from the last one accepted.
        self._last_label = ""
        # The flags currently on show, keyed by flag name, so a flag named by
        # two matching label_flags patterns gets exactly one checkbox.
        self._flag_checkboxes: dict[str, QtWidgets.QCheckBox] = {}
        # Checked state per flag key, remembered for the lifetime of one popup.
        # The checkboxes themselves cannot hold it: editing the label rebuilds
        # them, and an intermediate keystroke that matches no pattern destroys
        # them entirely.
        self._flag_states: dict[str, bool] = {}

        if fit_to_content is None:
            fit_to_content = {"row": False, "column": True}
        self._fit_to_content = fit_to_content

        # Build widgets
        self.edit = QtWidgets.QLineEdit()
        self.edit.setPlaceholderText(text)
        self.edit.setAccessibleName(self.tr("Label"))

        group_id_name = self.tr("Group ID")
        self.edit_group_id = QtWidgets.QLineEdit()
        self.edit_group_id.setPlaceholderText(group_id_name)
        self.edit_group_id.setAccessibleName(group_id_name)
        self.edit_group_id.setValidator(
            QtGui.QRegularExpressionValidator(QtCore.QRegularExpression(r"[0-9]*"))
        )

        description_name = self.tr("Description")
        self.edit_description = QtWidgets.QTextEdit()
        self.edit_description.setPlaceholderText(description_name)
        self.edit_description.setAccessibleName(description_name)
        self.edit_description.setFixedHeight(50)

        self.label_list = QtWidgets.QListWidget()
        self.label_list.setFixedHeight(LABEL_LIST_HEIGHT)

        # Configure label list
        if sort_labels:
            self.label_list.setDragDropMode(
                QtWidgets.QAbstractItemView.DragDropMode.NoDragDrop
            )
        else:
            self.label_list.setDragDropMode(
                QtWidgets.QAbstractItemView.DragDropMode.InternalMove
            )

        if fit_to_content["row"]:
            self.label_list.setHorizontalScrollBarPolicy(
                QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
        if fit_to_content["column"]:
            self.label_list.setVerticalScrollBarPolicy(
                QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )

        # Set up completer bound to label_list's model
        completer = self._make_completer(completion=completion)
        self.edit.setCompleter(completer)
        # Up/Down are taken before the line edit sees them so the arrow keys walk
        # the label list while every other key keeps editing the text.
        self.edit.installEventFilter(self)

        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel,
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        self._ok_button = button_box.button(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
        )

        # Build layout
        main_layout = QtWidgets.QVBoxLayout()
        self.setLayout(main_layout)

        if show_text_field:
            top_row = QtWidgets.QHBoxLayout()
            top_row.addWidget(self.edit, stretch=4)
            top_row.addWidget(self.edit_group_id, stretch=1)
            main_layout.addLayout(top_row)
        else:
            self.edit.setParent(None)

        main_layout.addWidget(button_box)
        main_layout.addWidget(self.label_list)

        self._flags_container = QtWidgets.QWidget()
        self._flags_layout = QtWidgets.QVBoxLayout()
        self._flags_layout.setContentsMargins(0, 0, 0, 0)
        self._flags_layout.setSpacing(0)
        self._flags_container.setLayout(self._flags_layout)

        self._flags_scroll = QtWidgets.QScrollArea()
        self._flags_scroll.setWidgetResizable(True)
        self._flags_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self._flags_scroll.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._flags_scroll.setWidget(self._flags_container)
        main_layout.addWidget(self._flags_scroll)

        main_layout.addWidget(self.edit_description)

        # Connect signals
        self.edit.textChanged.connect(self._on_text_changed)
        self.label_list.currentItemChanged.connect(self._on_label_selected)
        self.label_list.itemDoubleClicked.connect(self._submit_item)

        # Populate initial labels
        for label in dict.fromkeys([*(labels or []), *self._label_history]):
            self.label_list.addItem(label)
        if sort_labels:
            self.label_list.sortItems()

        self._refresh_ok_button()

    @property
    def label_history(self) -> list[str]:
        return self._label_history[:]

    def _make_completer(self, *, completion: str) -> QtWidgets.QCompleter:
        if completion == "startswith":
            completer = QtWidgets.QCompleter(self.label_list.model())
            completer.setCompletionMode(
                QtWidgets.QCompleter.CompletionMode.InlineCompletion
            )
            return completer
        elif completion == "contains":
            completer = QtWidgets.QCompleter(self.label_list.model())
            completer.setCompletionMode(
                QtWidgets.QCompleter.CompletionMode.PopupCompletion
            )
            completer.setFilterMode(QtCore.Qt.MatchFlag.MatchContains)
            return completer
        else:
            raise ValueError(f"Unknown completion mode: {completion!r}")

    def _on_text_changed(self, text: str, /) -> None:
        # Leading whitespace never belongs to a label, so undo it as it is typed;
        # the re-entrant signal then handles the corrected text.
        if text != text.lstrip():
            self.edit.setText(text.lstrip())
            return
        self._refresh_ok_button()
        if "flags" not in self._locked:
            self._update_flags(text)

    def _refresh_ok_button(self) -> None:
        # Return only ever reaches an enabled default button, so disabling OK is
        # what keeps a blank label from being submitted.
        self._ok_button.setEnabled(
            "label" in self._locked or bool(self.edit.text().strip())
        )

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent, /) -> bool:
        if watched is self.edit and event.type() == QtCore.QEvent.Type.KeyPress:
            assert isinstance(event, QtGui.QKeyEvent)
            step = {QtCore.Qt.Key.Key_Up: -1, QtCore.Qt.Key.Key_Down: 1}.get(
                QtCore.Qt.Key(event.key())
            )
            if step is not None:
                row = self.label_list.currentRow() + step
                self.label_list.setCurrentRow(
                    min(max(row, 0), self.label_list.count() - 1)
                )
                return True
        return super().eventFilter(watched, event)

    def _on_label_selected(
        self,
        current: QtWidgets.QListWidgetItem | None,
        _previous: QtWidgets.QListWidgetItem | None,
        /,
    ) -> None:
        if current is None:
            return
        self.edit.setText(current.text())

    def _submit_item(self, item: QtWidgets.QListWidgetItem, /) -> None:
        self.label_list.setCurrentItem(item)
        self._ok_button.click()

    def _clear_flag_checkboxes(self) -> None:
        self._flag_checkboxes.clear()
        while self._flags_layout.count():
            item = self._flags_layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _update_flags(self, text: str, /) -> None:
        self._flag_states.update(self._collect_flags())
        flags: dict[str, bool] = {}
        for pattern, flag_keys in self._flags_spec.items():
            if not pattern.match(text):
                continue
            for key in flag_keys:
                flags[key] = self._flag_states.get(key, False)
        self._set_flag_checkboxes(flags=flags)

    def add_label_history(self, *, label: str) -> None:
        if label not in self._label_history:
            self._label_history.append(label)

        if self.label_list.findItems(label, QtCore.Qt.MatchFlag.MatchExactly):
            return
        self.label_list.addItem(label)
        if self._sort_labels:
            self.label_list.sortItems()

    def set_predefined_labels(self, *, labels: list[str]) -> None:
        history_extras = [h for h in self._label_history if h not in labels]
        all_labels = list(dict.fromkeys(labels)) + history_extras

        self.label_list.clear()
        for label in all_labels:
            self.label_list.addItem(label)

        if self._sort_labels:
            self.label_list.sortItems()

    def remember_label(self, *, label: str) -> None:
        self._last_label = label

    def _find_label_row(self, text: str, /) -> int:
        # Match through the model so the highlight folds case the way Qt's own
        # text matching does; Python's folding differs on the sharp s, say.
        model = self.label_list.model()
        hits = model.match(
            model.index(0, 0),
            QtCore.Qt.ItemDataRole.DisplayRole,
            text,
            flags=QtCore.Qt.MatchFlag.MatchFixedString,
        )
        return hits[0].row() if hits else -1

    def popup(
        self,
        *,
        text: str | None = None,
        flags: dict[str, bool] | None = None,
        group_id: int | None = None,
        description: str | None = None,
        locked: Collection[LabelDialogField] = (),
        move: bool = True,
        position: QtCore.QPoint | None = None,
    ) -> LabelDialogEntry | None:
        self._locked = frozenset(locked)
        # Drop the previous popup's checkboxes and their remembered states so a
        # fresh popup starts unchecked. This has to precede setText() below,
        # whose textChanged signal would otherwise re-seed the states from the
        # previous popup's checkboxes; the flags block below rebuilds them.
        self._flag_states.clear()
        self._clear_flag_checkboxes()

        # A locked field shows nothing: the caller's value is not shared by the
        # whole selection, and the field is skipped when the entry is applied.
        for name, widgets in self._get_field_widgets().items():
            for widget in widgets:
                widget.setEnabled(name not in self._locked)
        if "label" in self._locked:
            text = ""
        elif text is None:
            text = self._last_label
        if "group_id" in self._locked:
            group_id = None
        if "description" in self._locked:
            description = None
        if "flags" in self._locked:
            flags = {}

        self.edit.setText(text)
        # Read the text back: a stored label with leading whitespace is shown
        # normalized, and the flags and list match must follow what is shown.
        text = self.edit.text()
        self.edit.selectAll()
        self.edit_group_id.setText("" if group_id is None else str(group_id))
        self.edit_description.setPlainText(description or "")
        if flags is None:
            self._update_flags(text)
        else:
            self._set_flag_checkboxes(flags=flags)

        self.label_list.setCurrentRow(self._find_label_row(text))

        self._fit_label_list_to_content()
        self._refresh_ok_button()
        self.edit.setFocus(QtCore.Qt.FocusReason.PopupFocusReason)

        if move:
            target = position if position is not None else QtGui.QCursor.pos()
            self._move_within_screen(target)
            # frameGeometry() lacks the window-manager decoration size until the
            # dialog is mapped, so re-clamp once exec() has shown it. Clamp only
            # (no re-anchor to target): a full re-move visibly jerks the already
            # visible dialog, while the clamp is a no-op unless it overflows.
            QtCore.QTimer.singleShot(0, lambda: self._clamp_within_screen(target))

        if self.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return None

        # The flag checkboxes follow the text, so normalize it before they are
        # collected: "cat " must yield the flags of "cat", not none.
        self.edit.setText(self.edit.text().strip())
        group_id_text = self.edit_group_id.text()
        entry = LabelDialogEntry(
            label=self.edit.text(),
            flags=self._collect_flags(),
            group_id=int(group_id_text) if group_id_text else None,
            description=self.edit_description.toPlainText(),
        )
        # A locked label is accepted as blank, and the next new-shape popup
        # starts blank too, exactly as a cancelled locked edit leaves it.
        self.remember_label(label=entry.label)
        return entry

    def _get_field_widgets(
        self,
    ) -> dict[LabelDialogField, tuple[QtWidgets.QWidget, ...]]:
        return {
            "label": (self.edit, self.label_list),
            "flags": (self._flags_container,),
            "group_id": (self.edit_group_id,),
            "description": (self.edit_description,),
        }

    def _set_flag_checkboxes(self, *, flags: dict[str, bool]) -> None:
        FLAGS_SCROLL_MAX_HEIGHT: Final[int] = 150

        self._clear_flag_checkboxes()
        for key, checked in flags.items():
            checkbox = QtWidgets.QCheckBox(key)
            checkbox.setChecked(checked)
            self._flag_checkboxes[key] = checkbox
            self._flags_layout.addWidget(checkbox)
            # A widget added to a visible layout stays hidden until the event
            # loop activates the layout, and the layout counts hidden widgets as
            # empty, so the container hint below would be momentarily 0 and
            # would pin the scroll area shut for the rest of the popup.
            checkbox.show()

        content_height = self._flags_container.sizeHint().height()
        self._flags_scroll.setFixedHeight(min(content_height, FLAGS_SCROLL_MAX_HEIGHT))

    def _collect_flags(self) -> dict[str, bool]:
        return {key: cb.isChecked() for key, cb in self._flag_checkboxes.items()}

    def _fit_label_list_to_content(self) -> None:
        if self._fit_to_content["row"]:
            self.label_list.setMinimumHeight(
                self.label_list.sizeHintForRow(0) * self.label_list.count() + 2
            )
        if self._fit_to_content["column"]:
            self.label_list.setMinimumWidth(self.label_list.sizeHintForColumn(0) + 2)

    def _move_within_screen(self, target: QtCore.QPoint, /) -> None:
        self.adjustSize()
        # setGeometry() anchors the client area, unlike move() which anchors the
        # window frame: the content corner lands at target, not the title bar's.
        self.setGeometry(QtCore.QRect(target, self.size()))
        self._clamp_within_screen(target)

    def _clamp_within_screen(self, target: QtCore.QPoint, /) -> None:
        screen = (
            QtGui.QGuiApplication.screenAt(target)
            or QtGui.QGuiApplication.primaryScreen()
        )
        if screen is None:
            return
        available = screen.availableGeometry()

        # Nudge by the actual frame overflow (frameGeometry() includes the
        # window-manager decoration) so the title bar and borders stay on screen,
        # not just the content rect.
        frame = self.frameGeometry()
        dx = min(0, available.right() - frame.right())
        dx = max(dx, available.left() - frame.left())
        dy = min(0, available.bottom() - frame.bottom())
        dy = max(dy, available.top() - frame.top())
        if dx or dy:
            self.move(self.x() + dx, self.y() + dy)
