"""Writing DebateRun records atomically, and refusing to resume onto different inputs."""

from __future__ import annotations

import os
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path

import yaml

from seeker.ontology import DebateRun, RoleDigest, Sha256Digest

HEADER = (
    "# Debate-run record (schema/seeker.yaml: DebateRun). Inputs are pinned: the\n"
    "# generation file's digest, every role file's digest and the tournament seed.\n"
    "# Rerunning with the same output path resumes where the run stopped.\n"
)


class DebateSink(ABC):
    """Where a run in progress is saved after each debate and each comparison."""

    @abstractmethod
    def save(self, run: DebateRun) -> None: ...


class DebateFile(DebateSink):
    """A YAML record on disk, rewritten atomically (temp file, then os.replace)."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def exists(self) -> bool:
        return self.path.is_file()

    def read(self) -> DebateRun:
        return DebateRun.model_validate(yaml.safe_load(self.path.read_text(encoding="utf-8")))

    def save(self, run: DebateRun) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        body = yaml.safe_dump(run.model_dump(mode="json", exclude_none=True), sort_keys=False, allow_unicode=True, width=100)
        handle, temp = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(HEADER + body)
            os.replace(temp, self.path)
        except BaseException:
            Path(temp).unlink(missing_ok=True)
            raise


class DebateResumeMismatch(Exception):
    """A recorded run cannot be continued with these inputs."""

    def __init__(self, field: str, recorded: str, requested: str) -> None:
        self.field = field
        super().__init__(
            f"cannot resume: the existing record's {field} is {recorded!r} but this run's is {requested!r}; "
            "use a new output path"
        )


class ResumeCheck:
    """The pinned inputs a resume must match. The catalog digest is not among them:
    the run's own captured works change it."""

    def __init__(self, generation_digest: Sha256Digest, role_digests: tuple[RoleDigest, ...], seed: int) -> None:
        self.generation_digest = generation_digest
        self.role_digests = role_digests
        self.seed = seed

    def verify(self, record: DebateRun) -> None:
        if record.generation_digest != self.generation_digest:
            raise DebateResumeMismatch(
                "generation digest", record.generation_digest[:12], self.generation_digest[:12]
            )
        for wanted in self.role_digests:
            recorded = record.digest_of(wanted.role_name)
            if recorded != wanted.role_digest:
                raise DebateResumeMismatch(
                    f"{wanted.role_name.value} role digest", (recorded or "none")[:12], wanted.role_digest[:12]
                )
        if record.tournament_seed != self.seed:
            raise DebateResumeMismatch("tournament seed", str(record.tournament_seed), str(self.seed))
