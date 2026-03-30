from PyQt5.QtCore import Qt


def test_zoom_widget_range(qtbot):
    """ZoomWidget clamps value to [1, 1000]."""
    from labelme.widgets.zoom_widget import ZoomWidget

    w = ZoomWidget()
    qtbot.addWidget(w)
    assert w.minimum() == 1
    assert w.maximum() == 1000


def test_zoom_widget_suffix(qtbot):
    """ZoomWidget shows ' %' suffix."""
    from labelme.widgets.zoom_widget import ZoomWidget

    w = ZoomWidget(value=150)
    qtbot.addWidget(w)
    assert w.suffix() == " %"
    assert w.value() == 150


def test_zoom_widget_alignment(qtbot):
    """ZoomWidget text is center-aligned."""
    from labelme.widgets.zoom_widget import ZoomWidget

    w = ZoomWidget()
    qtbot.addWidget(w)
    assert w.alignment() == Qt.AlignCenter
