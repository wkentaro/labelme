from __future__ import annotations

import re
from typing import cast

from loguru import logger
from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

import labelme.utils

# TODO(unknown):
# - Calculate optimal position so as not to go out of screen area.


class LabelQLineEdit(QtWidgets.QLineEdit):
    def set_list_widget(self, list_widget: QtWidgets.QListWidget) -> None:
        self.list_widget = list_widget

    def keyPressEvent(self, a0: QtGui.QKeyEvent) -> None:
        if a0.key() in [QtCore.Qt.Key.Key_Up, QtCore.Qt.Key.Key_Down]:
            self.list_widget.keyPressEvent(a0)
        else:
            super().keyPressEvent(a0)


class LabelDialog(QtWidgets.QDialog):
    def __init__(
        self,
        text: str = "Enter object label",
        parent: QtWidgets.QWidget | None = None,
        labels: list[str] | None = None,
        sort_labels: bool = True,
        show_text_field: bool = True,
        completion: str = "startswith",
        fit_to_content: dict[str, bool] | None = None,
        flags: dict[str, list[str]] | None = None,
    ) -> None:
        super().__init__(parent)

        if fit_to_content is None:
            fit_to_content = {"row": False, "column": True}
        self._fit_to_content = fit_to_content
        self._sort_labels = sort_labels
        self._flags = flags or {}

        self.edit = self._build_label_edit(placeholder=text, has_flags=bool(flags))
        self.edit_group_id = self._build_group_id_edit()
        self.label_list = self._build_label_list(labels=labels)
        self.edit.set_list_widget(self.label_list)
        self._flags_layout = QtWidgets.QVBoxLayout()
        self._reset_flags()
        self.edit_description = self._build_description_edit()
        button_box = self._build_button_box()

        root = QtWidgets.QVBoxLayout(self)
        if show_text_field:
            edit_row = QtWidgets.QHBoxLayout()
            edit_row.addWidget(self.edit, stretch=6)
            edit_row.addWidget(self.edit_group_id, stretch=2)
            root.addLayout(edit_row)
        root.addWidget(button_box)
        root.addWidget(self.label_list)
        root.addItem(self._flags_layout)
        root.addWidget(self.edit_description)

        self.edit.setCompleter(self._build_completer(mode=completion))

    def _build_label_edit(self, placeholder: str, has_flags: bool) -> LabelQLineEdit:
        edit = LabelQLineEdit()
        edit.setPlaceholderText(placeholder)
        edit.setValidator(labelme.utils.label_validator())
        edit.editingFinished.connect(self._on_editing_finished)
        if has_flags:
            edit.textChanged.connect(self._on_text_changed)
        return edit

    def _build_group_id_edit(self) -> QtWidgets.QLineEdit:
        edit_group_id = QtWidgets.QLineEdit()
        edit_group_id.setPlaceholderText("Group ID")
        edit_group_id.setValidator(
            QtGui.QRegularExpressionValidator(QtCore.QRegularExpression(r"\d*"))
        )
        return edit_group_id

    def _build_label_list(self, labels: list[str] | None) -> QtWidgets.QListWidget:
        label_list = QtWidgets.QListWidget()
        if self._fit_to_content["row"]:
            label_list.setHorizontalScrollBarPolicy(
                QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
        if self._fit_to_content["column"]:
            label_list.setVerticalScrollBarPolicy(
                QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
        if labels:
            label_list.addItems(labels)
        if self._sort_labels:
            label_list.sortItems()
        else:
            label_list.setDragDropMode(
                QtWidgets.QAbstractItemView.DragDropMode.InternalMove
            )
        label_list.currentItemChanged.connect(self._on_label_selected)
        label_list.itemDoubleClicked.connect(self._on_label_double_clicked)
        label_list.setFixedHeight(150)
        return label_list

    def _build_description_edit(self) -> QtWidgets.QTextEdit:
        description = QtWidgets.QTextEdit()
        description.setPlaceholderText("Label description")
        description.setFixedHeight(50)
        return description

    def _build_button_box(self) -> QtWidgets.QDialogButtonBox:
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel,
            orientation=QtCore.Qt.Orientation.Horizontal,
            parent=self,
        )
        button_box.accepted.connect(self._validate)
        button_box.rejected.connect(self.reject)
        return button_box

    def _build_completer(self, mode: str) -> QtWidgets.QCompleter:
        completer = QtWidgets.QCompleter()
        if mode == "startswith":
            completer.setCompletionMode(
                QtWidgets.QCompleter.CompletionMode.InlineCompletion
            )
        elif mode == "contains":
            completer.setCompletionMode(
                QtWidgets.QCompleter.CompletionMode.PopupCompletion
            )
            completer.setFilterMode(QtCore.Qt.MatchFlag.MatchContains)
        else:
            raise ValueError(f"Unsupported completion: {mode}")
        completer.setModel(self.label_list.model())
        return completer

    def add_label_history(self, label: str) -> None:
        if self.label_list.findItems(label, QtCore.Qt.MatchFlag.MatchExactly):
            return
        self.label_list.addItem(label)
        if self._sort_labels:
            self.label_list.sortItems()

    def _on_label_selected(self, item: QtWidgets.QListWidgetItem) -> None:
        self.edit.setText(item.text())

    def _validate(self) -> None:
        if not self.edit.isEnabled():
            self.accept()
            return

        if self.edit.text().strip():
            self.accept()

    def _on_label_double_clicked(self, _: QtWidgets.QListWidgetItem) -> None:
        self._validate()

    def _on_editing_finished(self) -> None:
        self.edit.setText(self.edit.text().strip())

    def _on_text_changed(self, label_new: str) -> None:
        # keep state of shared flags
        flags_old = self._current_flags()

        flags_new = {}
        for pattern, keys in self._flags.items():
            if re.match(pattern, label_new):
                for key in keys:
                    flags_new[key] = flags_old.get(key, False)
        self._set_flags(flags_new)

    def _delete_flags(self) -> None:
        while self._flags_layout.count() > 0:
            item = self._flags_layout.takeAt(0)
            if item is None:
                break
            widget = item.widget()
            if widget is not None:
                widget.setParent(QtWidgets.QWidget())

    def _reset_flags(self, label: str = "") -> None:
        flags = {}
        for pattern, keys in self._flags.items():
            if re.match(pattern, label):
                for key in keys:
                    flags[key] = False
        self._set_flags(flags)

    def _set_flags(self, flags: dict[str, bool]) -> None:
        self._delete_flags()
        for key, checked in flags.items():
            item = QtWidgets.QCheckBox(key, self)
            item.setChecked(checked)
            self._flags_layout.addWidget(item)
            item.show()

    def _current_flags(self) -> dict[str, bool]:
        return {
            cb.text(): cb.isChecked()
            for i in range(self._flags_layout.count())
            if (item := self._flags_layout.itemAt(i)) is not None
            and (cb := cast(QtWidgets.QCheckBox, item.widget())) is not None
        }

    def _current_group_id(self) -> int | None:
        group_id = self.edit_group_id.text()
        if group_id:
            return int(group_id)
        return None

    def _restore_or_reset_flags(self, text: str, flags: dict[str, bool] | None) -> None:
        if flags:
            self._set_flags(flags)
        else:
            self._reset_flags(text)

    def popup(
        self,
        text: str | None = None,
        move: bool = True,
        flags: dict[str, bool] | None = None,
        group_id: int | None = None,
        description: str | None = None,
        flags_disabled: bool = False,
    ) -> tuple[str, dict[str, bool], int | None, str] | tuple[None, None, None, None]:
        # text=None preserves whatever was previously typed in the edit field.
        if text is None:
            text = self.edit.text()

        self._fit_label_list_to_content()
        self._apply_dialog_state(
            text=text,
            group_id=group_id,
            description=description or "",
            flags=flags,
            flags_disabled=flags_disabled,
        )
        self.edit.setFocus(QtCore.Qt.FocusReason.PopupFocusReason)
        if move:
            self.move(QtGui.QCursor.pos())

        if not self.exec():
            return None, None, None, None
        return self._read_dialog_state()

    def _fit_label_list_to_content(self) -> None:
        if self._fit_to_content["row"]:
            self.label_list.setMinimumHeight(
                self.label_list.sizeHintForRow(0) * self.label_list.count() + 2
            )
        if self._fit_to_content["column"]:
            self.label_list.setMinimumWidth(self.label_list.sizeHintForColumn(0) + 2)

    def _apply_dialog_state(
        self,
        text: str,
        group_id: int | None,
        description: str,
        flags: dict[str, bool] | None,
        flags_disabled: bool,
    ) -> None:
        self.edit_description.setPlainText(description)
        self._restore_or_reset_flags(text=text, flags=flags)
        if flags_disabled:
            for i in range(self._flags_layout.count()):
                item = self._flags_layout.itemAt(i)
                if item is not None:
                    widget = item.widget()
                    if widget is not None:
                        widget.setDisabled(True)

        self.edit.setText(text)
        self.edit.selectAll()

        if group_id is None:
            self.edit_group_id.clear()
        else:
            self.edit_group_id.setText(str(group_id))

        self._highlight_matching_label(text)

    def _highlight_matching_label(self, text: str) -> None:
        items = self.label_list.findItems(text, QtCore.Qt.MatchFlag.MatchFixedString)
        if not items:
            return
        if len(items) != 1:
            logger.warning(f"Label list has duplicate '{text}'")
        self.label_list.setCurrentItem(items[0])
        self.edit.completer().setCurrentRow(self.label_list.row(items[0]))

    def _read_dialog_state(
        self,
    ) -> tuple[str, dict[str, bool], int | None, str]:
        return (
            self.edit.text(),
            self._current_flags(),
            self._current_group_id(),
            self.edit_description.toPlainText(),
        )
