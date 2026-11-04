"""Writing Generation records: atomically, after every draw."""

from __future__ import annotations

import os
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path

import yaml

from seeker.ontology import Generation

HEADER = (
    "# Generation record (schema/seeker.yaml). Inputs are pinned: the embedded draw\n"
    "# batch, reading, model, role-file digest and git commit. Rerunning with the same\n"
    "# output path resumes, filling in only the positions without an idea.\n"
)


class GenerationSink(ABC):
    """Where a generation in progress is saved after each draw."""

    @abstractmethod
    def save(self, generation: Generation) -> None: ...


class GenerationFile(GenerationSink):
    """A YAML record on disk, rewritten atomically (temp file, then os.replace)."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def exists(self) -> bool:
        return self.path.is_file()

    def read(self) -> Generation:
        return Generation.model_validate(yaml.safe_load(self.path.read_text(encoding="utf-8")))

    def save(self, generation: Generation) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        body = yaml.safe_dump(generation.model_dump(mode="json"), sort_keys=False, allow_unicode=True, width=100)
        handle, temp = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(HEADER + body)
            os.replace(temp, self.path)
        except BaseException:
            Path(temp).unlink(missing_ok=True)
            raise
