from __future__ import annotations

import json
from typing import cast

from PyQt5 import QtCore
from PyQt5 import QtGui
from PyQt5 import QtWidgets

PREVIEW_DIMENSION = 300
PREVIEW_PADDING = 30


class ScrollAreaPreview(QtWidgets.QScrollArea):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)

        self.setWidgetResizable(True)

        container = QtWidgets.QWidget()
        self.label = QtWidgets.QLabel()
        self.label.setWordWrap(True)

        vbox = QtWidgets.QVBoxLayout(container)
        vbox.addWidget(self.label)

        self.setWidget(container)

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

        self.labelPreview = ScrollAreaPreview(self)
        self.labelPreview.setFixedSize(PREVIEW_DIMENSION, PREVIEW_DIMENSION)
        self.labelPreview.setVisible(False)

        preview_column = QtWidgets.QVBoxLayout()
        preview_column.addWidget(self.labelPreview)
        preview_column.addStretch()

        self.setFixedSize(self.width() + PREVIEW_DIMENSION, self.height())
        layout = self.layout()
        layout = cast(QtWidgets.QGridLayout, layout)
        layout.addLayout(preview_column, 1, 3, 1, 1)
        self.currentChanged.connect(self.onChange)

    def onChange(self, path: str) -> None:
        if path.lower().endswith(".json"):
            try:
                with open(path) as f:
                    data = json.load(f)
                text = json.dumps(data, indent=4, sort_keys=False)
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                text = f"Cannot preview: {e}"
            self.labelPreview.setText(text)
            self.labelPreview.label.setAlignment(
                QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop
            )
            self.labelPreview.setVisible(True)
        else:
            pixmap = QtGui.QPixmap(path)
            if pixmap.isNull():
                self.labelPreview.clear()
                self.labelPreview.setVisible(False)
            else:
                available_width = self.labelPreview.width() - PREVIEW_PADDING
                available_height = self.labelPreview.height() - PREVIEW_PADDING
                scaled = pixmap.scaled(
                    available_width,
                    available_height,
                    QtCore.Qt.KeepAspectRatio,
                    QtCore.Qt.SmoothTransformation,
                )
                self.labelPreview.setPixmap(scaled)
                self.labelPreview.label.setAlignment(QtCore.Qt.AlignCenter)
                self.labelPreview.setVisible(True)
