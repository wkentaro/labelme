from __future__ import annotations

import typing
from collections.abc import Callable

from PyQt5 import QtCore
from PyQt5 import QtGui
from PyQt5 import QtWidgets

from labelme._config import _schema as schema

ApplySetting = Callable[[tuple[str, ...], object], bool]


class _PlainTextEdit(QtWidgets.QPlainTextEdit):
    editing_finished = QtCore.pyqtSignal()

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


class SettingsDialog(QtWidgets.QDialog):
    def __init__(
        self,
        config: dict,
        apply_setting: ApplySetting,
        open_as_text: Callable[[], None],
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Settings"))

        self._config = config
        self._apply_setting = apply_setting
        self._editors: dict[tuple[str, ...], QtWidgets.QWidget] = {}

        tabs = QtWidgets.QTabWidget()
        for section in typing.get_args(schema.Section):
            settings = [s for s in schema.SETTINGS if s.section == section]
            if not settings:
                continue
            tabs.addTab(self._build_page(settings=settings), self.tr(section))

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
        layout.addWidget(tabs, stretch=1)
        layout.addLayout(button_layout)
        self.setLayout(layout)
        self.resize(640, 460)

        self._sync_validate_label_gate()

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

    def _read_value(self, key_path: tuple[str, ...]) -> object:
        node: object = self._config
        for key in key_path:
            if not isinstance(node, dict):
                raise TypeError(f"config path {key_path} is not a mapping at {key!r}")
            node = node[key]
        return node

    def _build_page(self, settings: list[schema.Setting]) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        for setting in settings:
            editor = self._create_editor(setting=setting)
            self._editors[setting.key_path] = editor

            label = QtWidgets.QLabel(self.tr(setting.label))
            label.setWordWrap(True)
            row = QtWidgets.QWidget()
            if setting.kind == "str_list":
                row_layout = QtWidgets.QVBoxLayout(row)
                row_layout.addWidget(label)
            else:
                row_layout = QtWidgets.QHBoxLayout(row)
                row_layout.addWidget(label, stretch=1)
            row_layout.addWidget(editor)
            layout.addWidget(row)
        layout.addStretch(1)
        return page

    def _create_editor(self, setting: schema.Setting) -> QtWidgets.QWidget:
        value = self._read_value(setting.key_path)
        if setting.kind == "bool":
            check = QtWidgets.QCheckBox()
            self._set_editor_value(editor=check, value=value)
            check.toggled.connect(
                lambda checked: self._apply(setting.key_path, checked)
            )
            return check
        if setting.kind == "enum":
            assert setting.choices is not None
            combo = QtWidgets.QComboBox()
            combo.setMinimumWidth(140)
            for choice in setting.choices:
                combo.addItem(
                    self.tr("(none)") if choice is None else str(choice), choice
                )
            self._set_editor_value(editor=combo, value=value)
            combo.currentIndexChanged.connect(
                lambda: self._apply(setting.key_path, combo.currentData())
            )
            return combo
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

    def _set_editor_value(self, editor: QtWidgets.QWidget, value: object) -> None:
        if isinstance(editor, QtWidgets.QCheckBox):
            editor.setChecked(bool(value))
        elif isinstance(editor, QtWidgets.QComboBox):
            editor.setCurrentIndex(max(editor.findData(value), 0))
        elif isinstance(editor, _PlainTextEdit):
            items = value if isinstance(value, list) else []
            editor.setPlainText("\n".join(str(item) for item in items))
            editor.mark_committed()

    def _apply(self, key_path: tuple[str, ...], value: object) -> bool:
        if self._apply_setting(key_path, value):
            return True
        # The write failed and the in-memory config was left unchanged, so reset
        # the editor to the last-saved value rather than show a phantom edit that
        # never persisted.
        self._revert_editor(key_path=key_path)
        return False

    def _revert_editor(self, key_path: tuple[str, ...]) -> None:
        # blockSignals stops the reset from re-triggering apply.
        editor = self._editors[key_path]
        editor.blockSignals(True)
        self._set_editor_value(editor=editor, value=self._read_value(key_path))
        editor.blockSignals(False)

    def _on_labels_edited(self, edit: _PlainTextEdit) -> None:
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


def _parse_str_list(*, edit: _PlainTextEdit) -> list[str] | None:
    items: list[str] = []
    for line in edit.toPlainText().splitlines():
        item = line.strip()
        if item and item not in items:
            items.append(item)
    return items or None
