"""What the mutator sees."""

from pathlib import Path

import pytest

from seeker.config import SeekerConfig
from seeker.debate.runner import GenerationInput
from seeker.decks import DeckDirectory
from seeker.mutate.plan import MutationPlan, RunInput
from seeker.mutate.prompt import MutationPrompt
from seeker.ontology import DeckSet

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def decks() -> DeckSet:
    return DeckDirectory(SeekerConfig.load(ROOT / "seeker.yaml").paths.decks).load()


@pytest.fixture(scope="module")
def plan(decks: DeckSet) -> MutationPlan:
    parent = RunInput.read(ROOT / "debates" / "2026-11-14-round-1-literal.yaml", ROOT)
    source = GenerationInput.read(ROOT / parent.run.generation_path, ROOT)
    return MutationPlan.build(parent, source, decks, 7, 2)


def test_reworking_prompt_shows_the_revised_parent_and_its_debate(plan: MutationPlan, decks: DeckSet) -> None:
    entry = plan.entry_at(1)
    debate = entry.parent.debate
    assert debate.defense.revision is not None
    text = MutationPrompt(entry, decks).render()
    assert debate.final_statement in text
    assert f"(originally: {entry.parent.idea.statement})" in text
    for critique in debate.critiques:
        assert critique.failure in text
        assert debate.defense.reply_to(critique.role_name).argument in text
    for card in entry.draw.drawn_cards:
        assert f"(id: {card})" in text
    assert "Task: reworking" in text and "Already taken" not in text


def test_second_reworking_sees_the_first(plan: MutationPlan, decks: DeckSet) -> None:
    first = "A chapel camera that sings vespers because light is late."
    text = MutationPrompt(plan.entry_at(2), decks, taken=(first,)).render()
    assert "Already taken" in text and first in text


def test_swap_prompt_names_the_new_card(plan: MutationPlan, decks: DeckSet) -> None:
    entry = plan.entry_at(3)
    text = MutationPrompt(entry, decks).render()
    assert f"(id: {entry.new_card}) is new and replaces" in text
    assert f"(id: {entry.lineage.replaced_card})" in text
    assert f"in this order of ids: {', '.join(entry.draw.drawn_cards)}" in text


def test_carried_entries_are_not_prompted(plan: MutationPlan, decks: DeckSet) -> None:
    with pytest.raises(ValueError):
        MutationPrompt(plan.entry_at(13), decks)
