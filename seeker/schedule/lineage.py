"""Where the lineage stands, read only from the records on disk: its head, any round in
progress, and whether the head waits at a review point.

Nothing here trusts a state file, so a round made by hand between triggers is picked up
exactly like one the scheduler made."""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml
from pydantic import ConfigDict, Field, ValidationError

from seeker.config import SeekerConfig
from seeker.debate.carried import CarriedDebates, CarryError
from seeker.ontology import DebateRun, Generation, Reading, ReviewSignOff, SeekerModel, Sha256Digest, StopReason

SCRATCH = "scratch"


class LineageError(Exception):
    """The records do not describe one lineage the scheduler can advance."""


class NoHead(LineageError):
    def __init__(self, folder: Path) -> None:
        super().__init__(f"no finished debate run in {folder}; run round 1 by hand first")


class TwoHeads(LineageError):
    def __init__(self, round_: int, labels: tuple[str, ...]) -> None:
        self.labels = labels
        super().__init__(
            f"{len(labels)} finished runs share the highest round ({round_}): {', '.join(labels)}; "
            "the scheduler advances one lineage, so move or finish all but one"
        )


class UnreadableRecord(LineageError):
    def __init__(self, path: Path, reason: str) -> None:
        super().__init__(f"{path}: not a readable record ({reason})")


class LineageHead(SeekerModel):
    """The finished debate run a lineage would mutate next."""

    model_config = ConfigDict(title="LineageHead")

    path: Path = Field(description="The debate run's file.")
    label: str = Field(description="The path relative to the repository root when inside it.")
    digest: Sha256Digest = Field(description="SHA-256 of the run file's bytes.")
    round: int = Field(ge=1, description="The round of the generation the run debated.")
    reading: Reading = Field(description="The generation's reading, which names the next round's files.")


class LineageState(SeekerModel):
    """The head, any round already started from it, and the review gate."""

    model_config = ConfigDict(title="LineageState")

    head: LineageHead
    in_progress: Path | None = Field(
        default=None, description="A generation mutated from the head, whose round is not finished yet."
    )
    in_progress_run: Path | None = Field(
        default=None, description="The debate run of the in-progress generation, if one was started."
    )
    report_missing: bool = Field(description="The head has no survivors report yet.")
    at_review_point: bool = Field(description="The head's round is a multiple of review_every.")
    signed_off: bool = Field(description="A sign-off names the head and matches its current bytes.")

    @property
    def awaiting_review(self) -> bool:
        return self.at_review_point and not self.signed_off


class LineageRecords:
    """Reads debate runs, generations and sign-offs from the configured folders, skipping scratch."""

    def __init__(self, config: SeekerConfig) -> None:
        self.config = config
        self.root = config.root

    # -- reading ---------------------------------------------------------------------

    def label(self, path: Path) -> str:
        resolved = path.resolve()
        return str(resolved.relative_to(self.root)) if resolved.is_relative_to(self.root) else str(resolved)

    @staticmethod
    def records(folder: Path) -> tuple[Path, ...]:
        if not folder.is_dir():
            return ()
        return tuple(sorted(p for p in folder.rglob("*.yaml") if SCRATCH not in p.relative_to(folder).parts))

    @staticmethod
    def _load(path: Path) -> object:
        try:
            return yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
            raise UnreadableRecord(path, str(exc).splitlines()[0]) from exc

    def run_at(self, path: Path) -> DebateRun:
        try:
            return DebateRun.model_validate(self._load(path))
        except ValidationError as exc:
            raise UnreadableRecord(path, f"{exc.error_count()} validation errors as a DebateRun") from exc

    def generation_at(self, path: Path) -> Generation:
        try:
            return Generation.model_validate(self._load(path))
        except ValidationError as exc:
            raise UnreadableRecord(path, f"{exc.error_count()} validation errors as a Generation") from exc

    def sign_offs(self) -> tuple[ReviewSignOff, ...]:
        found = []
        for path in self.records(self.config.paths.reviews):
            try:
                found.append(ReviewSignOff.model_validate(self._load(path)))
            except ValidationError as exc:
                raise UnreadableRecord(path, f"{exc.error_count()} validation errors as a ReviewSignOff") from exc
        return tuple(found)

    @staticmethod
    def is_finished(run: DebateRun) -> bool:
        """Finished as mutation requires: the tournament ran to the end and was not skipped."""
        return run.stop_reason is StopReason.FINISHED and run.tournament is not None and not run.tournament.skipped

    # -- the lineage -----------------------------------------------------------------

    def head(self) -> LineageHead:
        """The finished run whose generation has the highest round. Raises NoHead or TwoHeads."""
        best: list[LineageHead] = []
        for path in self.records(self.config.paths.debates):
            run = self.run_at(path)
            if not self.is_finished(run):
                continue
            generation = self.generation_at(self.root / run.generation_path)
            head = LineageHead(
                path=path,
                label=self.label(path),
                digest=hashlib.sha256(path.read_bytes()).hexdigest(),
                round=generation.round,
                reading=generation.reading,
            )
            if not best or head.round > best[0].round:
                best = [head]
            elif head.round == best[0].round:
                best.append(head)
        if not best:
            raise NoHead(self.config.paths.debates)
        if len(best) > 1:
            raise TwoHeads(best[0].round, tuple(h.label for h in best))
        return best[0]

    def child_of(self, head: LineageHead) -> Path | None:
        """A non-scratch generation mutated from ``head``, if one exists."""
        target = head.path.resolve()
        for path in self.records(self.config.paths.generations):
            origin = self.generation_at(path).mutation
            if origin is None:
                continue
            try:
                parent = CarriedDebates.parent_path(origin, self.root)
            except CarryError:
                continue
            if parent.resolve() == target:
                return path
        return None

    def run_of(self, generation: Path) -> Path | None:
        """The non-scratch debate run of ``generation``, if one was started."""
        target = generation.resolve()
        for path in self.records(self.config.paths.debates):
            if (self.root / self.run_at(path).generation_path).resolve() == target:
                return path
        return None

    def state(self) -> LineageState:
        head = self.head()
        child = self.child_of(head)
        review_every = self.config.schedule.review_every
        return LineageState(
            head=head,
            in_progress=child,
            in_progress_run=self.run_of(child) if child is not None else None,
            report_missing=not (self.config.paths.reports / f"{head.path.stem}.md").is_file(),
            at_review_point=head.round % review_every == 0,
            signed_off=any(s.approves(head.label, head.digest) for s in self.sign_offs()),
        )
