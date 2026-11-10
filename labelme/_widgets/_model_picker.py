from __future__ import annotations

from collections.abc import Collection
from collections.abc import Mapping
from collections.abc import Sequence

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets


class ModelPicker(QtWidgets.QComboBox):
    _options: list[tuple[str, str]]
    _available: set[str]
    _downloading: set[str]
    _selected: str
    _requested: str
    _unavailable: dict[str, str]

    model_changed = QtCore.Signal(str)
    download_requested = QtCore.Signal(str)
    manage_requested = QtCore.Signal()
    # Fires when label() or the status tooltip may have changed.
    display_changed = QtCore.Signal()

    def __init__(self, *, options: Sequence[tuple[str, str]]) -> None:
        super().__init__()
        self._options = list(options)
        self._available = {name for name, _ in options}
        self._downloading = set()
        self._selected = ""
        self._requested = ""
        self._unavailable = {}
        self._populate()
        self.currentIndexChanged.connect(self._on_changed)

    def _populate(self) -> None:
        with QtCore.QSignalBlocker(self):
            self.clear()
            for name, display in self._options:
                if name in self._available:
                    self.addItem(display, name)
            missing = [
                (name, display)
                for name, display in self._options
                if name not in self._available
            ]
            if missing:
                if self.count():
                    self.insertSeparator(self.count())
                self.addItem(self.tr("Download and use"))
                model = self.model()
                assert isinstance(model, QtGui.QStandardItemModel)
                header = model.item(self.count() - 1)
                assert header is not None
                header.setEnabled(False)
                for name, display in missing:
                    self.addItem(display, name)
            model = self.model()
            assert isinstance(model, QtGui.QStandardItemModel)
            for name, reason in self._unavailable.items():
                index = self.findData(name)
                if index < 0:
                    continue
                item = model.item(index)
                assert item is not None
                item.setEnabled(False)
                item.setToolTip(reason)
            self.insertSeparator(self.count())
            self.addItem(self.tr("Manage models…"), "manage")
            self._show_missing_selection()
            self.setCurrentIndex(self.findData(self._selected))
        self.display_changed.emit()

    def _show_missing_selection(self) -> None:
        self.setPlaceholderText(self.tr("Choose a model…"))
        status = ""
        if self._requested and self._requested not in self._available:
            display = dict(self._options)[self._requested]
            # The toolbar picker is too narrow for "Unavailable: <model>" in most
            # languages, so the model name stands alone, greyed out as a
            # placeholder, and the status goes to the tooltip.
            self.setPlaceholderText(display)
            status = (
                self.tr("Downloading: {model}")
                if self._requested in self._downloading
                else self.tr("Unavailable: {model}")
            ).format(model=display)
        self.setToolTip(status)

    def set_available_models(
        self, *, available: set[str], downloading: set[str]
    ) -> None:
        available = available.intersection(name for name, _ in self._options)
        if self._available == available and self._downloading == downloading:
            return
        self._available = available
        self._downloading = downloading
        # The remembered choice already lives in the config, so it is restored
        # as soon as its files exist; only other models stay unselected.
        self._selected = self._requested if self._requested in available else ""
        self._populate()

    def set_unavailable_models(self, *, unavailable: dict[str, str]) -> None:
        # Maps each model that the current context cannot use to the reason.
        # The selection stays, so the Setting is unchanged.
        if self._unavailable == unavailable:
            return
        self._unavailable = unavailable
        self._populate()

    def set_model_name(self, *, model_name: str) -> None:
        self._requested = model_name
        self._selected = model_name if model_name in self._available else ""
        self._show_missing_selection()
        with QtCore.QSignalBlocker(self):
            self.setCurrentIndex(self.findData(self._selected))
        self.display_changed.emit()

    def select_model(self, *, model_name: str) -> None:
        # Choosing a model that is not downloaded yet records the choice now;
        # it takes effect once the download finishes.
        self.set_model_name(model_name=model_name)
        self.model_changed.emit(model_name)

    def label(self) -> str:
        # A missing selection shows as the placeholder.
        return self.currentText() or self.placeholderText()

    def add_actions(
        self,
        *,
        menu: QtWidgets.QMenu,
        folded: Collection[str],
        notes: Mapping[str, str],
        sizes: Mapping[str, int],
        tips: Mapping[str, str],
    ) -> None:
        locale = self.locale()
        group = QtGui.QActionGroup(menu)
        more: QtWidgets.QMenu | None = None
        # Folded models follow the others, in a submenu at the section's end.
        for name, display in sorted(self._options, key=lambda o: o[0] in folded):
            target = menu
            if name in folded:
                if more is None:
                    # Parented, so it outlives this Python reference.
                    more = QtWidgets.QMenu(self.tr("More models…"), menu)
                    menu.addMenu(more)
                    more.setToolTipsVisible(True)
                target = more
            column = [notes[name]] if name in notes else []
            if name not in self._available and name in sizes:
                # What choosing it costs: a download before first use.
                size = sizes[name]
                column.append(
                    locale.formattedDataSize(
                        size,
                        0 if size < 2**30 else 1,
                        QtCore.QLocale.DataSizeFormat.DataSizeTraditionalFormat,
                    )
                )
            # Text after a tab shows in the menu's muted shortcut column.
            text = "\t".join([display, " · ".join(column)]) if column else display
            action = target.addAction(text)
            action.setCheckable(True)
            action.setChecked(name == self._selected)
            group.addAction(action)
            if name in self._unavailable:
                action.setEnabled(False)
                action.setToolTip(self._unavailable[name])
            elif name in tips:
                action.setToolTip(tips[name])
            # The combo's own handler downloads or selects the model.
            action.triggered.connect(
                lambda _=False, name=name: self.setCurrentIndex(self.findData(name))
            )

    def _on_changed(self, index: int, /) -> None:
        value = self.itemData(index)
        if not value:
            return
        if value in self._available:
            self._requested = value
            self._selected = value
            self.model_changed.emit(value)
            return
        with QtCore.QSignalBlocker(self):
            self.setCurrentIndex(self.findData(self._selected))
        if value == "manage":
            self.manage_requested.emit()
        else:
            self.download_requested.emit(value)
