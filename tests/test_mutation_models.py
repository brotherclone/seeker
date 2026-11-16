"""Unit tests for the mutation ontology: Lineage, MutationOrigin, and the
optional lineage, mutation, carried_from and both_orders slots."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from seeker.debate.elo import Ratings
from seeker.ontology import DebateRun, Generation, Lineage, MutationKind, MutationOrigin, RoleName
from tests.test_generation_models import generation, idea

ROOT = Path(__file__).resolve().parent.parent
DIGEST = "c" * 64


def origin() -> MutationOrigin:
    return MutationOrigin(parent_run_path="debates/x.yaml", parent_run_digest=DIGEST, mutation_seed=7, round=2)


def test_card_swap_names_its_axis_and_card() -> None:
    swap = Lineage(parent_position=10, mutation_kind="card_swap", swapped_axis="medium", replaced_card="camera-obscura")
    assert swap.mutation_kind is MutationKind.CARD_SWAP
    with pytest.raises(ValidationError, match="names its swapped axis"):
        Lineage(parent_position=10, mutation_kind="card_swap", swapped_axis="medium")


@pytest.mark.parametrize("kind", ["reworking", "carried"])
def test_only_a_swap_names_a_card(kind: str) -> None:
    assert Lineage(parent_position=3, mutation_kind=kind).swapped_axis is None
    with pytest.raises(ValidationError, match="only a card swap"):
        Lineage(parent_position=3, mutation_kind=kind, replaced_card="zine")


def test_origin_round_starts_at_two() -> None:
    with pytest.raises(ValidationError):
        MutationOrigin(parent_run_path="debates/x.yaml", parent_run_digest=DIGEST, mutation_seed=7, round=1)


def test_mutator_is_a_role_name() -> None:
    assert RoleName("mutator") is RoleName.MUTATOR


def test_mutated_generation_needs_lineage_on_every_idea() -> None:
    plain = generation((idea(1), idea(2)))
    assert plain.round == 1
    with pytest.raises(ValidationError, match="lineage exactly when"):
        Generation.model_validate({**plain.model_dump(), "mutation": origin().model_dump()})
    child = idea(1).model_copy(update={"lineage": Lineage(parent_position=4, mutation_kind="reworking")})
    with pytest.raises(ValidationError, match="lineage exactly when"):
        generation((child, idea(2)))
    both = (child, idea(2).model_copy(update={"lineage": Lineage(parent_position=4, mutation_kind="carried")}))
    record = {**plain.model_dump(), "ideas": [i.model_dump() for i in both], "mutation": origin().model_dump()}
    mutated = Generation.model_validate(record)
    assert mutated.round == 2


@pytest.mark.parametrize("name", ["2026-11-04-round-1-literal", "2026-11-04-round-1-metaphorical"])
def test_round_one_generations_load_without_lineage(name: str) -> None:
    record = Generation.model_validate(yaml.safe_load((ROOT / "generations" / f"{name}.yaml").read_text()))
    assert record.mutation is None
    assert all(i.lineage is None for i in record.ideas)


def test_round_one_debate_run_loads_single_order() -> None:
    run = DebateRun.model_validate(yaml.safe_load((ROOT / "debates" / "2026-11-14-round-1-literal.yaml").read_text()))
    tournament = run.tournament
    assert tournament is not None and tournament.both_orders is False
    assert all(d.carried_from is None for d in run.debates)
    recomputed = Ratings.recompute(tournament.entrants, tournament.comparisons, tournament.k_factor, tournament.initial_rating)
    assert recomputed == tournament.ratings
