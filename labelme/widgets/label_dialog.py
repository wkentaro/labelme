import re
from typing import Optional

from loguru import logger
from PyQt5 import QtCore
from PyQt5 import QtGui
from PyQt5 import QtWidgets

import labelme.utils


class LabelQLineEdit(QtWidgets.QLineEdit):
    """A QLineEdit that forwards Up/Down key events to a paired list widget."""

    def setListWidget(self, list_widget: QtWidgets.QListWidget) -> None:
        """Pair this line edit with *list_widget* for keyboard navigation."""
        self.list_widget = list_widget

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() in (QtCore.Qt.Key_Up, QtCore.Qt.Key_Down):
            self.list_widget.keyPressEvent(event)
        else:
            super().keyPressEvent(event)


class LabelDialog(QtWidgets.QDialog):
    """Dialog for entering a shape label, flags, group ID, and description."""

    def __init__(
        self,
        text: str = "Enter object label",
        parent: Optional[QtWidgets.QWidget] = None,
        labels: Optional[list] = None,
        sort_labels: bool = True,
        show_text_field: bool = True,
        completion: str = "startswith",
        fit_to_content: Optional[dict] = None,
        flags: Optional[dict] = None,
    ) -> None:
        if fit_to_content is None:
            fit_to_content = {"row": False, "column": True}
        self._fit_to_content = fit_to_content

        super().__init__(parent)

        # Label text input
        self.edit = LabelQLineEdit()
        self.edit.setPlaceholderText(text)
        self.edit.setValidator(labelme.utils.labelValidator())
        self.edit.editingFinished.connect(self.postProcess)
        if flags:
            self.edit.textChanged.connect(self.updateFlags)

        # Group ID input
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

        # OK / Cancel buttons
        self.buttonBox = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel,
            QtCore.Qt.Horizontal,
            self,
        )
        self.buttonBox.accepted.connect(self.validate)
        self.buttonBox.rejected.connect(self.reject)
        layout.addWidget(self.buttonBox)

        # Label history list
        self.labelList = QtWidgets.QListWidget()
        if self._fit_to_content["row"]:
            self.labelList.setHorizontalScrollBarPolicy(
                QtCore.Qt.ScrollBarAlwaysOff
            )
        if self._fit_to_content["column"]:
            self.labelList.setVerticalScrollBarPolicy(
                QtCore.Qt.ScrollBarAlwaysOff
            )
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

        # Per-label flag checkboxes
        if flags is None:
            flags = {}
        self._flags = flags
        self.flagsLayout = QtWidgets.QVBoxLayout()
        self.resetFlags()
        layout.addItem(self.flagsLayout)
        self.edit.textChanged.connect(self.updateFlags)

        # Description text area
        self.editDescription = QtWidgets.QTextEdit()
        self.editDescription.setPlaceholderText("Label description")
        self.editDescription.setFixedHeight(50)
        layout.addWidget(self.editDescription)

        self.setLayout(layout)

        # Auto-completion for the label input
        completer = QtWidgets.QCompleter()
        if completion == "startswith":
            completer.setCompletionMode(QtWidgets.QCompleter.InlineCompletion)
        elif completion == "contains":
            completer.setCompletionMode(QtWidgets.QCompleter.PopupCompletion)
            completer.setFilterMode(QtCore.Qt.MatchContains)
        else:
            raise ValueError(f"Unsupported completion: {completion}")
        completer.setModel(self.labelList.model())
        self.edit.setCompleter(completer)

    def addLabelHistory(self, label: str) -> None:
        """Add *label* to the label list if not already present."""
        if self.labelList.findItems(label, QtCore.Qt.MatchExactly):
            return
        self.labelList.addItem(label)
        if self._sort_labels:
            self.labelList.sortItems()

    def labelSelected(self, item: QtWidgets.QListWidgetItem) -> None:
        self.edit.setText(item.text())

    def validate(self) -> None:
        """Accept the dialog when the label field contains non-empty text."""
        if not self.edit.isEnabled():
            self.accept()
            return
        if self._stripped_text():
            self.accept()

    def _stripped_text(self) -> str:
        """Return the current label text with leading/trailing whitespace removed."""
        return self.edit.text().strip()

    def labelDoubleClicked(self, item: QtWidgets.QListWidgetItem) -> None:
        self.validate()

    def postProcess(self) -> None:
        self.edit.setText(self._stripped_text())

    def updateFlags(self, label_new: str) -> None:
        # Keep the state of flags that are shared between the old and new label.
        flags_old = self.getFlags()
        flags_new: dict[str, bool] = {}
        for pattern, keys in self._flags.items():
            if re.match(pattern, label_new):
                for key in keys:
                    flags_new[key] = flags_old.get(key, False)
        self.setFlags(flags_new)

    def deleteFlags(self) -> None:
        """Remove all flag checkboxes from the flags layout."""
        for i in reversed(range(self.flagsLayout.count())):
            widget = self.flagsLayout.itemAt(i).widget()
            self.flagsLayout.removeWidget(widget)
            widget.setParent(QtWidgets.QWidget())

    def resetFlags(self, label: str = "") -> None:
        """Reset all flag checkboxes to unchecked for the given *label*."""
        flags: dict[str, bool] = {}
        for pattern, keys in self._flags.items():
            if re.match(pattern, label):
                for key in keys:
                    flags[key] = False
        self.setFlags(flags)

    def setFlags(self, flags: dict[str, bool]) -> None:
        """Replace current flag checkboxes with those in *flags*."""
        self.deleteFlags()
        for key, checked in flags.items():
            checkbox = QtWidgets.QCheckBox(key, self)
            checkbox.setChecked(checked)
            self.flagsLayout.addWidget(checkbox)
            checkbox.show()

    def getFlags(self) -> dict[str, bool]:
        """Return the current state of all flag checkboxes."""
        flags: dict[str, bool] = {}
        for i in range(self.flagsLayout.count()):
            checkbox = self.flagsLayout.itemAt(i).widget()
            assert isinstance(checkbox, QtWidgets.QCheckBox)
            flags[checkbox.text()] = checkbox.isChecked()
        return flags

    def getGroupId(self) -> Optional[int]:
        """Return the group ID entered by the user, or ``None`` if empty."""
        group_id = self.edit_group_id.text()
        if group_id:
            return int(group_id)
        return None

    def popUp(
        self,
        text: Optional[str] = None,
        move: bool = True,
        flags: Optional[dict] = None,
        group_id: Optional[int] = None,
        description: Optional[str] = None,
        flags_disabled: bool = False,
    ) -> tuple:
        """Show the dialog and return ``(label, flags, group_id, description)``.

        Returns a tuple of four ``None`` values when the dialog is cancelled.
        """
        if self._fit_to_content["row"]:
            self.labelList.setMinimumHeight(
                self.labelList.sizeHintForRow(0) * self.labelList.count() + 2
            )
        if self._fit_to_content["column"]:
            self.labelList.setMinimumWidth(self.labelList.sizeHintForColumn(0) + 2)

        # If text is None, keep the label that was previously entered.
        if text is None:
            text = self.edit.text()
        # Description is always reset (unlike the label text field).
        self.editDescription.setPlainText(description if description is not None else "")

        if flags:
            self.setFlags(flags)
        else:
            self.resetFlags(text)

        if flags_disabled:
            for i in range(self.flagsLayout.count()):
                self.flagsLayout.itemAt(i).widget().setDisabled(True)

        self.edit.setText(text)
        self.edit.setSelection(0, len(text))

        if group_id is None:
            self.edit_group_id.clear()
        else:
            self.edit_group_id.setText(str(group_id))

        # Sync the label list selection with the current text.
        items = self.labelList.findItems(text, QtCore.Qt.MatchFixedString)
        if items:
            if len(items) != 1:
                logger.warning(f"Label list has duplicate '{text}'")
            self.labelList.setCurrentItem(items[0])
            self.edit.completer().setCurrentRow(self.labelList.row(items[0]))

        self.edit.setFocus(QtCore.Qt.PopupFocusReason)
        if move:
            self.move(QtGui.QCursor.pos())

        if self.exec_():
            return (
                self.edit.text(),
                self.getFlags(),
                self.getGroupId(),
                self.editDescription.toPlainText(),
            )
        return None, None, None, None
