import json
from typing import cast

from PyQt5 import QtCore
from PyQt5 import QtGui
from PyQt5 import QtWidgets


class ScrollAreaPreview(QtWidgets.QScrollArea):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.setWidgetResizable(True)

        content = QtWidgets.QWidget(self)
        self.setWidget(content)

        lay = QtWidgets.QVBoxLayout(content)

        self.label = QtWidgets.QLabel(content)
        self.label.setWordWrap(True)

        lay.addWidget(self.label)

    def setText(self, text):
        self.label.setText(text)

    def setPixmap(self, pixmap):
        self.label.setPixmap(pixmap)

    def clear(self):
        self.label.clear()


class FileDialogPreview(QtWidgets.QFileDialog):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setOption(self.DontUseNativeDialog, True)

        self.labelPreview = ScrollAreaPreview(self)
        self.labelPreview.setFixedSize(300, 300)
        self.labelPreview.setHidden(True)

        box = QtWidgets.QVBoxLayout()
        box.addWidget(self.labelPreview)
        box.addStretch()

        self.setFixedSize(self.width() + 300, self.height())
        layout = self.layout()
        layout = cast(QtWidgets.QGridLayout, layout)
        layout.addLayout(box, 1, 3, 1, 1)
        self.currentChanged.connect(self.onChange)

    def onChange(self, path):
        if path.lower().endswith(".json"):
            with open(path) as f:
                data = json.load(f)
                self.labelPreview.setText(json.dumps(data, indent=4, sort_keys=False))
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
                self.labelPreview.setPixmap(
                    pixmap.scaled(
                        self.labelPreview.width() - 30,
                        self.labelPreview.height() - 30,
                        QtCore.Qt.KeepAspectRatio,
                        QtCore.Qt.SmoothTransformation,
                    )
                )
                self.labelPreview.label.setAlignment(QtCore.Qt.AlignCenter)
                self.labelPreview.setHidden(False)
