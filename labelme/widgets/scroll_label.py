from qtpy import QtWidgets


class ScrollLabel(QtWidgets.QScrollArea):
    def __init__(self, *args, **kwargs):
        QtWidgets.QScrollArea.__init__(self, *args, **kwargs)

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
