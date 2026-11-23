"""One round of the loop, in process: mutate the head's survivors, debate and rank the new
generation, and render its report, all under one spend cap per trigger."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from pydantic import ConfigDict, Field

from seeker.config import SeekerConfig
from seeker.debate.job import DebateJob, ReportJob
from seeker.debate.meter import CostMeter
from seeker.debate.record import DebateFile
from seeker.generate.record import GenerationFile
from seeker.models import LanguageModel
from seeker.mutate.job import MutationJob
from seeker.ontology import ScheduleOutcome, SeekerModel, StopReason
from seeker.schedule.lineage import LineageState


class RoundResult(SeekerModel):
    """What one trigger's round did: how it ended, the files it wrote or resumed, and its spend."""

    model_config = ConfigDict(title="RoundResult")

    outcome: ScheduleOutcome = Field(description="advanced, or budget when the cap stopped it.")
    round: int = Field(ge=2, description="The round being made.")
    generation: Path = Field(description="The mutated generation.")
    debate_run: Path | None = Field(default=None, description="Its debate run, once started.")
    report: Path | None = Field(default=None, description="Its survivors report, once written.")
    cost_usd: float = Field(ge=0, description="Estimated spend in this trigger only.")

    @property
    def written(self) -> tuple[Path, ...]:
        return tuple(p for p in (self.generation, self.debate_run, self.report) if p is not None)


class RoundRunner:
    """Advances a lineage by one round. The model is shared by mutation, debate and tournament."""

    def __init__(self, config: SeekerConfig, model: LanguageModel, today: date) -> None:
        self.config = config
        self.model = model
        self.today = today

    def generation_path(self, state: LineageState) -> Path:
        """The in-progress generation, or ``<date>-round-<n>-<reading>.yaml`` for a new round."""
        if state.in_progress is not None:
            return state.in_progress
        name = f"{self.today.isoformat()}-round-{state.head.round + 1}-{state.head.reading.value}.yaml"
        return self.config.paths.generations / name

    def debate_path(self, state: LineageState, generation: Path) -> Path:
        if state.in_progress_run is not None:
            return state.in_progress_run
        return self.config.paths.debates / generation.name

    def advance(self, state: LineageState, cap_usd: float) -> RoundResult:
        """Make or resume the round after ``state.head``, spending at most ``cap_usd`` in this call
        (overshooting by at most one model call)."""
        generation_path = self.generation_path(state)
        round_ = state.head.round + 1

        mutation = MutationJob(self.config, state.head.path)
        sink = GenerationFile(generation_path)
        mutation_before = sink.read().estimated_cost_usd if sink.exists() else 0.0
        generation = mutation.run(self.model, sink, budget_usd=mutation_before + cap_usd)
        mutation_spent = max(0.0, generation.estimated_cost_usd - mutation_before)
        if generation.stop_reason is StopReason.BUDGET:
            return RoundResult(
                outcome=ScheduleOutcome.BUDGET, round=round_, generation=generation_path, cost_usd=mutation_spent
            )

        debate = DebateJob(self.config, generation_path, deck_set=mutation.deck_set)
        run_sink = DebateFile(self.debate_path(state, generation_path))
        meter = CostMeter(self.config.prices, 0.0)
        debate_before = meter.spent(run_sink.read()) if run_sink.exists() else 0.0
        remaining = max(0.0, cap_usd - mutation_spent)
        progress = debate.run(self.model, run_sink, debate_before + remaining, debate.works())
        debate_spent = max(0.0, meter.spent(progress.run) - debate_before)
        cost = round(mutation_spent + debate_spent, 6)
        if progress.run.stop_reason is StopReason.BUDGET:
            return RoundResult(
                outcome=ScheduleOutcome.BUDGET,
                round=round_,
                generation=generation_path,
                debate_run=run_sink.path,
                cost_usd=cost,
            )

        report = ReportJob(self.config, deck_set=mutation.deck_set).write(run_sink.path)
        return RoundResult(
            outcome=ScheduleOutcome.ADVANCED,
            round=round_,
            generation=generation_path,
            debate_run=run_sink.path,
            report=report.path,
            cost_usd=cost,
        )
