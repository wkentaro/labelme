from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from labelme._label_path import find_label_path
from labelme._label_path import has_label_file
from labelme._label_path import resolve_label_path
from labelme._label_path import resolve_stored_image_path


@pytest.mark.parametrize(
    "image_path, output_dir, expected",
    [
        (str(Path("/data/img.png")), None, str(Path("/data/img.json"))),
        (str(Path("/data/img.png")), Path("/out"), str(Path("/out/img.json"))),
        (str(Path("/data/a.b.png")), None, str(Path("/data/a.b.json"))),
    ],
    ids=["image-sibling-json", "image-honors-output-dir", "multi-dot-stem"],
)
def test_resolve_label_path(
    *,
    image_path: str,
    output_dir: Path | None,
    expected: str,
) -> None:
    assert (
        resolve_label_path(
            image_path=image_path, output_dir=output_dir, root_prefix=None
        )
        == expected
    )


def test_resolve_label_path_follows_the_recorded_image(*, tmp_path: Path) -> None:
    for name in ("x.jpg", "x.png", "y.jpg"):
        (tmp_path / name).touch()

    def resolve(name: str) -> str:
        return resolve_label_path(
            image_path=str(tmp_path / name), output_dir=None, root_prefix=None
        )

    def record(label_name: str, image_path: str) -> None:
        (tmp_path / label_name).write_text(json.dumps({"imagePath": image_path}))

    # x.jpg and x.png share the stem name; whichever saves second keeps its
    # extension.
    record("x.json", "x.jpg")
    assert resolve("x.jpg") == str(tmp_path / "x.json")
    assert resolve("x.png") == str(tmp_path / "x.png.json")
    record("x.png.json", "x.png")
    assert resolve("x.png") == str(tmp_path / "x.png.json")

    # A recorded Image that is gone still belongs here, unless its name is
    # another Image beside this one.
    record("x.json", "../moved/x.jpg")
    assert has_label_file(
        image_path=str(tmp_path / "x.jpg"), output_dir=None, root_prefix=None
    )
    record("y.json", "embedded-elsewhere.jpg")
    assert has_label_file(
        image_path=str(tmp_path / "y.jpg"), output_dir=None, root_prefix=None
    )
    (tmp_path / "x.png.json").unlink()
    assert resolve("x.png") == str(tmp_path / "x.png.json")

    # An unreadable file stays claimed, so opening reports it.
    (tmp_path / "y.json").write_text("{")
    assert resolve("y.jpg") == str(tmp_path / "y.json")


def test_find_label_path_reads_a_rewrite_within_one_timestamp(
    *, tmp_path: Path
) -> None:
    for name in ("x.jpg", "x.png"):
        (tmp_path / name).touch()
    label = tmp_path / "x.png.json"
    label.write_text(json.dumps({"imagePath": "x.png"}))
    image = str(tmp_path / "x.png")
    assert has_label_file(image_path=image, output_dir=None, root_prefix=None)

    # Same size and mtime, as a fast rewrite on a coarse clock leaves them.
    stat = label.stat()
    label.write_text(json.dumps({"imagePath": "x.jpg"}))
    os.utime(label, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    assert (
        find_label_path(
            image_path=image, output_dir=None, root_prefix=None, cached=False
        )
        is None
    )


def test_resolve_label_path_mirrors_subfolders(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    images = tmp_path / "images"
    out = tmp_path / "out"
    for name in ("0001.jpg", "a/0001.jpg", "b/0001.jpg"):
        (images / name).parent.mkdir(parents=True, exist_ok=True)
        (images / name).touch()
    root_prefix = os.path.join(str(images), "")

    def resolve(image_path: Path) -> str:
        return resolve_label_path(
            image_path=str(image_path), output_dir=out, root_prefix=root_prefix
        )

    assert resolve(images / "a" / "0001.jpg") == str(out / "a" / "0001.json")
    assert resolve(images / "0001.jpg") == str(out / "0001.json")
    # Images outside the opened folder have no subfolder to mirror.
    assert resolve(tmp_path / "x.jpg") == str(out / "x.json")
    assert resolve(tmp_path / "..x" / "x.jpg") == str(out / "x.json")

    # A flat Annotation File from before mirroring stays with its own Image,
    # even when the root Image's name is the same.
    out.mkdir()
    (out / "0001.json").write_text(json.dumps({"imagePath": "../images/b/0001.jpg"}))
    assert resolve(images / "b" / "0001.jpg") == str(out / "0001.json")
    assert resolve(images / "a" / "0001.jpg") == str(out / "a" / "0001.json")
    assert resolve(images / "0001.jpg") == str(out / "0001.jpg.json")

    # A folder opened as "." lists its Images without the "./" prefix.
    monkeypatch.chdir(images)
    assert resolve_label_path(
        image_path=os.path.join("a", "0001.jpg"),
        output_dir=out,
        root_prefix=os.path.join(".", ""),
    ) == str(out / "a" / "0001.json")


def test_resolve_stored_image_path_falls_back_to_absolute(
    *,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise(*_args: object, **_kwargs: object) -> str:
        raise ValueError("path is on mount 'D:', start on mount 'C:'")

    monkeypatch.setattr("os.path.relpath", _raise)

    assert resolve_stored_image_path(
        image_path="img.png", label_dir=Path("/labels")
    ) == os.path.abspath("img.png")


@pytest.mark.skipif(os.name != "nt", reason="only Windows has cross-drive paths")
def test_resolve_stored_image_path_falls_back_across_real_windows_drives() -> None:
    assert (
        resolve_stored_image_path(
            image_path=r"D:\imgs\img.png", label_dir=Path(r"C:\labels")
        )
        == r"D:\imgs\img.png"
    )


@pytest.mark.skipif(os.name != "nt", reason="only Windows has UNC paths")
@pytest.mark.parametrize(
    ("image_path", "label_dir"),
    [
        (r"\\server\share\imgs\img.png", Path(r"C:\labels")),
        (r"C:\imgs\img.png", Path(r"\\server\share\labels")),
        (r"\\server\share1\imgs\img.png", Path(r"\\server\share2\labels")),
        (r"\\server1\share\imgs\img.png", Path(r"\\server2\share\labels")),
    ],
    ids=[
        "unc-image-drive-label-dir",
        "drive-image-unc-label-dir",
        "unc-share-mismatch",
        "unc-server-mismatch",
    ],
)
def test_resolve_stored_image_path_falls_back_across_windows_unc_shares(
    *,
    image_path: str,
    label_dir: Path,
) -> None:
    assert (
        resolve_stored_image_path(image_path=image_path, label_dir=label_dir)
        == image_path
    )
