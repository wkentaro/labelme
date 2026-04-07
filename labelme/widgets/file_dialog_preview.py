from __future__ import annotations

import json
from typing import cast

from PyQt5 import QtCore
from PyQt5 import QtGui
from PyQt5 import QtWidgets

_PREVIEW_SIZE = 300
_PREVIEW_PADDING = 30


class ScrollAreaPreview(QtWidgets.QScrollArea):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)

        container = QtWidgets.QWidget(self)
        self.setWidget(container)

        container_layout = QtWidgets.QVBoxLayout(container)

        self.label = QtWidgets.QLabel(container)
        self.label.setWordWrap(True)
        container_layout.addWidget(self.label)

    def setText(self, text: str) -> None:
        self.label.setText(text)

    def setPixmap(self, pixmap: QtGui.QPixmap) -> None:
        self.label.setPixmap(pixmap)

    def clear(self) -> None:
        self.label.clear()


class FileDialogPreview(QtWidgets.QFileDialog):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setOption(self.DontUseNativeDialog, True)

        self.labelPreview = ScrollAreaPreview(parent=self)
        self.labelPreview.setFixedSize(_PREVIEW_SIZE, _PREVIEW_SIZE)
        self.labelPreview.setHidden(True)

        preview_layout = QtWidgets.QVBoxLayout()
        preview_layout.addWidget(self.labelPreview)
        preview_layout.addStretch()

        self.setFixedSize(self.width() + _PREVIEW_SIZE, self.height())
        grid = cast(QtWidgets.QGridLayout, self.layout())
        grid.addLayout(preview_layout, 1, 3, 1, 1)
        self.currentChanged.connect(self.onChange)

    def onChange(self, path: str) -> None:
        if path.lower().endswith(".json"):
            try:
                with open(path, encoding="utf-8") as fp:
                    parsed = json.load(fp)
                text = json.dumps(parsed, indent=4, sort_keys=False)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                text = f"Cannot preview: {exc}"
            self.labelPreview.setText(text)
            self.labelPreview.label.setAlignment(
                QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop
            )
            self.labelPreview.setHidden(False)
        else:
            pixmap = QtGui.QPixmap(path)
            if pixmap.isNull():
                self.labelPreview.clear()
                self.labelPreview.setHidden(True)
            else:
                max_dim = _PREVIEW_SIZE - _PREVIEW_PADDING
                scaled_pixmap = pixmap.scaled(
                    max_dim,
                    max_dim,
                    QtCore.Qt.KeepAspectRatio,
                    QtCore.Qt.SmoothTransformation,
                )
                self.labelPreview.setPixmap(scaled_pixmap)
                self.labelPreview.label.setAlignment(QtCore.Qt.AlignCenter)
                self.labelPreview.setHidden(False)
