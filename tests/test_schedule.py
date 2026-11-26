"""Tournament pairings (debate-ideas task 7.1)."""

from collections import Counter

import pytest

from seeker.debate.schedule import Schedule, TournamentStream


def counts(schedule: Schedule) -> Counter:
    return Counter(p for pairing in schedule.pairings for p in (pairing.first, pairing.second))


def test_round_robin_for_twelve() -> None:
    schedule = Schedule.build(tuple(range(1, 13)), seed=7, max_comparisons=66)
    assert len(schedule) == 66 and schedule.per_entrant == 11
    assert len({p.key for p in schedule.pairings}) == 66
    assert set(counts(schedule).values()) == {11}


@pytest.mark.parametrize("n", [13, 20, 30])
def test_large_batches_get_equal_seeded_opponents(n: int) -> None:
    schedule = Schedule.build(tuple(range(1, n + 1)), seed=7, max_comparisons=66)
    assert len(schedule) <= 66
    assert len({p.key for p in schedule.pairings}) == len(schedule)
    assert set(counts(schedule).values()) == {schedule.per_entrant}
    assert schedule.per_entrant >= 2


def test_same_seed_same_schedule_and_sides() -> None:
    a = Schedule.build((1, 3, 4, 7, 9), seed=7, max_comparisons=66)
    assert a == Schedule.build((9, 7, 4, 3, 1), seed=7, max_comparisons=66)
    assert a != Schedule.build((1, 3, 4, 7, 9), seed=8, max_comparisons=66)


def test_sides_vary() -> None:
    schedule = Schedule.build(tuple(range(1, 13)), seed=7, max_comparisons=66)
    assert any(p.first > p.second for p in schedule.pairings) and any(p.first < p.second for p in schedule.pairings)


def test_too_few_entrants() -> None:
    assert len(Schedule.build((4,), seed=7, max_comparisons=66)) == 0


def test_streams_are_salted_and_versioned() -> None:
    assert TournamentStream(7, "a").next64() != TournamentStream(7, "b").next64()
    from seeker.draw.stream import DrawStream

    assert TournamentStream(7).next64() != DrawStream(7).next64()


# --- mutate-ideas 5.3: both orders ---------------------------------------------------


def test_both_orders_round_robin_for_twelve() -> None:
    schedule = Schedule.build(tuple(range(1, 13)), seed=7, max_comparisons=132, both_orders=True)
    assert len(schedule) == 132 and schedule.per_entrant == 11
    assert len({p.key for p in schedule.pairings}) == 66
    firsts, reverses = schedule.pairings[0::2], schedule.pairings[1::2]
    assert all((r.first, r.second) == (f.second, f.first) for f, r in zip(firsts, reverses))
    single = Schedule.build(tuple(range(1, 13)), seed=7, max_comparisons=66)
    assert firsts == single.pairings


def test_both_orders_fifteen_entrants() -> None:
    schedule = Schedule.build(tuple(range(1, 16)), seed=7, max_comparisons=132, both_orders=True)
    pairs = [p.key for p in schedule.pairings[0::2]]
    assert len(pairs) == len(set(pairs)) <= 66
    assert set(counts(schedule).values()) == {2 * schedule.per_entrant}
    assert schedule.per_entrant == 8 and len(schedule) == 120


def test_round_one_record_replays_single_order() -> None:
    from pathlib import Path

    import yaml

    from seeker.ontology import DebateRun

    path = Path(__file__).resolve().parent.parent / "debates" / "2026-11-14-round-1-literal.yaml"
    run = DebateRun.model_validate(yaml.safe_load(path.read_text()))
    played = run.tournament
    schedule = Schedule.build(played.entrants, run.tournament_seed, played.max_comparisons, played.both_orders)
    assert [(p.first, p.second) for p in schedule.pairings] == [(c.first, c.second) for c in played.comparisons]
