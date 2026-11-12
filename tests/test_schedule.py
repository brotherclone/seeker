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
