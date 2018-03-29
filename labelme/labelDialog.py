#
# Copyright (C) 2011 Michael Pitidis, Hussein Abdulwahid.
#
# This file is part of Labelme.
#
# Labelme is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Labelme is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Labelme.  If not, see <http://www.gnu.org/licenses/>.
#

try:
    from PyQt5.QtGui import *
    from PyQt5.QtCore import *
    from PyQt5.QtWidgets import *
    PYQT5 = True
except ImportError:
    from PyQt4.QtGui import *
    from PyQt4.QtCore import *
    PYQT5 = False

from .lib import newIcon, labelValidator

# TODO:
# - Calculate optimal position so as not to go out of screen area.

BB = QDialogButtonBox

class LabelDialog(QDialog):

    def __init__(self, text="Enter object label", parent=None, labels=None,
                 sort_labels=True):
        super(LabelDialog, self).__init__(parent)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(text)
        self.edit.setValidator(labelValidator())
        self.edit.editingFinished.connect(self.postProcess)
        layout = QVBoxLayout()
        layout.addWidget(self.edit)
        # buttons
        self.buttonBox = bb = BB(BB.Ok | BB.Cancel, Qt.Horizontal, self)
        bb.button(BB.Ok).setIcon(newIcon('done'))
        bb.button(BB.Cancel).setIcon(newIcon('undo'))
        bb.accepted.connect(self.validate)
        bb.rejected.connect(self.reject)
        layout.addWidget(bb)
        # label_list
        self.labelList = QListWidget()
        self._sort_labels = sort_labels
        if labels:
            self.labelList.addItems(labels)
        if self._sort_labels:
            self.labelList.sortItems()
        else:
            self.labelList.setDragDropMode(QAbstractItemView.InternalMove)
        self.labelList.currentItemChanged.connect(self.labelSelected)
        layout.addWidget(self.labelList)
        self.setLayout(layout)

    def addLabelHistory(self, label):
        if self.labelList.findItems(label, Qt.MatchExactly):
            return
        self.labelList.addItem(label)
        if self._sort_labels:
            self.labelList.sortItems()

    def labelSelected(self, item):
        self.edit.setText(item.text())

    def validate(self):
        if PYQT5:
            if self.edit.text().strip():
                self.accept()
        else:
            if self.edit.text().trimmed():
                self.accept()

    def postProcess(self):
        if PYQT5:
            self.edit.setText(self.edit.text().strip())
        else:
            self.edit.setText(self.edit.text().trimmed())

    def popUp(self, text=None, move=True):
        if isinstance(text, str):
            self.edit.setText(text)
            self.edit.setSelection(0, len(text))
            i = self.labelList.findItems(text, Qt.MatchFixedString)
            if len(i) == 1:
                self.labelList.setCurrentItem(i[0])
        self.edit.setFocus(Qt.PopupFocusReason)
        if move:
            self.move(QCursor.pos())
        return self.edit.text() if self.exec_() else None

    def keyPressEvent(self, e):
        if e.key() in [Qt.Key_Up, Qt.Key_Down]:
            self.labelList.keyPressEvent(e)
        else:
            super().keyPressEvent(e)
