from __future__ import annotations

import re
from typing import cast

from loguru import logger
from PyQt5 import QtCore
from PyQt5 import QtGui
from PyQt5 import QtWidgets

import labelme.utils

# TODO(unknown):
# - Calculate optimal position so as not to go out of screen area.


class LabelQLineEdit(QtWidgets.QLineEdit):
    def setListWidget(self, list_widget: QtWidgets.QListWidget) -> None:
        self.list_widget = list_widget

    def keyPressEvent(self, a0: QtGui.QKeyEvent) -> None:
        if a0.key() in [QtCore.Qt.Key_Up, QtCore.Qt.Key_Down]:
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
        if fit_to_content is None:
            fit_to_content = {"row": False, "column": True}
        self._fit_to_content = fit_to_content

        super().__init__(parent)
        self.edit = LabelQLineEdit()
        self.edit.setPlaceholderText(text)
        self.edit.setValidator(labelme.utils.labelValidator())
        self.edit.editingFinished.connect(self.postProcess)
        self._has_flag_definitions = bool(flags)
        self.edit_group_id = QtWidgets.QLineEdit()
        self.edit_group_id.setPlaceholderText("Group ID")
        self.edit_group_id.setValidator(
            QtGui.QRegExpValidator(QtCore.QRegExp(r"\d*"), None)
        )
        layout = QtWidgets.QVBoxLayout()
        if show_text_field:
            layout_edit = QtWidgets.QHBoxLayout()
            layout_edit.addWidget(self.edit, 6)
            layout_edit.addWidget(self.edit_group_id, 2)
            layout.addLayout(layout_edit)
        self.buttonBox = bb = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel,
            QtCore.Qt.Horizontal,
            self,
        )
        bb.accepted.connect(self.validate)
        bb.rejected.connect(self.reject)
        layout.addWidget(bb)
        self.labelList = QtWidgets.QListWidget()
        if self._fit_to_content["row"]:
            self.labelList.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        if self._fit_to_content["column"]:
            self.labelList.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self._sort_labels = sort_labels
        if labels:
            self.labelList.addItems(labels)
        if self._sort_labels:
            self.labelList.sortItems()
        else:
            self.labelList.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.labelList.currentItemChanged.connect(self.labelSelected)
        self.labelList.itemDoubleClicked.connect(self.labelDoubleClicked)
        self.labelList.setFixedHeight(150)
        self.edit.setListWidget(self.labelList)
        layout.addWidget(self.labelList)
        self._flags = flags if flags is not None else {}
        self.flagsLayout = QtWidgets.QVBoxLayout()
        self.resetFlags()
        layout.addItem(self.flagsLayout)
        if self._has_flag_definitions:
            self.edit.textChanged.connect(self.updateFlags)
        self.editDescription = QtWidgets.QTextEdit()
        self.editDescription.setPlaceholderText("Label description")
        self.editDescription.setFixedHeight(50)
        layout.addWidget(self.editDescription)
        self.setLayout(layout)
        completer = QtWidgets.QCompleter()
        if completion == "startswith":
            completer.setCompletionMode(QtWidgets.QCompleter.InlineCompletion)
            # Default settings.
            # completer.setFilterMode(QtCore.Qt.MatchStartsWith)
        elif completion == "contains":
            completer.setCompletionMode(QtWidgets.QCompleter.PopupCompletion)
            completer.setFilterMode(QtCore.Qt.MatchContains)
        else:
            raise ValueError(f"Unsupported completion: {completion}")
        completer.setModel(self.labelList.model())
        self.edit.setCompleter(completer)

    def addLabelHistory(self, label: str) -> None:
        if self.labelList.findItems(label, QtCore.Qt.MatchExactly):
            return
        self.labelList.addItem(label)
        if self._sort_labels:
            self.labelList.sortItems()

    def labelSelected(self, item: QtWidgets.QListWidgetItem) -> None:
        self.edit.setText(item.text())

    def validate(self) -> None:
        if not self.edit.isEnabled():
            self.accept()
            return

        if self._get_stripped_text():
            self.accept()

    def _get_stripped_text(self) -> str:
        text = self.edit.text()
        if hasattr(text, "strip"):
            return str(text.strip())
        if hasattr(text, "trimmed"):
            return str(text.trimmed())
        return str(text)

    def labelDoubleClicked(self, item: QtWidgets.QListWidgetItem) -> None:
        self.validate()

    def postProcess(self) -> None:
        self.edit.setText(self._get_stripped_text())

    def updateFlags(self, label_new: str) -> None:
        previous_state = self.getFlags()
        merged: dict[str, bool] = {}
        for pattern, flag_names in self._flags.items():
            if re.match(pattern, label_new):
                for name in flag_names:
                    merged[name] = previous_state.get(name, False)
        self.setFlags(merged)

    def deleteFlags(self) -> None:
        while self.flagsLayout.count() > 0:
            widget = self.flagsLayout.takeAt(0).widget()
            if widget is not None:
                widget.setParent(QtWidgets.QWidget())

    def resetFlags(self, label: str = "") -> None:
        matched_flags: dict[str, bool] = {}
        for pattern, flag_names in self._flags.items():
            if re.match(pattern, label):
                matched_flags.update({name: False for name in flag_names})
        self.setFlags(matched_flags)

    def setFlags(self, flags: dict[str, bool]) -> None:
        self.deleteFlags()
        for name, checked in flags.items():
            checkbox = QtWidgets.QCheckBox(name, self)
            checkbox.setChecked(checked)
            self.flagsLayout.addWidget(checkbox)
            checkbox.show()

    def getFlags(self) -> dict[str, bool]:
        result: dict[str, bool] = {}
        for idx in range(self.flagsLayout.count()):
            checkbox = cast(QtWidgets.QCheckBox, self.flagsLayout.itemAt(idx).widget())
            result[checkbox.text()] = checkbox.isChecked()
        return result

    def getGroupId(self) -> int | None:
        group_id = self.edit_group_id.text()
        if group_id:
            return int(group_id)
        return None

    def _restoreOrResetFlags(self, flags: dict[str, bool] | None, label: str) -> None:
        if flags is not None and len(flags) > 0:
            self.setFlags(flags)
        else:
            self.resetFlags(label)

    def popUp(
        self,
        text: str | None = None,
        move: bool = True,
        flags: dict[str, bool] | None = None,
        group_id: int | None = None,
        description: str | None = None,
        flags_disabled: bool = False,
    ) -> tuple[str, dict[str, bool], int | None, str] | tuple[None, None, None, None]:
        if self._fit_to_content["row"]:
            self.labelList.setMinimumHeight(
                self.labelList.sizeHintForRow(0) * self.labelList.count() + 2
            )
        if self._fit_to_content["column"]:
            self.labelList.setMinimumWidth(self.labelList.sizeHintForColumn(0) + 2)
        if text is None:
            text = self.edit.text()
        self.editDescription.setPlainText(description or "")
        self._restoreOrResetFlags(flags=flags, label=text)
        if flags_disabled:
            for idx in range(self.flagsLayout.count()):
                self.flagsLayout.itemAt(idx).widget().setDisabled(True)
        self.edit.setText(text)
        self.edit.setSelection(0, len(text))
        if group_id is not None:
            self.edit_group_id.setText(str(group_id))
        else:
            self.edit_group_id.clear()
        matched_items = self.labelList.findItems(text, QtCore.Qt.MatchFixedString)
        if matched_items:
            if len(matched_items) != 1:
                logger.warning(f"Label list has duplicate '{text}'")
            self.labelList.setCurrentItem(matched_items[0])
            row = self.labelList.row(matched_items[0])
            self.edit.completer().setCurrentRow(row)
        self.edit.setFocus(QtCore.Qt.PopupFocusReason)
        if move:
            self.move(QtGui.QCursor.pos())
        accepted = self.exec_()
        if not accepted:
            return (None, None, None, None)
        return (
            self.edit.text(),
            self.getFlags(),
            self.getGroupId(),
            self.editDescription.toPlainText(),
        )
