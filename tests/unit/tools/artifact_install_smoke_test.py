from __future__ import annotations

from pathlib import Path

import pytest

from labelme import _locale
from tools.artifact_install_smoke import _check_packaged_resources


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
