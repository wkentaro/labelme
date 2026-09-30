from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ._label_file import Annotation
from ._label_file import write_label_file


@dataclass(frozen=True)
class SaveRequest:
    filename: str
    annotation: Annotation
    image_height: int
    image_width: int
    save_image_data: bool


def write_save_request(request: SaveRequest, /) -> None:
    Path(request.filename).parent.mkdir(parents=True, exist_ok=True)
    write_label_file(
        filename=request.filename,
        annotation=request.annotation,
        image_height=request.image_height,
        image_width=request.image_width,
        save_image_data=request.save_image_data,
    )
