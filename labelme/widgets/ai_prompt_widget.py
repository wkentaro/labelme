from PyQt5 import QtWidgets
from loguru import logger


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
        if (
            (layout := self.layout()) is None
            or (item := layout.itemAt(0)) is None
            or (widget := item.widget()) is None
        ):
            logger.warning("Cannot get text prompt")
            return ""
        return widget.get_text_prompt()

    def get_iou_threshold(self) -> float:
        if (
            (layout := self.layout()) is None
            or (item := layout.itemAt(1)) is None
            or (widget := item.widget()) is None
        ):
            logger.warning("Cannot get IoU threshold")
            return _IouThresholdWidget.default_iou_threshold
        return widget.get_iou_threshold()

    def get_score_threshold(self) -> float:
        if (
            (layout := self.layout()) is None
            or (item := layout.itemAt(1)) is None
            or (widget := item.widget()) is None
        ):
            logger.warning("Cannot get score threshold")
            return _ScoreThresholdWidget.default_score_threshold
        return widget.get_score_threshold()


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
        if (
            (layout := self.layout()) is None
            or (item := layout.itemAt(1)) is None
            or (widget := item.widget()) is None
        ):
            logger.warning("Cannot get text prompt")
            return ""
        return widget.text()


class _NmsParamsWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.setLayout(QtWidgets.QHBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().addWidget(_ScoreThresholdWidget(parent=parent))
        self.layout().addWidget(_IouThresholdWidget(parent=parent))

    def get_score_threshold(self) -> float:
        if (
            (layout := self.layout()) is None
            or (item := layout.itemAt(0)) is None
            or (widget := item.widget()) is None
        ):
            logger.warning("Cannot get score threshold")
            return _ScoreThresholdWidget.default_score_threshold
        return widget.get_value()

    def get_iou_threshold(self) -> float:
        if (
            (layout := self.layout()) is None
            or (item := layout.itemAt(1)) is None
            or (widget := item.widget()) is None
        ):
            logger.warning("Cannot get IoU threshold")
            return _IouThresholdWidget.default_iou_threshold
        return widget.get_value()


class _ScoreThresholdWidget(QtWidgets.QWidget):
    default_score_threshold: float = 0.1

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.setLayout(QtWidgets.QHBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)

        label = QtWidgets.QLabel(self.tr("Score Threshold"))
        self.layout().addWidget(label)

        threshold_widget: QtWidgets.QWidget = QtWidgets.QDoubleSpinBox()
        threshold_widget.setRange(0, 1)
        threshold_widget.setSingleStep(0.05)
        threshold_widget.setValue(self.default_score_threshold)
        self.layout().addWidget(threshold_widget)

    def get_value(self) -> float:
        if (
            (layout := self.layout()) is None
            or (item := layout.itemAt(1)) is None
            or (widget := item.widget()) is None
        ):
            logger.warning("Cannot get score threshold")
            return self.default_score_threshold
        return widget.value()


class _IouThresholdWidget(QtWidgets.QWidget):
    default_iou_threshold: float = 0.5

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.setLayout(QtWidgets.QHBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)

        label = QtWidgets.QLabel(self.tr("IoU Threshold"))
        self.layout().addWidget(label)

        threshold_widget: QtWidgets.QWidget = QtWidgets.QDoubleSpinBox()
        threshold_widget.setRange(0, 1)
        threshold_widget.setSingleStep(0.05)
        threshold_widget.setValue(self.default_iou_threshold)
        self.layout().addWidget(threshold_widget)

    def get_value(self) -> float:
        if (
            (layout := self.layout()) is None
            or (item := layout.itemAt(1)) is None
            or (widget := item.widget()) is None
        ):
            logger.warning("Cannot get IoU threshold")
            return self.default_iou_threshold
        return widget.value()
