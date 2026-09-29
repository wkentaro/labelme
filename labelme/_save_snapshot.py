from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ._label_file import Annotation
from ._label_file import write_label_file


@dataclass(frozen=True)
class SaveSnapshot:
    filename: str
    annotation: Annotation
    image_height: int
    image_width: int
    save_image_data: bool

    def write(self) -> None:
        Path(self.filename).parent.mkdir(parents=True, exist_ok=True)
        write_label_file(
            filename=self.filename,
            annotation=self.annotation,
            image_height=self.image_height,
            image_width=self.image_width,
            save_image_data=self.save_image_data,
        )
