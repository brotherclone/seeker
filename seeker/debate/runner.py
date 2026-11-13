"""A whole debate run over a recorded generation: every idea debated, then the tournament."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

import yaml
from pydantic import ConfigDict, Field

from seeker.debate.debater import Debater, DebateOutcome
from seeker.debate.meter import CostMeter
from seeker.debate.record import DebateSink, ResumeCheck
from seeker.debate.roles import DebateRoles
from seeker.ontology import DebateRun, Generation, GitCommit, SeekerModel, Sha256Digest, StopReason, Usage, WorkId


class GenerationInput(SeekerModel):
    """A generation record as a debate reads it: where it is, its bytes' digest, and its content."""

    model_config = ConfigDict(title="GenerationInput")

    label: str = Field(description="The path recorded in the run, relative to the repository when inside it.")
    digest: Sha256Digest = Field(description="SHA-256 of the file's bytes.")
    generation: Generation

    @classmethod
    def read(cls, path: Path, root: Path) -> GenerationInput:
        data = path.read_bytes()
        resolved = path.resolve()
        label = str(resolved.relative_to(root)) if resolved.is_relative_to(root) else str(resolved)
        generation = Generation.model_validate(yaml.safe_load(data.decode("utf-8")))
        return cls(label=label, digest=hashlib.sha256(data).hexdigest(), generation=generation)


class RunProgress(SeekerModel):
    """What one call to the runner did, for the command line to report."""

    model_config = ConfigDict(title="RunProgress")

    run: DebateRun
    debated: tuple[DebateOutcome, ...] = Field(default=(), description="Ideas debated by this call, in order.")
    captured: tuple[WorkId, ...] = Field(default=(), description="Works the prosecutor captured during this call.")


class DebateRunner:
    """Debates every idea of a generation that the record does not cover yet, saving after each one."""

    def __init__(self, roles: DebateRoles, debater: Debater, meter: CostMeter) -> None:
        self.roles = roles
        self.debater = debater
        self.meter = meter

    def start(self, source: GenerationInput, seed: int, git_commit: GitCommit | None) -> DebateRun:
        return DebateRun(
            generation_path=source.label,
            generation_digest=source.digest,
            role_digests=self.roles.digests,
            catalog_digest=self.debater.works.catalog().digest,
            git_commit=git_commit,
            tournament_seed=seed,
            started_at=datetime.now(timezone.utc),
            budget_usd=self.meter.budget_usd,
            usage=Usage.zero(),
            estimated_cost_usd=0.0,
        )

    def resume_check(self, source: GenerationInput, seed: int) -> ResumeCheck:
        return ResumeCheck(source.digest, self.roles.digests, seed)

    def debate_all(
        self,
        source: GenerationInput,
        seed: int,
        sink: DebateSink | None = None,
        record: DebateRun | None = None,
        git_commit: GitCommit | None = None,
    ) -> RunProgress:
        """Debate every idea not yet in the record. Stops cleanly at the budget."""
        if record is not None:
            self.resume_check(source, seed).verify(record)
            current = record.model_copy(update={"budget_usd": self.meter.budget_usd, "stop_reason": None})
        else:
            current = self.start(source, seed, git_commit)
        done = {d.position for d in current.debates} | {f.position for f in current.debate_failures}
        draws = {draw.position: draw for draw in source.generation.draw_batch.draws}
        debated: list[DebateOutcome] = []
        captured: list[WorkId] = []
        for idea in source.generation.ideas:
            if idea.position in done:
                continue
            if self.meter.reached(current):
                current = self._saved(current.model_copy(update={"stop_reason": StopReason.BUDGET}), sink)
                return RunProgress(run=current, debated=tuple(debated), captured=tuple(captured))
            outcome = self.debater.debate(idea, draws[idea.position])
            debated.append(outcome)
            captured += [work.work_id for work in outcome.captured]
            current = self._saved(self._with(current, outcome), sink)
        return RunProgress(run=current, debated=tuple(debated), captured=tuple(captured))

    def _with(self, run: DebateRun, outcome: DebateOutcome) -> DebateRun:
        debates = run.debates + ((outcome.debate,) if outcome.debate is not None else ())
        failures = run.debate_failures + outcome.failures
        updated = DebateRun.model_validate(
            {
                **run.model_dump(),
                "debates": [d.model_dump() for d in sorted(debates, key=lambda d: d.position)],
                "debate_failures": [f.model_dump() for f in sorted(failures, key=lambda f: f.position)],
            }
        )
        return self.meter.totals(updated)

    def _saved(self, run: DebateRun, sink: DebateSink | None) -> DebateRun:
        run = self.meter.totals(run)
        if sink is not None:
            sink.save(run)
        return run
