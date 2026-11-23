"""One mutation, set up from config: the parent run, its plan and the mutator role.

Shared by ``seeker-mutate`` and the scheduled run, so both build a round the same way."""

from __future__ import annotations

from pathlib import Path

from seeker.config import SeekerConfig
from seeker.debate.runner import GenerationInput
from seeker.decks import DeckDirectory
from seeker.generate.provenance import GitRepo
from seeker.generate.record import GenerationFile
from seeker.generate.role_file import LoadedRole
from seeker.models import LanguageModel
from seeker.mutate.mutator import IdeaMutator
from seeker.mutate.plan import MutationPlan, RunInput
from seeker.ontology import DeckSet, Generation, Reading

ROLE_FILE = "mutator.yaml"


class MutationJob:
    """Everything a mutation needs before its first model call. Building one makes no API call."""

    def __init__(
        self, config: SeekerConfig, run_path: Path, seed: int | None = None, deck_set: DeckSet | None = None
    ) -> None:
        self.config = config
        self.deck_set = deck_set or DeckDirectory(config.paths.decks).load()
        self.parent = RunInput.read(run_path, config.root)
        self.source = GenerationInput.read(config.root / self.parent.run.generation_path, config.root)
        self.seed = seed if seed is not None else self.parent.run.tournament_seed
        self.plan = MutationPlan.build(self.parent, self.source, self.deck_set, self.seed, config.mutation.reworkings)
        self.role = LoadedRole.load(config.paths.prompts / ROLE_FILE)

    @property
    def reading(self) -> Reading:
        return self.source.generation.reading

    @property
    def round(self) -> int:
        return self.plan.origin.round

    def mutator(self, model: LanguageModel, budget_usd: float | None) -> IdeaMutator:
        return IdeaMutator(self.role, model, self.deck_set, self.config.prices, budget_usd=budget_usd)

    def run(self, model: LanguageModel, sink: GenerationFile, budget_usd: float | None) -> Generation:
        """Mutate into ``sink``, resuming it when it exists. Stops cleanly at ``budget_usd``."""
        record = sink.read() if sink.exists() else None
        return self.mutator(model, budget_usd).mutate(
            self.plan, self.reading, record=record, sink=sink, git_commit=GitRepo(self.config.root).commit()
        )
