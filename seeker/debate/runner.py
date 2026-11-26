"""A whole debate run over a recorded generation: every idea debated, then the tournament."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

import yaml
from pydantic import ConfigDict, Field

from seeker.debate.carried import CarriedDebates
from seeker.debate.debater import Debater, DebateOutcome
from seeker.debate.meter import CostMeter
from seeker.debate.record import DebateSink, ResumeCheck
from seeker.debate.roles import DebateRoles
from seeker.ontology import DebateRun, Generation, GitCommit, SeekerModel, Sha256Digest, StopReason, Usage, WorkId


class UnfinishedMutation(Exception):
    """A mutated generation stopped at its budget, so it is not ready to debate."""

    def __init__(self, label: str, parent_run_path: str) -> None:
        self.label = label
        super().__init__(
            f"{label}: mutation stopped at its budget, so it cannot be debated yet; resume it with "
            f"seeker-mutate {parent_run_path} --out {label} --budget <more>"
        )


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

    def require_finished(self) -> GenerationInput:
        """This input, or UnfinishedMutation when its mutation stopped at its budget."""
        if self.generation.stop_reason is StopReason.BUDGET:
            origin = self.generation.mutation
            raise UnfinishedMutation(self.label, origin.parent_run_path if origin else "<parent run>")
        return self


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
        carried: CarriedDebates | None = None,
    ) -> RunProgress:
        """Debate every idea not yet in the record, after copying any carried debates. Stops cleanly at the budget."""
        if record is not None:
            self.resume_check(source, seed).verify(record)
            current = record.model_copy(update={"budget_usd": self.meter.budget_usd, "stop_reason": None})
        else:
            current = self.start(source, seed, git_commit)
        current = self._carry(current, carried or CarriedDebates(), sink)
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

    def _carry(self, run: DebateRun, carried: CarriedDebates, sink: DebateSink | None) -> DebateRun:
        """The run with every carried debate it lacks, saved if anything was added. No call is made."""
        have = {d.position for d in run.debates}
        missing = tuple(d for d in carried.debates if d.position not in have)
        if not missing:
            return run
        debates = sorted((*run.debates, *missing), key=lambda d: d.position)
        updated = DebateRun.model_validate({**run.model_dump(), "debates": [d.model_dump() for d in debates]})
        return self._saved(updated, sink)

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
