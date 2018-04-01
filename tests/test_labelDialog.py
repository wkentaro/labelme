try:
    from PyQt5 import QtCore
    from PyQt5 import QtWidgets
except ImportError:
    from PyQt4 import QtCore
    from PyQt4 import QtGui as QtWidgets

from labelme import labelDialog


def test_LabelQLineEdit(qtbot):
    list_widget = QtWidgets.QListWidget()
    list_widget.addItems([
        'bicycle',
        'car',
        'cat',
        'dog',
        'person',
    ])
    widget = labelDialog.LabelQLineEdit()
    widget.setListWidget(list_widget)
    qtbot.addWidget(widget)

    # key press to navigate in label list
    item = widget.list_widget.findItems('bicycle', QtCore.Qt.MatchExactly)[0]
    widget.list_widget.setCurrentItem(item)
    assert widget.list_widget.currentItem().text() == 'bicycle'
    qtbot.keyPress(widget, QtCore.Qt.Key_Down)
    assert widget.list_widget.currentItem().text() == 'car'

    # key press to enter label
    qtbot.keyPress(widget, QtCore.Qt.Key_P)
    qtbot.keyPress(widget, QtCore.Qt.Key_E)
    qtbot.keyPress(widget, QtCore.Qt.Key_R)
    qtbot.keyPress(widget, QtCore.Qt.Key_S)
    qtbot.keyPress(widget, QtCore.Qt.Key_O)
    qtbot.keyPress(widget, QtCore.Qt.Key_N)
    assert widget.text() == 'person'
