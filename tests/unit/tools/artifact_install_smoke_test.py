from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

import labelme
from labelme import _locale
from tools.artifact_install_smoke import _check_packaged_resources


def test_check_application_starts() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from tools.artifact_install_smoke import _check_application_starts; "
            "_check_application_starts()",
        ],
        capture_output=True,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_check_packaged_resources_rejects_corrupt_phosphor_icon(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    icon_path = tmp_path / "icons" / "phosphor" / "info.svg"
    icon_path.parent.mkdir(parents=True)
    icon_path.write_bytes(b"not an SVG")
    monkeypatch.setattr(labelme, "__file__", str(tmp_path / "__init__.py"))

    with pytest.raises(RuntimeError, match="packaged icon failed to load"):
        _check_packaged_resources()


def test_check_packaged_resources_rejects_corrupt_translation(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A truncated .qm is the failure mode QTranslator.load() swallows silently,
    # so it is the one case a stat-based check would wrongly pass. A real build
    # cannot produce this input, which is why it is asserted here.
    (tmp_path / "xx_XX.qm").write_bytes(b"not a real qm file")
    monkeypatch.setattr(_locale, "TRANSLATE_DIR", tmp_path)

    with pytest.raises(RuntimeError, match="translation failed to load"):
        _check_packaged_resources()
