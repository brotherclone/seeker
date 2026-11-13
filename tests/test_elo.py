"""Per-axis Elo and survivors (debate-ideas task 7.3)."""

import pytest

from seeker.debate.elo import Ratings, Survivors
from seeker.ontology import AxisVerdict, Comparison, Rating, ScoreAxis, Usage

USAGE = Usage(input_tokens=1, output_tokens=1, cache_read_tokens=0, cache_write_tokens=0)


def match(first: int, second: int, novelty: int, feasibility: int, promise: int) -> Comparison:
    winners = {ScoreAxis.NOVELTY: novelty, ScoreAxis.FEASIBILITY: feasibility, ScoreAxis.PROMISE: promise}
    verdicts = tuple(AxisVerdict(axis_name=axis, winner=w, ruling="r") for axis, w in winners.items())
    return Comparison(first=first, second=second, verdicts=verdicts, model="claude-sonnet-5-5", usage=USAGE)


def rating(ratings: tuple[Rating, ...], position: int, axis: ScoreAxis) -> Rating:
    return next(r for r in ratings if r.position == position and r.axis_name is axis)


def test_hand_computed_three_idea_elo() -> None:
    # 1 beats 2 (both at 1500): +16 / -16. Then 1 (1516) beats 3 (1500):
    # expected = 1/(1+10^(-16/400)) = 0.5230; gain = 32 * 0.4770 = 15.2645.
    games = (match(1, 2, 1, 1, 1), match(3, 1, 1, 1, 1))
    ratings = Ratings.recompute((1, 2, 3), games, 32.0, 1500.0)
    one = rating(ratings, 1, ScoreAxis.PROMISE)
    assert one.rating == pytest.approx(1516 + 15.264, abs=1e-3) and (one.wins, one.losses) == (2, 0)
    assert rating(ratings, 2, ScoreAxis.PROMISE).rating == pytest.approx(1484)
    assert rating(ratings, 3, ScoreAxis.PROMISE).rating == pytest.approx(1500 - 15.264, abs=1e-3)
    assert sum(r.rating for r in ratings if r.axis_name is ScoreAxis.PROMISE) == pytest.approx(4500)


def test_axes_move_independently() -> None:
    ratings = Ratings.recompute((3, 7), (match(3, 7, novelty=3, feasibility=7, promise=7),), 32.0, 1500.0)
    assert rating(ratings, 3, ScoreAxis.NOVELTY).rating > 1500 > rating(ratings, 3, ScoreAxis.FEASIBILITY).rating
    assert rating(ratings, 7, ScoreAxis.PROMISE).rating == pytest.approx(1516)


def test_failed_comparison_changes_nothing() -> None:
    failed = Comparison(first=1, second=2, failed=True, model="claude-sonnet-5-5", usage=USAGE)
    ratings = Ratings.recompute((1, 2), (failed,), 32.0, 1500.0)
    assert {r.rating for r in ratings} == {1500.0} and {r.wins for r in ratings} == {0}


def test_recompute_is_exact() -> None:
    games = tuple(match(a, b, a, b, a) for a, b in ((1, 2), (2, 3), (3, 1), (1, 4), (4, 2)))
    assert Ratings.recompute((1, 2, 3, 4), games, 32.0, 1500.0) == Ratings.recompute((1, 2, 3, 4), games, 32.0, 1500.0)


def test_survivor_tie_breaks() -> None:
    def promise(position: int, value: float, wins: int) -> Rating:
        return Rating(position=position, axis_name=ScoreAxis.PROMISE, rating=value, wins=wins, losses=0)

    ratings = (promise(5, 1520, 2), promise(2, 1520, 3), promise(9, 1500, 1), promise(1, 1500, 1), promise(4, 1400, 0))
    assert Survivors.pick(ratings) == (2, 5, 1)
    assert Survivors.pick(ratings[:2]) == (2, 5)
