"""Who meets whom in a tournament, in what order, and which idea is shown as A.

Everything derives from the tournament seed through a SHA-256 counter stream,
like draws, so a schedule replays identically from the record.
"""

from __future__ import annotations

import hashlib
from itertools import combinations

from pydantic import ConfigDict, Field, model_validator

from seeker.draw.stream import DrawStream
from seeker.ontology import SeekerModel


class TournamentStream(DrawStream):
    """A DrawStream under its own version, salted so different uses never share numbers."""

    VERSION = "seeker/tournament/v1"

    def __init__(self, seed: int, salt: str = "") -> None:
        super().__init__(seed)
        self.salt = salt

    def next64(self) -> int:
        message = f"{self.VERSION}:{self.salt}:{self.seed}:{self._counter}".encode("ascii")
        self._counter += 1
        return int.from_bytes(hashlib.sha256(message).digest()[:8], "big")


class Pairing(SeekerModel):
    """Two entrants to compare, in the order shown to the judge (A, then B)."""

    model_config = ConfigDict(title="Pairing")

    first: int = Field(ge=1, description="Shown as A.")
    second: int = Field(ge=1, description="Shown as B.")

    @model_validator(mode="after")
    def _distinct(self) -> Pairing:
        if self.first == self.second:
            raise ValueError("a pairing is between two different ideas")
        return self

    @property
    def key(self) -> frozenset[int]:
        return frozenset((self.first, self.second))


class Schedule(SeekerModel):
    """The seeded order of comparisons for a set of entrants."""

    model_config = ConfigDict(title="Schedule")

    pairings: tuple[Pairing, ...] = Field(default=(), description="In the order they are judged.")
    per_entrant: int = Field(ge=0, description="How many comparisons each entrant gets.")

    @classmethod
    def build(cls, entrants: tuple[int, ...], seed: int, max_comparisons: int) -> Schedule:
        ordered = tuple(sorted(set(entrants)))
        n = len(ordered)
        if n < 2:
            return cls(per_entrant=0)
        everyone = tuple(combinations(ordered, 2))
        if len(everyone) <= max_comparisons:
            pairs, per_entrant = everyone, n - 1
        else:
            pairs, per_entrant = cls._regular(ordered, seed, max_comparisons)
        return cls(pairings=cls._ordered(pairs, seed), per_entrant=per_entrant)

    @staticmethod
    def _regular(entrants: tuple[int, ...], seed: int, max_comparisons: int) -> tuple[tuple[tuple[int, int], ...], int]:
        """Every entrant meets the same number k of seeded opponents, no pair twice.

        Entrants are placed on a seeded circle; each meets its k/2 nearest
        neighbours on each side, plus the one opposite when k is odd (which
        needs an even count of entrants)."""
        n = len(entrants)
        k = min(n - 1, (2 * max_comparisons) // n)
        if k % 2 and n % 2:
            k -= 1
        circle = [entrants[i] for i in TournamentStream(seed, "circle").permutation(n)]
        pairs: set[tuple[int, int]] = set()
        for index, entrant in enumerate(circle):
            offsets = list(range(1, k // 2 + 1)) + ([n // 2] if k % 2 else [])
            for offset in offsets:
                other = circle[(index + offset) % n]
                pairs.add((min(entrant, other), max(entrant, other)))
        return tuple(sorted(pairs)), k

    @staticmethod
    def _ordered(pairs: tuple[tuple[int, int], ...], seed: int) -> tuple[Pairing, ...]:
        stream = TournamentStream(seed, "order")
        order = stream.permutation(len(pairs))
        sides = TournamentStream(seed, "sides")
        ordered = []
        for index in order:
            low, high = pairs[index]
            ordered.append(Pairing(first=low, second=high) if sides.below(2) == 0 else Pairing(first=high, second=low))
        return tuple(ordered)

    def __len__(self) -> int:
        return len(self.pairings)
