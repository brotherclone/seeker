"""The scheduled run's own records: one ScheduledRun per trigger, and the lock that stops
two triggers from overlapping."""

from __future__ import annotations

import fcntl
import os
import tempfile
from pathlib import Path

import yaml
from pydantic import ConfigDict, Field, ValidationError

from seeker.ontology import ScheduledRun, ScheduleOutcome, SeekerModel

LOCK_NAME = ".lock"


class RunRecord(SeekerModel):
    """One ScheduledRun together with the file it is stored in, so it can be named and rewritten."""

    model_config = ConfigDict(title="RunRecord")

    path: Path = Field(description="The record's YAML file in the runs folder.")
    run: ScheduledRun = Field(description="The trigger the file records.")


class RunLog:
    """ScheduledRun records in the configured runs folder, one YAML file per trigger, named by start time."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder

    def write(self, run: ScheduledRun) -> Path:
        self.folder.mkdir(parents=True, exist_ok=True)
        stem = run.started_at.strftime("%Y-%m-%dT%H%M%S")
        path = self.folder / f"{stem}.yaml"
        suffix = 2
        while path.exists():
            path = self.folder / f"{stem}-{suffix}.yaml"
            suffix += 1
        self._save(path, run)
        return path

    def rewrite(self, record: RunRecord) -> Path:
        """Replace an existing record's file with ``record.run``, keeping its file name."""
        self._save(record.path, record.run)
        return record.path

    def _save(self, path: Path, run: ScheduledRun) -> None:
        body = yaml.safe_dump(run.model_dump(mode="json", exclude_none=True), sort_keys=False, allow_unicode=True)
        handle, temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            out.write(body)
        os.replace(temp, path)

    def read(self, path: Path) -> RunRecord:
        """The record stored at ``path``; raises ValueError when it is not a readable ScheduledRun."""
        try:
            run = ScheduledRun.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError, yaml.YAMLError, ValidationError) as error:
            raise ValueError(f"{path}: not a readable ScheduledRun record ({type(error).__name__})") from error
        return RunRecord(path=path, run=run)

    def all(self) -> tuple[RunRecord, ...]:
        """Every readable record, oldest first. A record that does not parse is skipped, so one
        corrupt file cannot stop the schedule."""
        if not self.folder.is_dir():
            return ()
        found: list[RunRecord] = []
        for path in self.folder.glob("*.yaml"):
            try:
                found.append(self.read(path))
            except ValueError:
                continue
        return tuple(sorted(found, key=lambda record: record.run.started_at))

    def last(self) -> ScheduledRun | None:
        records = self.all()
        return records[-1].run if records else None

    def last_advanced(self) -> ScheduledRun | None:
        """The latest round that advanced and was not discarded; the cadence measures from it."""
        advanced = [
            r.run for r in self.all() if r.run.schedule_outcome is ScheduleOutcome.ADVANCED and not r.run.discarded
        ]
        return advanced[-1] if advanced else None

    def last_with_outputs(self) -> RunRecord | None:
        """The latest advanced or budget-stopped trigger, not discarded, whose files should be on disk."""
        found = [r for r in self.all() if r.run.wrote_outputs]
        return found[-1] if found else None


class RunLock:
    """An exclusive, non-blocking ``flock`` on ``<runs>/.lock``. The kernel releases it when the
    holding process exits, so a lock left by a dead process is free again without any cleanup."""

    def __init__(self, folder: Path) -> None:
        self.path = folder / LOCK_NAME
        self._handle: int | None = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(handle)
            return False
        os.ftruncate(handle, 0)
        os.write(handle, f"{os.getpid()}\n".encode())
        self._handle = handle
        return True

    def release(self) -> None:
        if self._handle is not None:
            fcntl.flock(self._handle, fcntl.LOCK_UN)
            os.close(self._handle)
            self._handle = None
