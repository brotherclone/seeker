"""One debate and its report, set up from config.

Shared by ``seeker-debate`` and the scheduled run, so both debate, rank and report a round the same way."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from pydantic import ConfigDict, Field

from seeker.config import SeekerConfig
from seeker.debate.carried import CarriedDebates
from seeker.debate.debater import Debater
from seeker.debate.meter import CostMeter
from seeker.debate.record import DebateFile
from seeker.debate.report import SurvivorReport
from seeker.debate.roles import DebateRoles
from seeker.debate.runner import DebateRunner, GenerationInput, RunProgress
from seeker.debate.tournament import TournamentRunner
from seeker.decks import DeckDirectory
from seeker.generate.provenance import GitRepo
from seeker.models import LanguageModel
from seeker.ontology import DebateRun, DeckSet, RoleName, SeekerModel, StopReason
from seeker.works.catalog import WorkNotes


class DebateJob:
    """Everything a debate needs before its first model call. Building one makes no API call,
    and refuses a generation whose mutation stopped at its budget."""

    def __init__(
        self, config: SeekerConfig, generation_path: Path, seed: int | None = None, deck_set: DeckSet | None = None
    ) -> None:
        self.config = config
        self.deck_set = deck_set or DeckDirectory(config.paths.decks).load()
        self.source = GenerationInput.read(generation_path, config.root).require_finished()
        self.roles = DebateRoles.load(config.paths.prompts, config.prices)
        self.seed = seed if seed is not None else self.source.generation.draw_batch.seed
        self.carried = CarriedDebates.for_generation(self.source.generation, config.root)

    def works(self) -> WorkNotes:
        """The vault's works catalog; raises VaultNotConfigured when there is no vault."""
        return WorkNotes(folder=self.config.vault().works, deck_set=self.deck_set)

    def run(
        self,
        model: LanguageModel,
        sink: DebateFile,
        budget_usd: float,
        works: WorkNotes,
        tournament: bool = True,
    ) -> RunProgress:
        """Debate into ``sink`` (resuming it when it exists), then rank unless stopped or told not to.
        The returned progress holds the run as saved last."""
        meter = CostMeter(self.config.prices, budget_usd)
        reading = self.source.generation.reading
        debater = Debater(self.roles, model, self.deck_set, works, reading, date.today())
        record = sink.read() if sink.exists() else None
        progress = DebateRunner(self.roles, debater, meter).debate_all(
            self.source,
            self.seed,
            sink=sink,
            record=record,
            git_commit=GitRepo(self.config.root).commit(),
            carried=self.carried,
        )
        current = progress.run
        if current.stop_reason is StopReason.BUDGET:
            return progress
        if not tournament:
            current = DebateRun.model_validate({**current.model_dump(), "stop_reason": StopReason.NO_TOURNAMENT})
            sink.save(current)
        else:
            ranker = TournamentRunner(
                self.roles.role(RoleName.JUDGE),
                model,
                reading,
                meter,
                self.config.tournament.max_comparisons,
                self.config.tournament.both_orders,
            )
            current = ranker.play(current, self.source.generation, sink)
        return progress.model_copy(update={"run": current})


class WrittenReport(SeekerModel):
    """Where a survivors report was written, and whether its generation changed since the run."""

    model_config = ConfigDict(title="WrittenReport")

    path: Path = Field(description="The rendered report.")
    generation_changed: bool = Field(description="The debated generation's bytes no longer match the run's digest.")


class ReportJob:
    """Renders a debate run's survivors report. Makes no API call."""

    def __init__(self, config: SeekerConfig, deck_set: DeckSet | None = None) -> None:
        self.config = config
        self.deck_set = deck_set or DeckDirectory(config.paths.decks).load()

    def path_for(self, run_path: Path) -> Path:
        return self.config.paths.reports / f"{run_path.stem}.md"

    def write(self, run_path: Path) -> WrittenReport:
        config = self.config
        run = DebateFile(run_path).read()
        source = GenerationInput.read(config.root / run.generation_path, config.root)
        parent = None
        if (origin := source.generation.mutation) is not None:
            parent_path = CarriedDebates.parent_path(origin, config.root)
            parent = DebateFile(parent_path).read() if parent_path.is_file() else None
        report = SurvivorReport(run, source.generation, self.deck_set, config.prices, parent=parent)
        path = report.write(config.paths.reports, run_path.stem)
        return WrittenReport(path=path, generation_changed=source.digest != run.generation_digest)
