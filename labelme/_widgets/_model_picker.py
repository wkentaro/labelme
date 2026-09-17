from __future__ import annotations

from collections.abc import Sequence

from PySide6 import QtCore
from PySide6 import QtWidgets


class ModelPicker(QtWidgets.QComboBox):
    model_changed = QtCore.Signal(str)
    manage_requested = QtCore.Signal()

    def __init__(self, *, options: Sequence[tuple[str, str]]) -> None:
        super().__init__()
        self._options = options
        self._available = {name for name, _ in options}
        self._selected = ""
        self._requested = ""
        self._populate()
        self.currentIndexChanged.connect(self._on_changed)

    def _populate(self) -> None:
        with QtCore.QSignalBlocker(self):
            self.clear()
            for name, display in self._options:
                if name in self._available:
                    self.addItem(display, name)
            self.addItem(
                self.tr("Manage models…")
                if self._available
                else self.tr("Download a model…"),
                "manage",
            )
            self._show_missing_selection()
            self.setCurrentIndex(self.findData(self._selected))

    def _show_missing_selection(self) -> None:
        self.setPlaceholderText(
            self.tr("Choose a model…")
            if self._available
            else self.tr("Download a model…")
        )
        if self._requested and self._requested not in self._available:
            display = dict(self._options)[self._requested]
            self.setPlaceholderText(
                self.tr("Unavailable: {model}").format(model=display)
            )

    def set_available_models(self, *, available: set[str]) -> None:
        available = available.intersection(name for name, _ in self._options)
        if self._available == available:
            return
        self._available = available
        # The remembered choice already lives in the config, so it is restored
        # as soon as its files exist; only other models stay unselected.
        self._selected = self._requested if self._requested in available else ""
        self._populate()

    def set_model_name(self, *, model_name: str) -> None:
        self._requested = model_name
        self._selected = model_name if model_name in self._available else ""
        self._show_missing_selection()
        with QtCore.QSignalBlocker(self):
            self.setCurrentIndex(self.findData(self._selected))

    def _on_changed(self, index: int, /) -> None:
        value = self.itemData(index)
        if value == "manage":
            with QtCore.QSignalBlocker(self):
                self.setCurrentIndex(self.findData(self._selected))
            self.manage_requested.emit()
        elif value:
            self._requested = value
            self._selected = value
            self.model_changed.emit(value)
