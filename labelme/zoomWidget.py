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
    from PyQt5 import QtCore
    from PyQt5 import QtGui
    from PyQt5 import QtWidgets
except ImportError:
    from PyQt4 import QtCore
    from PyQt4 import QtGui
    from PyQt4 import QtGui as QtWidgets


class ZoomWidget(QtWidgets.QSpinBox):

    def __init__(self, value=100):
        super(ZoomWidget, self).__init__()
        self.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.setRange(1, 500)
        self.setSuffix(' %')
        self.setValue(value)
        self.setToolTip('Zoom Level')
        self.setStatusTip(self.toolTip())
        self.setAlignment(QtCore.Qt.AlignCenter)

    def minimumSizeHint(self):
        height = super(ZoomWidget, self).minimumSizeHint().height()
        fm = QtGui.QFontMetrics(self.font())
        width = fm.width(str(self.maximum()))
        return QtCore.QSize(width, height)
