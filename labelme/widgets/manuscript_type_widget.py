from qtpy import QtWidgets
from qtpy import QtCore
from enum import Enum
from PyQt5.QtCore import Qt

class ManuscriptType(Enum):
    USTAV = "Устав"
    HALF_USTAV = "Полуустав"
    CURSIVE = "Скоропись"

class ManuscriptTypeWidget(QtWidgets.QWidget):
    manuscript_type_changed = QtCore.Signal()
    
    def __init__(self, value):
        super().__init__()
        self.setLayout(QtWidgets.QVBoxLayout())
        self.layout().addWidget(QtWidgets.QLabel(self.tr("Тип письма:")), 0, Qt.AlignHCenter)
        self.combo_box = TypeComboBox(value)
        self.combo_box.currentTextChanged.connect(self._type_changed)
        self.layout().addWidget(self.combo_box)
        
    def _type_changed(self):
        self.manuscript_type_changed.emit()
    
    def GetCurrentValue(self):
        value = self.combo_box.currentData()
        return value
    
    def LoadSetType(self, type):
        self.combo_box.setCurrentText(type.value)

class TypeComboBox(QtWidgets.QComboBox):
    def __init__(self, value):
        super().__init__()
        for type in ManuscriptType:
            self.addItem(type.value, type)
        self.setCurrentText(value.value)
        