from typing import Literal
from typing import TypeAlias

AiPromptKind: TypeAlias = Literal["points", "box"]

AiOutputFormat: TypeAlias = Literal[
    "rectangle", "polygon", "mask", "circle", "oriented_rectangle"
]
