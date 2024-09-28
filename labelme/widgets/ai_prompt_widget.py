from qtpy import QtWidgets


class AiPromptWidget(QtWidgets.QWidget):
    def __init__(self, on_submit, parent=None):
        super().__init__(parent=parent)

        self.setLayout(QtWidgets.QVBoxLayout())
        self.layout().setSpacing(0)

        text_prompt_widget = _TextPromptWidget(on_submit=on_submit, parent=self)
        text_prompt_widget.setMaximumWidth(400)
        self.layout().addWidget(text_prompt_widget)

        nms_params_widget = _NmsParamsWidget(parent=self)
        nms_params_widget.setMaximumWidth(400)
        self.layout().addWidget(nms_params_widget)

    def get_text_prompt(self) -> str:
        text_prompt_widget: QtWidgets.QWidget = self.layout().itemAt(0).widget()
        return text_prompt_widget.get_text_prompt()

    def get_iou_threshold(self) -> float:
        nms_params_widget = self.layout().itemAt(1).widget()
        return nms_params_widget.get_iou_threshold()

    def get_score_threshold(self) -> float:
        nms_params_widget = self.layout().itemAt(1).widget()
        return nms_params_widget.get_score_threshold()


class _TextPromptWidget(QtWidgets.QWidget):
    def __init__(self, on_submit, parent=None):
        super().__init__(parent=parent)

        self.setLayout(QtWidgets.QHBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)

        label = QtWidgets.QLabel(self.tr("AI Prompt"))
        self.layout().addWidget(label)

        texts_widget = QtWidgets.QLineEdit()
        texts_widget.setPlaceholderText(self.tr("e.g., dog,cat,bird"))
        self.layout().addWidget(texts_widget)

        submit_button = QtWidgets.QPushButton(text="Submit", parent=self)
        submit_button.clicked.connect(slot=on_submit)
        self.layout().addWidget(submit_button)

    def get_text_prompt(self) -> str:
        texts_widget: QtWidgets.QWidget = self.layout().itemAt(1).widget()
        return texts_widget.text()


class _NmsParamsWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.setLayout(QtWidgets.QHBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().addWidget(_ScoreThresholdWidget(parent=parent))
        self.layout().addWidget(_IouThresholdWidget(parent=parent))

    def get_score_threshold(self) -> float:
        score_threshold_widget: QtWidgets.QWidget = self.layout().itemAt(0).widget()
        return score_threshold_widget.get_value()

    def get_iou_threshold(self) -> float:
        iou_threshold_widget: QtWidgets.QWidget = self.layout().itemAt(1).widget()
        return iou_threshold_widget.get_value()


class _ScoreThresholdWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.setLayout(QtWidgets.QHBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)

        label = QtWidgets.QLabel(self.tr("Score Threshold"))
        self.layout().addWidget(label)

        threshold_widget: QtWidgets.QWidget = QtWidgets.QDoubleSpinBox()
        threshold_widget.setRange(0, 1)
        threshold_widget.setSingleStep(0.05)
        threshold_widget.setValue(0.1)
        self.layout().addWidget(threshold_widget)

    def get_value(self) -> float:
        threshold_widget: QtWidgets.QWidget = self.layout().itemAt(1).widget()
        return threshold_widget.value()


class _IouThresholdWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.setLayout(QtWidgets.QHBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)

        label = QtWidgets.QLabel(self.tr("IoU Threshold"))
        self.layout().addWidget(label)

        threshold_widget: QtWidgets.QWidget = QtWidgets.QDoubleSpinBox()
        threshold_widget.setRange(0, 1)
        threshold_widget.setSingleStep(0.05)
        threshold_widget.setValue(0.5)
        self.layout().addWidget(threshold_widget)

    def get_value(self) -> float:
        threshold_widget: QtWidgets.QWidget = self.layout().itemAt(1).widget()
        return threshold_widget.value()
