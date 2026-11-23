"""The mutator end to end against ScriptedModel: children, carried parents, failures, resume."""

import shutil
from pathlib import Path

import pytest

from seeker.config import SeekerConfig
from seeker.debate.runner import GenerationInput
from seeker.decks import DeckDirectory
from seeker.generate import GenerationFile, LoadedRole, ResumeMismatch
from seeker.models import ScriptedModel
from seeker.mutate.mutator import IdeaMutator
from seeker.mutate.plan import MutationPlan, RunInput
from seeker.ontology import DeckSet, Generation, MutationKind, Reading, RoleName, StopReason, Usage
from tests.test_generator import CALL, answer

ROOT = Path(__file__).resolve().parent.parent
RUN = ROOT / "debates" / "2026-11-14-round-1-literal.yaml"


@pytest.fixture(scope="module")
def config() -> SeekerConfig:
    return SeekerConfig.load(ROOT / "seeker.yaml")


@pytest.fixture(scope="module")
def decks(config: SeekerConfig) -> DeckSet:
    return DeckDirectory(config.paths.decks).load()


@pytest.fixture(scope="module")
def role() -> LoadedRole:
    return LoadedRole.load(ROOT / "prompts" / "mutator.yaml")


def make_plan(decks: DeckSet, run_path: Path = RUN, root: Path = ROOT) -> MutationPlan:
    parent = RunInput.read(run_path, root)
    source = GenerationInput.read(ROOT / parent.run.generation_path, ROOT)
    return MutationPlan.build(parent, source, decks, 7, 2)


def replies(plan: MutationPlan, positions: range | tuple[int, ...] | None = None) -> tuple:
    wanted = set(positions) if positions is not None else {e.position for e in plan.children}
    return tuple(
        answer(e.draw, statement=f"A child {e.position} that hums because paper is a speaker.")
        for e in plan.children
        if e.position in wanted
    )


def mutator(role: LoadedRole, model: ScriptedModel, decks: DeckSet, config: SeekerConfig) -> IdeaMutator:
    return IdeaMutator(role, model, decks, config.prices)


def test_default_plan_makes_twelve_calls(role, decks, config) -> None:
    plan = make_plan(decks)
    model = ScriptedModel(replies(plan))
    record = mutator(role, model, decks, config).mutate(plan, Reading.LITERAL)
    assert len(model.requests) == 12 and model.remaining == 0
    assert record.role_name is RoleName.MUTATOR
    assert record.mutation == plan.origin and record.round == 2
    assert [i.position for i in record.ideas] == list(range(1, 16))
    assert record.usage == Usage.total((CALL,) * 12)
    assert record.estimated_cost_usd > 0
    assert Generation.model_validate(record.model_dump(mode="json")) == record


def test_carried_ideas_equal_their_parents(role, decks, config) -> None:
    plan = make_plan(decks)
    record = mutator(role, ScriptedModel(replies(plan)), decks, config).mutate(plan, Reading.LITERAL)
    for entry in plan.carried:
        idea = record.idea_at(entry.position)
        assert idea.lineage.mutation_kind is MutationKind.CARRIED
        assert idea.lineage.parent_position == entry.parent.position
        same = idea.model_dump(exclude={"position", "lineage", "usage"})
        assert same == entry.parent.idea.model_dump(exclude={"position", "lineage", "usage"})
        assert idea.usage == Usage.zero()


def test_second_reworking_is_shown_the_first(role, decks, config) -> None:
    plan = make_plan(decks)
    model = ScriptedModel(replies(plan))
    mutator(role, model, decks, config).mutate(plan, Reading.LITERAL)
    assert "Already taken" not in model.requests[0].prompt
    assert "A child 1 that hums" in model.requests[1].prompt


def test_reading_the_replaced_card_is_retried_then_failed(role, decks, config) -> None:
    plan = make_plan(decks)
    swap = plan.entry_at(3)
    wrong = answer(swap.parent.draw)  # reads the replaced card instead of its replacement
    rest = replies(plan, tuple(p for p in range(1, 13) if p != 3))
    model = ScriptedModel((*rest[:2], wrong, wrong, *rest[2:]))
    record = mutator(role, model, decks, config).mutate(plan, Reading.LITERAL)
    assert model.requests[3].retry is not None
    failure = next(f for f in record.failures if f.position == 3)
    assert "card_readings" in failure.reason
    assert record.idea_at(3) is None and len(record.ideas) == 14


