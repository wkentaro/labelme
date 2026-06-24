from __future__ import annotations

import re
from typing import Final

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from .._utils import label_validator

_PLACEHOLDER_TEXT: Final[str] = "Enter object label"
_GROUP_ID_PLACEHOLDER: Final[str] = "Group ID"
_DESCRIPTION_PLACEHOLDER: Final[str] = "Description"


class LabelQLineEdit(QtWidgets.QLineEdit):
    """QLineEdit that forwards Up/Down key events to a paired list widget."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.list_widget: QtWidgets.QListWidget | None = None

    def set_list_widget(self, list_widget: QtWidgets.QListWidget) -> None:
        self.list_widget = list_widget

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        key = event.key()
        if key in (QtCore.Qt.Key.Key_Up, QtCore.Qt.Key.Key_Down):
            if self.list_widget is not None:
                QtWidgets.QApplication.sendEvent(self.list_widget, event)
            return
        super().keyPressEvent(event)


class LabelDialog(QtWidgets.QDialog):
    """Dialog for entering label, group id, description, and flags."""

    def __init__(
        self,
        text: str = _PLACEHOLDER_TEXT,
        parent: QtWidgets.QWidget | None = None,
        labels: list[str] | None = None,
        sort_labels: bool = True,
        show_text_field: bool = True,
        completion: str = "startswith",
        fit_to_content: dict[str, bool] | None = None,
        flags: dict[str, list[str]] | None = None,
    ) -> None:
        super().__init__(parent)

        self._sort_labels = sort_labels
        self._flags_spec: dict[str, list[str]] = flags or {}
        self._label_history: list[str] = []
        self._flags_disabled = False

        if fit_to_content is None:
            fit_to_content = {"row": False, "column": True}
        self._fit_to_content = fit_to_content

        # Build widgets
        self.edit = LabelQLineEdit()
        self.edit.setPlaceholderText(text)
        self.edit.setValidator(label_validator())

        self.edit_group_id = QtWidgets.QLineEdit()
        self.edit_group_id.setPlaceholderText(_GROUP_ID_PLACEHOLDER)
        self.edit_group_id.setValidator(
            QtGui.QRegularExpressionValidator(QtCore.QRegularExpression(r"[0-9]*"))
        )

        self.edit_description = QtWidgets.QTextEdit()
        self.edit_description.setPlaceholderText(_DESCRIPTION_PLACEHOLDER)
        self.edit_description.setFixedHeight(50)

        self.label_list = QtWidgets.QListWidget()
        self.label_list.setFixedHeight(150)

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
        self.edit.set_list_widget(self.label_list)

        # Button box
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel,
        )
        button_box.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).clicked.connect(
            self._on_ok_clicked
        )
        button_box.rejected.connect(self.reject)

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
        main_layout.addWidget(self._flags_container)

        main_layout.addWidget(self.edit_description)

        # Connect signals
        self.edit.editingFinished.connect(self._strip_edit_text)
        self.edit.textChanged.connect(self._update_flags)
        self.label_list.currentItemChanged.connect(self._on_label_selected)
        self.label_list.itemDoubleClicked.connect(self._on_item_double_clicked)

        # Populate initial labels
        if labels is not None:
            for label in labels:
                self.label_list.addItem(label)
            if sort_labels:
                self.label_list.sortItems()

    def _make_completer(self, completion: str) -> QtWidgets.QCompleter:
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

    def _strip_edit_text(self) -> None:
        self.edit.setText(self.edit.text().strip())

    def _on_label_selected(
        self,
        current: QtWidgets.QListWidgetItem | None,
        previous: QtWidgets.QListWidgetItem | None,
    ) -> None:
        if current is None:
            return
        self.edit.setText(current.text())

    def _on_item_double_clicked(self, item: QtWidgets.QListWidgetItem) -> None:
        self.label_list.setCurrentItem(item)
        self._on_ok_clicked()

    def _on_ok_clicked(self) -> None:
        if not self.edit.isEnabled() or self.edit.text().strip():
            self.accept()

    def _flag_checkboxes(self) -> list[QtWidgets.QCheckBox]:
        checkboxes: list[QtWidgets.QCheckBox] = []
        for i in range(self._flags_layout.count()):
            item = self._flags_layout.itemAt(i)
            widget = item.widget() if item is not None else None
            if isinstance(widget, QtWidgets.QCheckBox):
                checkboxes.append(widget)
        return checkboxes

    def _clear_flags_layout(self) -> None:
        while self._flags_layout.count():
            item = self._flags_layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _update_flags(self, text: str) -> None:
        current_states = {cb.text(): cb.isChecked() for cb in self._flag_checkboxes()}
        self._clear_flags_layout()

        for pattern, flag_keys in self._flags_spec.items():
            if re.match(pattern, text):
                for key in flag_keys:
                    checkbox = QtWidgets.QCheckBox(key)
                    if key in current_states:
                        checkbox.setChecked(current_states[key])
                    checkbox.setEnabled(not self._flags_disabled)
                    self._flags_layout.addWidget(checkbox)

    def add_label_history(self, label: str) -> None:
        if label not in self._label_history:
            self._label_history.append(label)

        if not self.label_list.findItems(label, QtCore.Qt.MatchFlag.MatchExactly):
            self.label_list.addItem(label)
            if self._sort_labels:
                self.label_list.sortItems()

    def set_predefined_labels(self, labels: list[str]) -> None:
        history_extras = [h for h in self._label_history if h not in labels]
        all_labels = list(dict.fromkeys(labels)) + history_extras

        self.label_list.clear()
        for label in all_labels:
            self.label_list.addItem(label)

        if self._sort_labels:
            self.label_list.sortItems()

    def popup(
        self,
        text: str | None = None,
        move: bool = True,
        flags: dict[str, bool] | None = None,
        group_id: int | None = None,
        description: str | None = None,
        flags_disabled: bool = False,
    ) -> tuple[str, dict[str, bool], int | None, str] | tuple[None, None, None, None]:
        if text is not None:
            self.edit.setText(text)
        self.edit.selectAll()

        self.edit_description.setPlainText(description or "")

        if group_id is None:
            self.edit_group_id.setText("")
        else:
            self.edit_group_id.setText(str(group_id))

        self._flags_disabled = flags_disabled
        if flags is not None:
            self._show_popup_flags(flags)
        else:
            self._update_flags(self.edit.text())

        matches = self.label_list.findItems(
            self.edit.text(), QtCore.Qt.MatchFlag.MatchFixedString
        )
        if matches:
            self.label_list.setCurrentItem(matches[0])

        self._fit_label_list_to_content()
        self.edit.setFocus(QtCore.Qt.FocusReason.PopupFocusReason)

        if move:
            cursor_pos = QtGui.QCursor.pos()
            self.move(cursor_pos)

        result = self.exec()

        if result == QtWidgets.QDialog.DialogCode.Accepted:
            label = self.edit.text()
            returned_flags = self._collect_flags()
            gid_text = self.edit_group_id.text()
            returned_group_id: int | None = int(gid_text) if gid_text else None
            returned_description = self.edit_description.toPlainText()
            return label, returned_flags, returned_group_id, returned_description

        return None, None, None, None

    def _show_popup_flags(self, flags: dict[str, bool]) -> None:
        self._clear_flags_layout()
        for key, checked in flags.items():
            checkbox = QtWidgets.QCheckBox(key)
            checkbox.setChecked(checked)
            checkbox.setEnabled(not self._flags_disabled)
            self._flags_layout.addWidget(checkbox)

    def _collect_flags(self) -> dict[str, bool]:
        return {cb.text(): cb.isChecked() for cb in self._flag_checkboxes()}

    def _fit_label_list_to_content(self) -> None:
        if self._fit_to_content["row"]:
            self.label_list.setMinimumHeight(
                self.label_list.sizeHintForRow(0) * self.label_list.count() + 2
            )
        if self._fit_to_content["column"]:
            self.label_list.setMinimumWidth(self.label_list.sizeHintForColumn(0) + 2)
