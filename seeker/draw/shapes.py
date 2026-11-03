"""The six draw shapes and how large a batch a deck set can support."""

from __future__ import annotations

from itertools import combinations
from typing import ClassVar

from pydantic import ConfigDict, Field

from seeker.ontology import AxisId, DeckSet, SeekerModel

CONSTRAINT = AxisId("constraint")
OTHER_AXES: tuple[AxisId, ...] = tuple(axis for axis in DeckSet.REQUIRED_AXES if axis != CONSTRAINT)


class DrawShape(SeekerModel):
    """Which three axes a draw takes cards from: always ``constraint``, plus two
    of technique, medium, historical-artifact and domain, in that order."""

    model_config = ConfigDict(title="DrawShape")

    axes: tuple[AxisId, ...] = Field(min_length=3, max_length=3, description="Constraint first, then canonical order.")

    @classmethod
    def all(cls) -> tuple[DrawShape, ...]:
        """The six shapes, in canonical order."""
        return tuple(cls(axes=(CONSTRAINT, *pair)) for pair in combinations(OTHER_AXES, 2))

    def __str__(self) -> str:
        return " + ".join(self.axes)


class DrawCapacity(SeekerModel):
    """The largest batch a deck set can support without repeating a card,
    assuming the extra draws of an uneven batch land on the worst axes."""

    model_config = ConfigDict(title="DrawCapacity")

    SHAPE_COUNT: ClassVar[int] = 6
    SHAPES_PER_OTHER_AXIS: ClassVar[int] = 3

    largest: int = Field(ge=1, description="The largest drawable batch size.")
    limiting_axis: AxisId = Field(description="The axis that runs out first beyond `largest`.")

    @classmethod
    def worst_usage(cls, axis: str, size: int) -> int:
        """The most cards a batch of ``size`` can take from ``axis``."""
        if axis == CONSTRAINT:
            return size
        q, r = divmod(size, cls.SHAPE_COUNT)
        return cls.SHAPES_PER_OTHER_AXIS * q + min(r, cls.SHAPES_PER_OTHER_AXIS)

    @classmethod
    def of(cls, deck_set: DeckSet) -> DrawCapacity:
        decks = tuple(deck_set.deck(axis) for axis in (CONSTRAINT, *OTHER_AXES))
        size = 1
        while True:
            short = [deck.axis for deck in decks if cls.worst_usage(deck.axis, size + 1) > len(deck)]
            if short:
                return cls(largest=size, limiting_axis=short[0])
            size += 1
