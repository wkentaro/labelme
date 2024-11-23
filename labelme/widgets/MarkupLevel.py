from qtpy import QtWidgets
from qtpy import QtGui
from qtpy.QtCore import Qt

from ..shape import ShapeClass

class MarkupLevelWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.setMinimumWidth(170)
        self.setLayout(QtWidgets.QVBoxLayout())
        self.layout().setSpacing(10)
        self.layout().setAlignment(Qt.AlignHCenter)

        label = QtWidgets.QLabel()
        label.setMaximumWidth(400)
        label.setText("Уровень разметки:")
        self.layout().addWidget(label, alignment = Qt.AlignHCenter)

        self.level_label = QtWidgets.QLabel()
        self.level_label.setMaximumWidth(400)
        font = self.font()
        font.setPointSize(24)
        self.level_label.setFont(font)
        self.layout().addWidget(self.level_label, alignment = Qt.AlignHCenter)

    def set_markup_level(self, selected_shape_class : ShapeClass) -> str:
        if selected_shape_class == ShapeClass.TEXT:
            self.level_label.setText("cтрока")
        elif selected_shape_class == ShapeClass.ROW:
            self.level_label.setText("буква")
        elif selected_shape_class is None:
            self.level_label.setText("текст")
        self.update()
