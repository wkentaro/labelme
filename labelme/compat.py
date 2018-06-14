from qtpy import QT_VERSION
from qtpy import QtCore


QT5 = QT_VERSION[0] == '5'


if QT5:
    QPoint = QtCore.QPoint
else:
    QPoint = QtCore.QPointF


del QT_VERSION
del QtCore
