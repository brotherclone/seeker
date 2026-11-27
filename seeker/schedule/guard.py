"""The missing-output guard: a trigger never redoes a round whose files left the disk.

The cadence reads the git-ignored runs folder, but the lineage head is read from the round
outputs on disk. A branch switch that drops the latest round's outputs makes the two disagree,
and without this check the next due trigger silently re-runs that round."""

from __future__ import annotations

from pathlib import Path

from seeker.config import SeekerConfig
from seeker.schedule.log import RunLog, RunRecord


class OutputsMissing(Exception):
    """The latest trigger that did round work names files that are no longer on disk."""

    def __init__(self, record: str, missing: tuple[str, ...]) -> None:
        self.record = record
        self.missing = missing
        super().__init__(
            f"the outputs of {record} are missing: {', '.join(missing)}. "
            "The round they hold would be redone, so nothing ran. Restore them (check out the "
            "branch that has them, or copy them back), or, if they were dropped on purpose, run "
            f'uv run seeker-schedule discard {record} --note "<why>"'
        )


class OutputGuard:
    """Checks the latest non-discarded advanced or budget record against the disk."""

    def __init__(self, config: SeekerConfig, log: RunLog) -> None:
        self.config = config
        self.log = log

    def resolve(self, written: str) -> Path:
        path = Path(written)
        return path if path.is_absolute() else self.config.root / path

    def label(self, path: Path) -> str:
        resolved = path.resolve()
        root = self.config.root.resolve()
        return str(resolved.relative_to(root)) if resolved.is_relative_to(root) else str(resolved)

    def missing(self, record: RunRecord) -> tuple[str, ...]:
        return tuple(p for p in record.run.written_paths if not self.resolve(p).exists())

    def check(self) -> None:
        """Raise OutputsMissing when the latest record with outputs names a file that is gone."""
        record = self.log.last_with_outputs()
        if record is None:
            return
        missing = self.missing(record)
        if missing:
            raise OutputsMissing(self.label(record.path), missing)
