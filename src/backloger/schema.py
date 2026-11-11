"""Export JSON Schema from the same models used by every adapter."""

from pathlib import Path
from typing import Any

from pydantic import BaseModel

from backloger.errors import BacklogError
from backloger.filesystem import encode
from backloger.models import Backlog, Project, WorkItem


def reject_unknown(value: Any, path: str = "backlog") -> None:
    if isinstance(value, BaseModel):
        if value.model_extra:
            raise BacklogError(
                f"{path}: campos desconhecidos: {', '.join(value.model_extra)}; use extensions"
            )
        for name in type(value).model_fields:
            if name != "extensions":
                reject_unknown(getattr(value, name), f"{path}.{name}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            reject_unknown(item, f"{path}[{index}]")


def generate(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name, model in (("work-item", WorkItem), ("project", Project), ("backlog", Backlog)):
        schema = model.model_json_schema()
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["$id"] = f"https://softctrl.com/backloger/schemas/1.0.0/{name}.schema.json"
        (directory / f"{name}.schema.json").write_bytes(encode(schema))


if __name__ == "__main__":
    generate(Path("schemas/1.0.0"))
