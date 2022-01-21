from PyQt5.QtWidgets import QGridLayout, QLabel, QPushButton
from qtpy.QtCore import Qt
from qtpy import QtWidgets


class editSingleVariableDialog(QtWidgets.QDialog):
    def __init__(self, parent=None,
                 defaultValue=None,
                 minValue=None,
                 maxValue=None,
                 highValueText="",
                 lowValueText="",
                 WindowTitle="generic Dialog",
                 helpText="generic Help Text",
                 WindowWidth=400,
                 WindowHeight=150
                 ):
        super(editSingleVariableDialog, self).__init__(parent)

        self.minValue = minValue
        self.maxValue = maxValue
        self.highValueText = highValueText
        self.lowValueText = lowValueText
        self.helpText = helpText

        self.setModal(True)
        self.setWindowTitle(WindowTitle)
        self.value = defaultValue
        self.slider_snapping = self._create_slider()
        self.valueLabel = QLabel()
        self.valueLabel.setText(
            f"current Value {self.slider_snapping.value()}"
        )
        self.applyButton = QPushButton()
        self.applyButton.setText("apply Change")
        self.applyButton.clicked.connect(self._apply_change)
        smallEndLabel = QLabel()
        smallEndLabel.setText(self.lowValueText)
        largeEndLabel = QLabel()
        largeEndLabel.setText(self.highValueText)
        #self.setWhatsThis(self.helpText)

        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)

        self.setToolTip(self.helpText)

        self.parent = parent

        grid = QGridLayout()
        grid.addWidget(smallEndLabel, 1, 0, 1, 1)
        grid.addWidget(self.slider_snapping, 1, 1, 1, 1)
        grid.addWidget(largeEndLabel, 1, 2, 1, 1)
        grid.addWidget(self.valueLabel, 2, 1, 1, 1)
        grid.addWidget(self.applyButton, 3, 1, 1, 1)
        self.setLayout(grid)
        self.setFixedSize(WindowWidth, WindowHeight)
        self.setSizeGripEnabled(False)

    def _create_slider(self):
        slider = QtWidgets.QSlider(Qt.Horizontal)
        slider.setRange(self.minValue, self.maxValue)
        slider.setValue(self.value)
        slider.valueChanged.connect(self.onNewValue)
        return slider

    def onNewValue(self):
        self.valueLabel.setText(
            f"current Value {self.slider_snapping.value()}"
        )

    def _apply_change(self):
        self.value = self.slider_snapping.value()
        self.close()
