"""Per-axis Elo ladders, recomputed from a tournament's stored comparisons, and its survivors."""

from __future__ import annotations

from typing import ClassVar

from seeker.ontology import Comparison, Rating, ScoreAxis


class Ladder:
    """One axis's ratings, updated comparison by comparison with the standard Elo formula."""

    SCALE: ClassVar[float] = 400.0

    def __init__(self, axis: ScoreAxis, entrants: tuple[int, ...], k_factor: float, initial: float) -> None:
        self.axis = axis
        self.k_factor = k_factor
        self.ratings = {position: initial for position in entrants}
        self.wins = {position: 0 for position in entrants}
        self.losses = {position: 0 for position in entrants}

    def expected(self, position: int, opponent: int) -> float:
        return 1.0 / (1.0 + 10 ** ((self.ratings[opponent] - self.ratings[position]) / self.SCALE))

    def play(self, comparison: Comparison) -> None:
        verdict = comparison.verdict_on(self.axis)
        if comparison.failed or verdict is None:
            return
        winner = verdict.winner
        loser = comparison.second if winner == comparison.first else comparison.first
        gain = self.k_factor * (1.0 - self.expected(winner, loser))
        self.ratings[winner] += gain
        self.ratings[loser] -= gain
        self.wins[winner] += 1
        self.losses[loser] += 1

    def records(self) -> tuple[Rating, ...]:
        return tuple(
            Rating(
                position=position,
                axis_name=self.axis,
                rating=round(self.ratings[position], 6),
                wins=self.wins[position],
                losses=self.losses[position],
            )
            for position in sorted(self.ratings)
        )


class Ratings:
    """All three ladders over the same comparisons, in schedule order."""

    @staticmethod
    def recompute(
        entrants: tuple[int, ...], comparisons: tuple[Comparison, ...], k_factor: float, initial: float
    ) -> tuple[Rating, ...]:
        ladders = [Ladder(axis, entrants, k_factor, initial) for axis in ScoreAxis]
        for comparison in comparisons:
            for ladder in ladders:
                ladder.play(comparison)
        return tuple(rating for ladder in ladders for rating in ladder.records())


class Survivors:
    """The top entrants by promise: highest rating, then most promise wins, then lowest position."""

    COUNT: ClassVar[int] = 3

    @classmethod
    def pick(cls, ratings: tuple[Rating, ...]) -> tuple[int, ...]:
        promise = [r for r in ratings if r.axis_name is ScoreAxis.PROMISE]
        ranked = sorted(promise, key=lambda r: (-r.rating, -r.wins, r.position))
        return tuple(r.position for r in ranked[: cls.COUNT])
