from __future__ import annotations

from pathlib import Path

import pytest

import labelme
from tools.artifact_install_smoke import _check_packaged_resources
from tools.artifact_install_smoke import _check_source_isolation


def test_check_source_isolation_rejects_sys_path_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_root = tmp_path / "checkout"
    source_root.mkdir()
    monkeypatch.setattr("sys.path", [str(source_root)])

    with pytest.raises(RuntimeError, match="sys.path"):
        _check_source_isolation(
            source_root=source_root,
            package_path=tmp_path / "site-packages" / "labelme" / "__init__.py",
        )


def test_check_source_isolation_rejects_package_under_source_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_root = tmp_path / "checkout"
    source_root.mkdir()
    monkeypatch.setattr("sys.path", [])

    with pytest.raises(RuntimeError, match="imported from source checkout"):
        _check_source_isolation(
            source_root=source_root,
            package_path=source_root / "labelme" / "__init__.py",
        )


def test_check_source_isolation_passes_for_installed_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_root = tmp_path / "checkout"
    source_root.mkdir()
    monkeypatch.setattr("sys.path", [])

    # Neither guard trips: sys.path is clean and the package lives outside
    # source_root, which is what a genuinely isolated install looks like.
    _check_source_isolation(
        source_root=source_root,
        package_path=tmp_path / "site-packages" / "labelme" / "__init__.py",
    )


def test_check_packaged_resources_rejects_missing_file(tmp_path: Path) -> None:
    package_path = tmp_path / "labelme" / "__init__.py"
    package_path.parent.mkdir()
    package_path.touch()
    (package_path.parent / "_config").mkdir()
    (package_path.parent / "_config" / "default_config.yaml").touch()
    # icons/icon-256.png is intentionally left out.

    with pytest.raises(RuntimeError, match="packaged resources are missing"):
        _check_packaged_resources(package_path=package_path)


def test_check_packaged_resources_passes_for_real_package() -> None:
    # Runs the real check, including the QTranslator.load() call, against
    # this checkout's own labelme package rather than a built artifact —
    # QTranslator.load() fails silently, so this is worth asserting on
    # directly rather than trusting the file-existence check alone.
    _check_packaged_resources(package_path=Path(labelme.__file__).resolve())


def _fake_package(package_dir: Path) -> Path:
    (package_dir / "_config").mkdir(parents=True)
    (package_dir / "_config" / "default_config.yaml").touch()
    (package_dir / "icons").mkdir()
    (package_dir / "icons" / "icon-256.png").touch()
    return package_dir / "__init__.py"


def test_check_packaged_resources_rejects_no_translation_catalogs(
    tmp_path: Path,
) -> None:
    package_dir = tmp_path / "labelme"
    package_path = _fake_package(package_dir)
    (package_dir / "translate").mkdir()  # empty: ships no .qm files

    with pytest.raises(RuntimeError, match="ships no translation catalogs"):
        _check_packaged_resources(package_path=package_path)


def test_check_packaged_resources_rejects_corrupt_translation(
    tmp_path: Path,
) -> None:
    package_dir = tmp_path / "labelme"
    package_path = _fake_package(package_dir)
    translate_dir = package_dir / "translate"
    translate_dir.mkdir()
    # A truncated .qm is exactly the failure mode QTranslator.load() swallows
    # silently: the file exists but isn't a loadable translation catalog.
    (translate_dir / "xx_XX.qm").write_bytes(b"not a real qm file")

    with pytest.raises(RuntimeError, match="translation failed to load"):
        _check_packaged_resources(package_path=package_path)
