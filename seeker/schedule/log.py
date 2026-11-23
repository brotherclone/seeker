"""The scheduled run's own records: one ScheduledRun per trigger, and the lock that stops
two triggers from overlapping."""

from __future__ import annotations

import fcntl
import os
import tempfile
from pathlib import Path

import yaml
from pydantic import ValidationError

from seeker.ontology import ScheduledRun, ScheduleOutcome

LOCK_NAME = ".lock"


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
        body = yaml.safe_dump(run.model_dump(mode="json", exclude_none=True), sort_keys=False, allow_unicode=True)
        handle, temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=self.folder)
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            out.write(body)
        os.replace(temp, path)
        return path

    def all(self) -> tuple[ScheduledRun, ...]:
        """Every readable record, oldest first. A record that does not parse is skipped, so one
        corrupt file cannot stop the schedule."""
        if not self.folder.is_dir():
            return ()
        found: list[ScheduledRun] = []
        for path in self.folder.glob("*.yaml"):
            try:
                found.append(ScheduledRun.model_validate(yaml.safe_load(path.read_text(encoding="utf-8"))))
            except (OSError, UnicodeDecodeError, yaml.YAMLError, ValidationError):
                continue
        return tuple(sorted(found, key=lambda run: run.started_at))

    def last(self) -> ScheduledRun | None:
        runs = self.all()
        return runs[-1] if runs else None

    def last_advanced(self) -> ScheduledRun | None:
        advanced = [r for r in self.all() if r.schedule_outcome is ScheduleOutcome.ADVANCED]
        return advanced[-1] if advanced else None


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
