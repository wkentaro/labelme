from __future__ import annotations

import functools
import os
import unicodedata
from pathlib import Path

from ._label_file import LABEL_FILE_SUFFIX
from ._label_file import LabelFileReadError
from ._label_file import read_label_file_image_path


def resolve_label_path(
    *, image_path: str, output_dir: Path | None, root_prefix: str | None
) -> str:
    # The Image's Annotation File, or where a new one is written.
    if found := find_label_path(
        image_path=image_path,
        output_dir=output_dir,
        root_prefix=root_prefix,
        cached=False,
    ):
        return found
    candidates = _label_path_candidates(
        image_path=image_path, output_dir=output_dir, root_prefix=root_prefix
    )
    # Never default to another Image's Annotation File. With every candidate
    # taken, the save refuses to overwrite the first one.
    return str(next((c for c in candidates if not c.exists()), candidates[0]))


def find_label_path(
    *,
    image_path: str,
    output_dir: Path | None,
    root_prefix: str | None,
    cached: bool,
) -> str | None:
    for candidate in [
        *_label_path_candidates(
            image_path=image_path, output_dir=output_dir, root_prefix=root_prefix
        ),
        *_legacy_label_path_candidates(
            image_path=image_path, output_dir=output_dir, root_prefix=root_prefix
        ),
    ]:
        if label_file_belongs_to_image(
            label_path=candidate, image_path=image_path, cached=cached
        ):
            return str(candidate)
    return None


def _label_path_candidates(
    *, image_path: str, output_dir: Path | None, root_prefix: str | None
) -> list[Path]:
    image = Path(image_path)
    if output_dir is None:
        parent = image.parent
    else:
        # Mirror the opened folder's subfolders, so Images sharing a name in
        # different subfolders keep separate Annotation Files.
        relative = relative_to_root(path=image_path, root_prefix=root_prefix)
        parent = output_dir if relative is None else output_dir / Path(relative).parent
    return _label_names_in(parent=parent, image=image)


def _legacy_label_path_candidates(
    *, image_path: str, output_dir: Path | None, root_prefix: str | None
) -> list[Path]:
    # Annotation Folders written before mirroring are flat. Their files are
    # still read, but new ones go to the mirrored subfolder.
    relative = relative_to_root(path=image_path, root_prefix=root_prefix)
    if output_dir is None or relative is None or Path(relative).parent == Path():
        return []
    return _label_names_in(parent=output_dir, image=Path(image_path))


def _label_names_in(*, parent: Path, image: Path) -> list[Path]:
    # _refresh_image_list_checkmarks maps both names back to the stem.
    # The stem name is the convention other tools read. Images sharing a stem in
    # one folder (x.jpg, x.png) cannot both have it, so the next one keeps its
    # extension (x.png.json).
    return [
        parent / f"{image.stem}{LABEL_FILE_SUFFIX}",
        parent / f"{image.name}{LABEL_FILE_SUFFIX}",
    ]


def relative_to_root(*, path: str, root_prefix: str | None) -> str | None:
    if root_prefix is None:
        return None
    try:
        # A prefix check would miss "./a.jpg" under the opened folder ".",
        # which the scan lists as "a.jpg".
        relative = os.path.relpath(path, root_prefix)
    except ValueError:  # Windows paths on different drives
        return None
    if relative == os.pardir or relative.startswith(os.pardir + os.sep):
        return None
    return relative


def label_file_belongs_to_image(
    *, label_path: Path, image_path: str, cached: bool
) -> bool:
    # An Annotation File records its Image in imagePath; the file name alone
    # cannot tell Images sharing a stem apart.
    try:
        stat = label_path.stat()
    except OSError:
        return False
    stored = (
        _read_stored_image_path_cached(
            label_path=str(label_path), _mtime_ns=stat.st_mtime_ns, _size=stat.st_size
        )
        if cached
        else _read_stored_image_path(label_path=str(label_path))
    )
    if stored is None:
        # Unreadable: claim it, so opening the Image reports the error instead
        # of hiding the file and saving over it.
        return True
    if os.path.exists(stored):
        try:
            return os.path.samefile(stored, image_path)
        except OSError:
            return False
    # The recorded Image is gone, e.g. moved with its folder or embedded from
    # elsewhere. Moved Images keep their names, so a name that matches another
    # Image beside this one is that Image's.
    image = Path(image_path)
    stored_name = Path(stored).name
    return (
        os.path.normcase(stored_name) == os.path.normcase(image.name)
        or not (image.parent / stored_name).exists()
    )


# The Image List checks every Image on each rebuild and search keystroke, so
# its check marks parse each Annotation File once per revision. A rewrite of
# the same size within one timestamp tick keeps a stale check mark, so loading,
# saving and Delete read the file fresh.
# ponytail: the first parse reads the whole file, ~0.6 ms with embedded image
# data; stop reading at imagePath if first builds of such folders are slow.
@functools.lru_cache(maxsize=65536)
def _read_stored_image_path_cached(
    *, label_path: str, _mtime_ns: int, _size: int
) -> str | None:
    return _read_stored_image_path(label_path=label_path)


def _read_stored_image_path(*, label_path: str) -> str | None:
    try:
        image_path = read_label_file_image_path(filename=label_path)
    except LabelFileReadError:
        return None
    return str(Path(label_path).parent / image_path)


def resolve_stored_image_path(*, image_path: str, label_dir: Path) -> str:
    try:
        image = Path(image_path)
        relative_path = os.path.relpath(image_path, label_dir)
        if os.path.realpath(label_dir / relative_path) != os.path.realpath(image):
            # Parent traversal follows directory symlinks, unlike lexical path math.
            # Keep valid project links and the source filename when correcting it.
            relative_path = os.path.relpath(
                os.path.join(os.path.realpath(image.parent), image.name),
                os.path.realpath(label_dir),
            )
        return relative_path
    except ValueError:
        # Windows drives and UNC shares have no relative path between them; an
        # absolute path costs portability but beats failing the save.
        return os.path.abspath(image_path)


def comparable_stem(*, path: str) -> str:
    # Over-matching only re-checks extra items, so fold the case and Unicode
    # forms a filesystem may treat as the same name.
    return unicodedata.normalize("NFC", Path(path).stem).casefold()


def has_label_file(
    *, image_path: str, output_dir: Path | None, root_prefix: str | None
) -> bool:
    return (
        find_label_path(
            image_path=image_path,
            output_dir=output_dir,
            root_prefix=root_prefix,
            cached=True,
        )
        is not None
    )
