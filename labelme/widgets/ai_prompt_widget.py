from PyQt5 import QtWidgets


class AiPromptWidget(QtWidgets.QWidget):
    def __init__(self, on_submit, parent=None):
        super().__init__(parent=parent)

        self.setLayout(QtWidgets.QVBoxLayout())
        self.layout().setSpacing(0)

        self._text_prompt_widget = _TextPromptWidget(on_submit=on_submit, parent=self)
        self._text_prompt_widget.setMaximumWidth(300)
        self.layout().addWidget(self._text_prompt_widget)

        self._nms_params_widget = _NmsParamsWidget(parent=self)
        self._nms_params_widget.setMaximumWidth(300)
        self.layout().addWidget(self._nms_params_widget)

    def get_text_prompt(self) -> str:
        return self._text_prompt_widget.get_text_prompt()

    def get_iou_threshold(self) -> float:
        return self._nms_params_widget.get_iou_threshold()

    def get_score_threshold(self) -> float:
        return self._nms_params_widget.get_score_threshold()


class _TextPromptWidget(QtWidgets.QWidget):
    def __init__(self, on_submit, parent=None):
        super().__init__(parent=parent)

        self.setLayout(QtWidgets.QHBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)

        label = QtWidgets.QLabel(self.tr("AI Prompt"))
        self.layout().addWidget(label)

        self._texts_widget = QtWidgets.QLineEdit()
        self._texts_widget.setPlaceholderText(self.tr("e.g., dog,cat,bird"))
        self.layout().addWidget(self._texts_widget)

        submit_button = QtWidgets.QPushButton(text="Run", parent=self)
        submit_button.clicked.connect(slot=on_submit)
        self.layout().addWidget(submit_button)

    def get_text_prompt(self) -> str:
        return self._texts_widget.text()


class _NmsParamsWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.setLayout(QtWidgets.QHBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)

        self._score_threshold_widget: _ScoreThresholdWidget = _ScoreThresholdWidget(
            parent=parent
        )
        self.layout().addWidget(self._score_threshold_widget)

        self._iou_threshold_widget: _IouThresholdWidget = _IouThresholdWidget(
            parent=parent
        )
        self.layout().addWidget(self._iou_threshold_widget)

    def get_score_threshold(self) -> float:
        return self._score_threshold_widget.get_value()

    def get_iou_threshold(self) -> float:
        return self._iou_threshold_widget.get_value()


class _ScoreThresholdWidget(QtWidgets.QWidget):
    default_score_threshold: float = 0.1

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.setLayout(QtWidgets.QHBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)

        label = QtWidgets.QLabel(self.tr("Score Threshold"))
        self.layout().addWidget(label)

        self._threshold_widget: QtWidgets.QDoubleSpinBox = QtWidgets.QDoubleSpinBox()
        self._threshold_widget.setRange(0, 1)
        self._threshold_widget.setSingleStep(0.05)
        self._threshold_widget.setValue(self.default_score_threshold)
        self._threshold_widget.setMinimumWidth(50)
        self.layout().addWidget(self._threshold_widget)

    def get_value(self) -> float:
        return self._threshold_widget.value()


class _IouThresholdWidget(QtWidgets.QWidget):
    default_iou_threshold: float = 0.5

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.setLayout(QtWidgets.QHBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)

        label = QtWidgets.QLabel(self.tr("IoU Threshold"))
        self.layout().addWidget(label)

        self._threshold_widget: QtWidgets.QDoubleSpinBox = QtWidgets.QDoubleSpinBox()
        self._threshold_widget.setRange(0, 1)
        self._threshold_widget.setSingleStep(0.05)
        self._threshold_widget.setValue(self.default_iou_threshold)
        self._threshold_widget.setMinimumWidth(50)
        self.layout().addWidget(self._threshold_widget)

    def get_value(self) -> float:
        return self._threshold_widget.value()
