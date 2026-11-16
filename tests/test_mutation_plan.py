"""The mutation plan: children and carried parents, seeded swaps, and refusals."""

from pathlib import Path

import pytest

from seeker.config import SeekerConfig
from seeker.debate.runner import GenerationInput
from seeker.decks import DeckDirectory
from seeker.mutate.plan import MutationPlan, ParentGenerationChanged, RunInput, UnfinishedRun
from seeker.ontology import CreativeField, DeckSet, Draw, MutationKind, StopReason

ROOT = Path(__file__).resolve().parent.parent
RUN = ROOT / "debates" / "2026-11-14-round-1-literal.yaml"


@pytest.fixture(scope="module")
def decks() -> DeckSet:
    return DeckDirectory(SeekerConfig.load(ROOT / "seeker.yaml").paths.decks).load()


@pytest.fixture(scope="module")
def parent() -> RunInput:
    return RunInput.read(RUN, ROOT)


@pytest.fixture(scope="module")
def source(parent: RunInput) -> GenerationInput:
    return GenerationInput.read(ROOT / parent.run.generation_path, ROOT)


def build(parent: RunInput, source: GenerationInput, decks: DeckSet, seed: int = 7, reworkings: int = 2) -> MutationPlan:
    return MutationPlan.build(parent, source, decks, seed, reworkings)


def test_default_plan_shape(parent: RunInput, source: GenerationInput, decks: DeckSet) -> None:
    plan = build(parent, source, decks)
    kinds = [(e.position, e.parent.position, e.kind) for e in plan.entries]
    rework, swap, carried = MutationKind.REWORKING, MutationKind.CARD_SWAP, MutationKind.CARRIED
    assert kinds == [
        (1, 10, rework), (2, 10, rework), (3, 10, swap), (4, 10, swap),
        (5, 6, rework), (6, 6, rework), (7, 6, swap), (8, 6, swap),
        (9, 3, rework), (10, 3, rework), (11, 3, swap), (12, 3, swap),
        (13, 10, carried), (14, 6, carried), (15, 3, carried),
    ]
    assert len(plan.children) == 12 and len(plan.carried) == 3
    assert plan.batch.size == 15
    assert plan.origin.round == 2
    assert plan.origin.parent_run_digest == parent.digest
    assert plan.origin.parent_run_path == "debates/2026-11-14-round-1-literal.yaml"


def test_reworkings_and_carried_keep_the_parents_draw(parent: RunInput, source: GenerationInput, decks: DeckSet) -> None:
    plan = build(parent, source, decks)
    for entry in plan.entries:
        if entry.kind is not MutationKind.CARD_SWAP:
            assert entry.draw.drawn_cards == entry.parent.draw.drawn_cards
            assert entry.new_card is None


def test_swaps_keep_shape_and_other_cards(parent: RunInput, source: GenerationInput, decks: DeckSet) -> None:
    plan = build(parent, source, decks)
    swaps = [e for e in plan.entries if e.kind is MutationKind.CARD_SWAP]
    assert [e.lineage.swapped_axis for e in swaps] == [
        a for e in plan.entries if e.kind is MutationKind.CARRIED for a in e.draw.axes[1:]
    ]
    for entry in swaps:
        old, new = entry.parent.draw, entry.draw
        axis = entry.lineage.swapped_axis
        assert (new.axes, new.home_field) == (old.axes, old.home_field)
        assert entry.lineage.replaced_card == old.card_for(axis)
        assert entry.new_card != old.card_for(axis)
        assert decks.deck(axis).card(entry.new_card) is not None
        kept = [(a, c) for a, c in zip(new.axes, new.drawn_cards) if a != axis]
        assert kept == [(a, c) for a, c in zip(old.axes, old.drawn_cards) if a != axis]


def test_no_swapped_in_card_repeats(parent: RunInput, source: GenerationInput, decks: DeckSet) -> None:
    plan = build(parent, source, decks)
    round_one = set(source.generation.draw_batch.card_ids)
    new_cards = [e.new_card for e in plan.children if e.new_card is not None]
    assert len(new_cards) == len(set(new_cards)) == 6
    assert not set(new_cards) & round_one


