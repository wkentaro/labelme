from PyQt5.QtWidgets import QGridLayout, QLabel, QPushButton
from qtpy.QtCore import Qt,Signal
from qtpy import QtWidgets
from functools import partial

class editVariablesDialog(QtWidgets.QDialog):
    
    updateChartLimit = Signal(list)
    
    def __init__(self, parent=None,
                 defaultValues=None,
                 minValue=None,
                 maxValue=None,
                 highValueText="",
                 lowValueText="",
                 WindowTitle="generic Dialog",
                 helpText="generic Help Text",
                 reactive=False,
                 WindowWidth=400,
                 WindowHeight=150
                 ):
        super(editVariablesDialog, self).__init__(parent)

        self.minValue = minValue
        self.maxValue = maxValue
        self.highValueText = highValueText
        self.lowValueText = lowValueText
        self.helpText = helpText
        self.reactive = reactive

        self.setModal(True)
        self.setWindowTitle(WindowTitle)
        self.values = defaultValues
        self.sliders = []
        self.valueLabels = []
        self.smallEndLabel = []
        self.largeEndLabel = []
        for i, _ in enumerate(defaultValues):

            self.sliders.append(self._create_slider(minValue[i],
                                                    maxValue[i],
                                                    defaultValues[i],
                                                    i))
            self.valueLabels.append(QLabel())
            self.valueLabels[-1].setText(
                f"current Value {self.sliders[-1].value()}"
            )
            self.smallEndLabel.append(QLabel())
            self.smallEndLabel[-1].setText(self.lowValueText[i])
            self.largeEndLabel.append(QLabel())
            self.largeEndLabel[-1].setText(self.highValueText[i])
        if self.reactive:
            self.applyButton = QPushButton()
            self.applyButton.setText("apply Change")
            self.applyButton.clicked.connect(self._apply_change)
            
        # self.setWhatsThis(self.helpText)

        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)

        self.setToolTip(self.helpText)

        self.parent = parent

        grid = QGridLayout()
        for i, slider in enumerate(self.sliders):
            grid.addWidget(self.smallEndLabel[i], 2 * i, 0, 1, 1)
            grid.addWidget(slider, 2 * i, 1, 1, 1)
            grid.addWidget(self.largeEndLabel[i], 2 * i, 2, 1, 1)
            grid.addWidget(self.valueLabels[i], 2 * i + 1, 1, 1, 1)
        if self.reactive:
            grid.addWidget(self.applyButton, len(self.sliders) + 2, 1, 1, 1)
        self.setLayout(grid)
        self.setFixedSize(WindowWidth, WindowHeight)
        self.setSizeGripEnabled(False)

    def _create_slider(self, min_value, max_value, default_value, index):
        slider = QtWidgets.QSlider(Qt.Horizontal)
        slider.setRange(min_value, max_value)
        slider.setValue(default_value)
        ValueChangeCallback = partial(self.onNewValue, index)
        slider.valueChanged.connect(ValueChangeCallback)
        return slider

    def onNewValue(self, element_index):
        self.valueLabels[element_index].setText(
            f"current Value {self.sliders[element_index].value()}"
        )
        if self.reactive:
            self._apply_change()

    def _apply_change(self):
        for i, slider in enumerate(self.sliders):
            self.values[i] = slider.value()
        self.updateChartLimit.emit(self.values)
        if not self.reactive:
            self.close()
