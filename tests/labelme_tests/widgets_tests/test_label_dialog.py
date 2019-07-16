from qtpy import QtCore
from qtpy import QtWidgets

from labelme.widgets import LabelDialog
from labelme.widgets import LabelQLineEdit


def test_LabelQLineEdit(qtbot):
    list_widget = QtWidgets.QListWidget()
    list_widget.addItems([
        'cat',
        'dog',
        'person',
    ])
    widget = LabelQLineEdit()
    widget.setListWidget(list_widget)
    qtbot.addWidget(widget)

    # key press to navigate in label list
    item = widget.list_widget.findItems('cat', QtCore.Qt.MatchExactly)[0]
    widget.list_widget.setCurrentItem(item)
    assert widget.list_widget.currentItem().text() == 'cat'
    qtbot.keyPress(widget, QtCore.Qt.Key_Down)
    assert widget.list_widget.currentItem().text() == 'dog'

    # key press to enter label
    qtbot.keyPress(widget, QtCore.Qt.Key_P)
    qtbot.keyPress(widget, QtCore.Qt.Key_E)
    qtbot.keyPress(widget, QtCore.Qt.Key_R)
    qtbot.keyPress(widget, QtCore.Qt.Key_S)
    qtbot.keyPress(widget, QtCore.Qt.Key_O)
    qtbot.keyPress(widget, QtCore.Qt.Key_N)
    assert widget.text() == 'person'


def test_LabelDialog_addLabelHistory(qtbot):
    labels = ['cat', 'dog', 'person']
    widget = LabelDialog(labels=labels, sort_labels=True)
    qtbot.addWidget(widget)

    widget.addLabelHistory('bicycle')
    assert widget.labelList.count() == 4
    widget.addLabelHistory('bicycle')
    assert widget.labelList.count() == 4
    item = widget.labelList.item(0)
    assert item.text() == 'bicycle'


def test_LabelDialog_popUp(qtbot):
    labels = ['cat', 'dog', 'person']
    widget = LabelDialog(labels=labels, sort_labels=True)
    qtbot.addWidget(widget)

    # popUp(text='cat')

    def interact():
        qtbot.keyClick(widget.edit, QtCore.Qt.Key_P)  # enter 'p' for 'person'  # NOQA
        qtbot.keyClick(widget.edit, QtCore.Qt.Key_Enter)  # NOQA
        qtbot.keyClick(widget.edit, QtCore.Qt.Key_Enter)  # NOQA

    QtCore.QTimer.singleShot(500, interact)
    label, flags = widget.popUp('cat')
    assert label == 'person'
    assert flags == {}

    # popUp()

    def interact():
        qtbot.keyClick(widget.edit, QtCore.Qt.Key_Enter)  # NOQA
        qtbot.keyClick(widget.edit, QtCore.Qt.Key_Enter)  # NOQA

    QtCore.QTimer.singleShot(500, interact)
    label, flags = widget.popUp()
    assert label == 'person'
    assert flags == {}

    # popUp() + key_Up

    def interact():
        qtbot.keyClick(widget.edit, QtCore.Qt.Key_Up)  # 'person' -> 'dog'  # NOQA
        qtbot.keyClick(widget.edit, QtCore.Qt.Key_Enter)  # NOQA
        qtbot.keyClick(widget.edit, QtCore.Qt.Key_Enter)  # NOQA

    QtCore.QTimer.singleShot(500, interact)
    label, flags = widget.popUp()
    assert label == 'dog'
    assert flags == {}