def test_same_inputs_same_plan(parent: RunInput, source: GenerationInput, decks: DeckSet) -> None:
    assert build(parent, source, decks) == build(parent, source, decks)
    assert build(parent, source, decks).batch != build(parent, source, decks, seed=8).batch


def test_reworkings_setting(parent: RunInput, source: GenerationInput, decks: DeckSet) -> None:
    plan = build(parent, source, decks, reworkings=3)
    assert len(plan.children) == 15
    third = plan.entry_at(3)
    assert third is not None and third.attempt == 3
    assert [s.position for s in plan.siblings_before(third)] == [1, 2]


def test_swap_keeps_the_home_field(parent: RunInput, source: GenerationInput, decks: DeckSet) -> None:
    """When the swapped card was the only one listing the home field, its replacement must list it."""
    field, constraint, medium, domain = _lonely_home_card(decks)
    draws = [
        Draw(position=d.position, axes=("constraint", "medium", "domain"), home_field=field,
             drawn_cards=(constraint, medium, domain)) if d.position == 3 else d
        for d in source.generation.draw_batch.draws
    ]
    batch = source.generation.draw_batch.model_copy(update={"draws": tuple(draws)})
    altered = source.model_copy(update={"generation": source.generation.model_copy(update={"draw_batch": batch})})
    plan = build(parent, altered, decks)
    swap = next(e for e in plan.children if e.parent.position == 3 and e.lineage.swapped_axis == "medium")
    assert decks.card(swap.new_card).lists_field(field)


def _lonely_home_card(decks: DeckSet) -> tuple[CreativeField, str, str, str]:
    """A field, and constraint/medium/domain cards where only the medium card lists that field,
    while some medium cards don't (so narrowing matters)."""
    for field in CreativeField:
        others = [c for c in decks.deck("medium").cards if not c.lists_field(field)]
        listing = [c for c in decks.deck("medium").cards if c.lists_field(field)]
        constraint = next((c for c in decks.deck("constraint").cards if not c.lists_field(field)), None)
        domain = next((c for c in decks.deck("domain").cards if not c.lists_field(field)), None)
        if others and len(listing) > 1 and constraint and domain:
            return field, constraint.id, listing[-1].id, domain.id
    pytest.skip("the decks have no field fit for this test")


@pytest.mark.parametrize(
    ("update", "message"),
    [
        ({"stop_reason": StopReason.BUDGET}, "'budget'"),
        ({"stop_reason": StopReason.NO_TOURNAMENT}, "'no_tournament'"),
        ({"stop_reason": None}, "still running"),
    ],
)
def test_unfinished_runs_are_refused(parent: RunInput, source: GenerationInput, decks: DeckSet, update: dict, message: str) -> None:
    unfinished = parent.model_copy(update={"run": parent.run.model_copy(update=update)})
    with pytest.raises(UnfinishedRun, match=message):
        build(unfinished, source, decks)


def test_skipped_tournament_is_refused(parent: RunInput, source: GenerationInput, decks: DeckSet) -> None:
    skipped = parent.run.tournament.model_copy(update={"skipped": True, "comparisons": (), "survivors": ()})
    run = parent.run.model_copy(update={"tournament": skipped})
    with pytest.raises(UnfinishedRun, match="skipped"):
        build(parent.model_copy(update={"run": run}), source, decks)


def test_changed_parent_generation_is_refused(parent: RunInput, source: GenerationInput, decks: DeckSet) -> None:
    with pytest.raises(ParentGenerationChanged, match="round-1-literal"):
        build(parent, source.model_copy(update={"digest": "0" * 64}), decks)


def test_two_survivors_plan_eight_children(parent: RunInput, source: GenerationInput, decks: DeckSet) -> None:
    fewer = parent.run.tournament.model_copy(update={"survivors": (10, 6)})
    run = parent.run.model_copy(update={"tournament": fewer})
    plan = build(parent.model_copy(update={"run": run}), source, decks)
    assert len(plan.children) == 8
    assert [e.parent.position for e in plan.carried] == [10, 6]
