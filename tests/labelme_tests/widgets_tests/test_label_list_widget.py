import pytest

from labelme.widgets.label_list_widget import LabelListWidget
from labelme.widgets.label_list_widget import LabelListWidgetItem


@pytest.mark.gui
def test_LabelListWidget(qtbot):
    widget = LabelListWidget()

    item = LabelListWidgetItem(text="person <font color='red'>●</fon>")
    widget.addItem(item)
    item = LabelListWidgetItem(text="dog <font color='blue'>●</fon>")
    widget.addItem(item)

    widget.show()
    qtbot.addWidget(widget)
    qtbot.waitExposed(widget)