def test_resume_after_five_children(role, decks, config, tmp_path: Path) -> None:
    plan = make_plan(decks)
    sink = GenerationFile(tmp_path / "round-2.yaml")
    first = ScriptedModel(replies(plan, range(1, 6)))
    with pytest.raises(Exception, match="no scripted reply"):
        mutator(role, first, decks, config).mutate(plan, Reading.LITERAL, sink=sink)
    assert [i.position for i in sink.read().ideas] == [1, 2, 3, 4, 5]
    second = ScriptedModel(replies(plan, range(6, 13)))
    record = mutator(role, second, decks, config).mutate(plan, Reading.LITERAL, record=sink.read(), sink=sink)
    assert len(second.requests) == 7
    assert "A child 5 that hums" in second.requests[0].prompt  # position 6 is 6's second reworking
    assert len(record.ideas) == 15


def test_changed_parent_run_is_refused(role, decks, config, tmp_path: Path) -> None:
    plan = make_plan(decks)
    record = mutator(role, ScriptedModel(replies(plan)), decks, config).mutate(plan, Reading.LITERAL)
    copy = tmp_path / RUN.name
    shutil.copy(RUN, copy)
    copy.write_text(copy.read_text() + "\n# edited\n")
    changed = make_plan(decks, copy, tmp_path)
    with pytest.raises(ResumeMismatch, match="parent run digest"):
        mutator(role, ScriptedModel(()), decks, config).mutate(changed, Reading.LITERAL, record=record)


def test_changed_decks_are_refused(role, decks, config) -> None:
    plan = make_plan(decks)
    record = mutator(role, ScriptedModel(replies(plan)), decks, config).mutate(plan, Reading.LITERAL)
    edited = decks.model_copy(update={"decks": tuple(
        d.model_copy(update={"description": d.description + " (edited)"}) if d.axis == "domain" else d
        for d in decks.decks
    )})
    with pytest.raises(ResumeMismatch, match="deck-set digest"):
        mutator(role, ScriptedModel(()), edited, config).mutate(make_plan(edited), Reading.LITERAL, record=record)


# -- budget -----------------------------------------------------------------------------


def per_call(config: SeekerConfig, role: LoadedRole) -> float:
    return config.prices.cost(role.role.model, CALL)


def test_budget_stops_after_the_call_that_crosses_it(role, decks, config, tmp_path: Path) -> None:
    plan = make_plan(decks)
    sink = GenerationFile(tmp_path / "round-2.yaml")
    model = ScriptedModel(replies(plan, range(1, 7)))
    budget = per_call(config, role) * 5.5
    record = IdeaMutator(role, model, decks, config.prices, budget_usd=budget).mutate(
        plan, Reading.LITERAL, sink=sink
    )
    assert len(model.requests) == 6
    assert [i.position for i in record.ideas] == [1, 2, 3, 4, 5, 6]
    assert record.stop_reason is StopReason.BUDGET
    assert sink.read().stop_reason is StopReason.BUDGET


def test_resume_with_more_budget_finishes_and_clears_the_stop(role, decks, config, tmp_path: Path) -> None:
    plan = make_plan(decks)
    sink = GenerationFile(tmp_path / "round-2.yaml")
    low = per_call(config, role) * 5.5
    IdeaMutator(role, ScriptedModel(replies(plan, range(1, 7))), decks, config.prices, budget_usd=low).mutate(
        plan, Reading.LITERAL, sink=sink
    )
    second = ScriptedModel(replies(plan, range(7, 13)))
    record = IdeaMutator(role, second, decks, config.prices, budget_usd=2.0).mutate(
        plan, Reading.LITERAL, record=sink.read(), sink=sink
    )
    assert len(second.requests) == 6
    assert len(record.ideas) == 15
    assert record.stop_reason is None and sink.read().stop_reason is None


def test_no_budget_never_stops(role, decks, config) -> None:
    plan = make_plan(decks)
    record = mutator(role, ScriptedModel(replies(plan)), decks, config).mutate(plan, Reading.LITERAL)
    assert record.stop_reason is None and len(record.ideas) == 15
