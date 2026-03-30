from __future__ import annotations

from PyQt5 import QtWidgets

from labelme.widgets.tool_bar import ToolBar


def test_toolbar_is_not_movable(qtbot):
    """ToolBar is always fixed (not draggable)."""
    tb = ToolBar(title="TestBar", actions=[])
    qtbot.addWidget(tb)
    assert not tb.isMovable()
    assert not tb.isFloatable()


def test_toolbar_title_sets_object_name(qtbot):
    """ToolBar sets objectName from title."""
    tb = ToolBar(title="Actions", actions=[])
    qtbot.addWidget(tb)
    assert tb.objectName() == "ActionsToolBar"


def test_toolbar_adds_actions(qtbot):
    """ToolBar adds QAction items as QToolButton widgets."""
    action = QtWidgets.QAction("Test")
    tb = ToolBar(title="TestBar", actions=[action])
    qtbot.addWidget(tb)
    # ToolBar.addAction wraps each QAction in a QToolButton via addWidget()
    buttons = [
        tb.layout().itemAt(i).widget()
        for i in range(tb.layout().count())
        if isinstance(tb.layout().itemAt(i).widget(), QtWidgets.QToolButton)
    ]
    assert len(buttons) == 1
    assert buttons[0].defaultAction() is action
