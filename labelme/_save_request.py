from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ._label_file import Annotation
from ._label_file import LabelFileError
from ._label_file import write_label_file
from ._label_path import label_file_belongs_to_image


class ForeignAnnotationFileError(LabelFileError):
    filename: str

    def __init__(self, *, filename: str) -> None:
        super().__init__(f"The Annotation File belongs to another Image: {filename}")
        self.filename = filename


@dataclass(frozen=True)
class SaveRequest:
    filename: str
    annotation: Annotation
    image_height: int
    image_width: int
    save_image_data: bool
    # The Image an existing file at filename must be recorded for, or None when
    # the user confirmed the overwrite. Checked where the write runs, so Auto
    # Save parses the existing file off the GUI thread.
    owner_image_path: str | None


def write_save_request(*, request: SaveRequest) -> None:
    if (
        request.owner_image_path is not None
        and Path(request.filename).exists()
        and not label_file_belongs_to_image(
            label_path=Path(request.filename),
            image_path=request.owner_image_path,
            cached=False,
        )
    ):
        raise ForeignAnnotationFileError(filename=request.filename)
    Path(request.filename).parent.mkdir(parents=True, exist_ok=True)
    write_label_file(
        filename=request.filename,
        annotation=request.annotation,
        image_height=request.image_height,
        image_width=request.image_width,
        save_image_data=request.save_image_data,
    )
