from qtpy import QT_VERSION
from qtpy import QtCore
from qtpy import QtGui
from qtpy import QtWidgets

import labelme.utils
from labelme.logger import logger
from labelme.widgets.label_dialog import LabelQLineEdit

QT5 = QT_VERSION[0] == "5"

class LabelDialog(QtWidgets.QDialog):
    def __init__(
        self,
        parent=None
    ):
        pass
    