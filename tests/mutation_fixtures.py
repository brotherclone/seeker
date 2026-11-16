"""A mutated round-2 generation built from the committed round-1 run with a scripted mutator."""

from pathlib import Path

from seeker.config import SeekerConfig
from seeker.debate.runner import GenerationInput
from seeker.decks import DeckDirectory
from seeker.generate import GenerationFile, LoadedRole
from seeker.models import ScriptedModel
from seeker.mutate.mutator import IdeaMutator
from seeker.mutate.plan import MutationPlan, RunInput
from seeker.ontology import Reading
from tests.test_generator import answer

ROOT = Path(__file__).resolve().parent.parent
ROUND_ONE_RUN = ROOT / "debates" / "2026-11-14-round-1-literal.yaml"


def mutated_generation(out: Path, run_path: Path = ROUND_ONE_RUN, root: Path = ROOT) -> Path:
    """Write a 15-position mutated generation (12 children, 3 carried) to ``out`` and return it."""
    config = SeekerConfig.load(ROOT / "seeker.yaml")
    decks = DeckDirectory(config.paths.decks).load()
    parent = RunInput.read(run_path, root)
    source = GenerationInput.read(ROOT / parent.run.generation_path, ROOT)
    plan = MutationPlan.build(parent, source, decks, parent.run.tournament_seed, 2)
    replies = tuple(
        answer(e.draw, statement=f"A child {e.position} that hums because paper is a speaker.") for e in plan.children
    )
    mutator = IdeaMutator(LoadedRole.load(ROOT / "prompts" / "mutator.yaml"), ScriptedModel(replies), decks, config.prices)
    mutator.mutate(plan, Reading.LITERAL, sink=GenerationFile(out))
    return out
