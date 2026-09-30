from __future__ import annotations

from pathlib import Path

import numpy as np
from pytestqt.qtbot import QtBot

from labelme._app import MainWindow
from labelme._label_file import read_label_file
from labelme._save_request import write_save_request
from labelme._shape import Shape


def test_save_request_owns_mutable_annotation_data(
    *, raw_win: MainWindow, tmp_path: Path, qtbot: QtBot
) -> None:
    win = raw_win
    win._actions.save_auto.setChecked(False)
    shape = Shape(
        label="mask",
        shape_type="mask",
        points=np.array([[0, 0], [2, 2]], dtype=float),
        mask=np.ones((3, 3), dtype=bool),
        flags={"checked": True},
        other_data={"custom": [1]},
    )
    win._commit_shapes([shape])
    assert win._annotation is not None
    win._annotation.other_data["custom"] = [2]
    path = tmp_path / "request.json"
    request = win._capture_save_request(label_path=str(path))
    shape.points[:] = 99
    assert shape.mask is not None and shape.flags is not None
    shape.mask[:] = False
    shape.flags["checked"] = False
    shape.other_data["custom"].append(3)
    win._annotation.other_data["custom"].append(4)
    write_save_request(request)
    restored = read_label_file(filename=str(path))
    assert restored.shapes[0]["points"] == [[0, 0], [2, 2]]
    assert np.all(restored.shapes[0]["mask"])
    assert restored.shapes[0]["flags"] == {"checked": True}
    assert restored.shapes[0]["other_data"] == {"custom": [1]}
    assert restored.other_data["custom"] == [2]
    win.mark_clean()
    qtbot.wait(1)
