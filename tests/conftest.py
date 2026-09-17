from __future__ import annotations

import importlib
import json
import os
import shutil
import threading
from collections.abc import Callable
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from pathlib import Path

import imgviz
import pytest
from PySide6 import QtWidgets
from PySide6.QtGui import QColor
from PySide6.QtGui import QImageReader
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QColorDialog
from PySide6.QtWidgets import QWidget
from pytestqt.qtbot import QtBot

import labelme._utils


def pytest_addoption(parser: pytest.Parser) -> None:  # noqa: GR005 -- pluggy calls hooks positionally
    parser.addoption(
        "--pause",
        action="store_true",
        default=False,
        help="Pause after each GUI test until the window is closed manually.",
    )
    parser.addoption(
        "--headed",
        action="store_true",
        default=False,
        help="Run GUI tests with a visible window (skip QT_QPA_PLATFORM=offscreen).",
    )
    parser.addoption(
        "--update-snapshots",
        action="store_true",
        default=False,
        help=(
            "Regenerate snapshot files under tests/data/snapshots/ instead of "
            "comparing against them. Run once to seed or update snapshots, then "
            "commit the resulting files and re-run without this flag to verify."
        ),
    )


def pytest_configure(config: pytest.Config) -> None:  # noqa: GR005 -- pluggy calls hooks positionally
    if not config.getoption("--headed"):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"


@pytest.fixture()
def pause(*, request: pytest.FixtureRequest) -> bool:
    return request.config.getoption("--pause", default=False)


@pytest.fixture()
def use_widget_color_dialog(*, monkeypatch: pytest.MonkeyPatch) -> None:
    class WidgetColorDialog(QColorDialog):
        def __init__(self, *, parent: QWidget, currentColor: QColor) -> None:
            super().__init__(parent=parent, currentColor=currentColor)
            self.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog)

    monkeypatch.setattr(QtWidgets, "QColorDialog", WidgetColorDialog)


@pytest.fixture()
def update_snapshots(*, request: pytest.FixtureRequest) -> bool:
    return request.config.getoption("--update-snapshots")


@pytest.fixture()
def snapshot_dir() -> Path:
    # ``--update-snapshots`` must write back to the real repo tree, not a tmp copy.
    return Path(__file__).parent / "data" / "snapshots"


@pytest.fixture()
def set_allocation_limit(
    *,
    qapp: QApplication,  # noqa: ARG001 -- a fixture cannot use usefixtures
) -> Iterator[Callable[[int], None]]:
    original_limit = QImageReader.allocationLimit()
    yield QImageReader.setAllocationLimit
    QImageReader.setAllocationLimit(original_limit)


def assert_labelfile_sanity(filename: str, /) -> None:
    label_path = Path(filename)
    assert label_path.exists()

    with open(label_path) as f:
        data = json.load(f)

    assert "imagePath" in data
    image_data = data.get("imageData", None)
    if image_data is None:
        img_file = label_path.parent / data["imagePath"]
        assert img_file.exists()
        img = imgviz.io.imread(img_file)
    else:
        img = labelme._utils.img_b64_to_arr(image_data)

    height, width = img.shape[:2]
    assert height == data["imageHeight"]
    assert width == data["imageWidth"]

    assert "shapes" in data
    for shape in data["shapes"]:
        assert "label" in shape
        assert "points" in shape
        for x, y in shape["points"]:
            assert 0 <= x <= width
            assert 0 <= y <= height


def close_or_pause(
    *, qtbot: QtBot, widget: QWidget, pause: bool, timeout: int = 60_000
) -> None:
    if pause:
        qtbot.waitUntil(lambda: not widget.isVisible(), timeout=timeout)
    else:
        widget.close()


def _create_annotated_nested(*, data_path: Path) -> None:
    dst_dir: Path = data_path / "annotated_nested"
    dst_dir.mkdir()

    (dst_dir / "images").mkdir()
    for image_file in (data_path / "annotated").glob("*.jpg"):
        shutil.copy(image_file, dst_dir / "images" / image_file.name)

    (dst_dir / "annotations").mkdir()
    for json_file in (data_path / "annotated").glob("*.json"):
        dst_json_file = dst_dir / "annotations" / json_file.name
        shutil.copy(json_file, dst_json_file)
        with open(dst_json_file) as f:
            json_data = json.load(f)
        json_data["imagePath"] = str(Path("..") / "images" / json_data["imagePath"])
        with open(dst_json_file, "w") as f:
            json.dump(json_data, f, indent=2)


@pytest.fixture(scope="function")
def data_path(*, tmp_path: Path) -> Path:
    data_path: Path = tmp_path / "data"
    shutil.copytree(Path(__file__).parent / "data", data_path)

    _create_annotated_nested(data_path=data_path)

    return data_path


@pytest.fixture
def download_server(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[str, list[str], threading.Event]]:
    # gdown resolves its staging directory at import time, before HOME is
    # redirected, so failed transfers would otherwise litter the real cache.
    monkeypatch.setattr(
        importlib.import_module("gdown.cached_download"),
        "cache_root",
        str(tmp_path / "gdown"),
    )
    requests: list[str] = []
    release = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            requests.append(self.path)
            content = {"/bad": b"corrupt", "/large": b"x" * 2**20}.get(
                self.path, b"weights"
            )
            self.send_response(200)
            self.send_header(
                "Content-Length", str(2**33 if self.path == "/large" else len(content))
            )
            self.end_headers()
            if self.path == "/slow":
                release.wait(timeout=5)
            try:
                self.wfile.write(content)
                self.wfile.flush()
                if self.path == "/large":
                    release.wait(timeout=5)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, format: str, *args: object) -> None:  # noqa: ARG002 -- silence local HTTP logs
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", requests, release
    release.set()
    server.shutdown()
    server.server_close()
    thread.join()
