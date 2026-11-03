"""The ``DeckSet`` class from schema/seeker.yaml."""

from __future__ import annotations

from collections.abc import Iterable
from itertools import groupby
from typing import ClassVar

from pydantic import ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

from seeker.ontology.base import SeekerModel
from seeker.ontology.card import Card
from seeker.ontology.deck import Deck
from seeker.ontology.types import AxisId, CardId


class SharedCardId(SeekerModel):
    """A card id that appears in more than one deck of a set."""

    model_config = ConfigDict(title="SharedCardId")

    card_id: CardId = Field(description="The id that collides.")
    axes: tuple[AxisId, ...] = Field(description="Every axis whose deck uses the id, sorted.")


class DeckSet(SeekerModel):
    """Every deck a run draws from. Card ids are unique across the whole set and
    the set must include the required starting axes: technique, medium,
    historical-artifact, constraint and domain."""

    model_config = ConfigDict(
        title="DeckSet", json_schema_extra={"class_uri": "seeker:DeckSet", "tree_root": True}
    )

    REQUIRED_AXES: ClassVar[tuple[AxisId, ...]] = tuple(
        AxisId(axis)
        for axis in ("technique", "medium", "historical-artifact", "constraint", "domain")
    )

    decks: tuple[Deck, ...] = Field(
        title="decks",
        min_length=1,
        description="Every deck in the set, one per axis.",
        json_schema_extra={"slot_uri": "seeker:decks"},
    )

    @classmethod
    def missing_axes(cls, present: Iterable[str]) -> tuple[AxisId, ...]:
        """Required axes absent from ``present``, in canonical order."""
        have = set(present)
        return tuple(axis for axis in cls.REQUIRED_AXES if axis not in have)

    @staticmethod
    def shared_card_ids(decks: Iterable[Deck]) -> tuple[SharedCardId, ...]:
        """Card ids used by more than one deck, sorted by id."""
        placements = sorted(
            {(card_id, deck.axis) for deck in decks for card_id in deck.card_ids}
        )
        shared = (
            (card_id, tuple(axis for _, axis in group))
            for card_id, group in groupby(placements, key=lambda placement: placement[0])
        )
        return tuple(
            SharedCardId(card_id=card_id, axes=axes) for card_id, axes in shared if len(axes) > 1
        )

    @model_validator(mode="after")
    def _set_rules(self) -> DeckSet:
        axes = [deck.axis for deck in self.decks]
        repeated = sorted({axis for axis in axes if axes.count(axis) > 1})
        if repeated:
            raise PydanticCustomError(
                "duplicate_axis", "axis repeated in deck set: {axes}", {"axes": ", ".join(repeated)}
            )
        missing = self.missing_axes(axes)
        if missing:
            raise PydanticCustomError(
                "missing_axis", "missing required axis: {axes}", {"axes": ", ".join(missing)}
            )
        shared = self.shared_card_ids(self.decks)
        if shared:
            raise PydanticCustomError(
                "shared_card_id",
                "card ids used in more than one deck: {ids}",
                {"ids": "; ".join(f"{s.card_id} ({', '.join(s.axes)})" for s in shared)},
            )
        return self

    @property
    def ordered(self) -> tuple[Deck, ...]:
        """Decks sorted by axis id: the canonical order for digests and reports."""
        return tuple(sorted(self.decks, key=lambda deck: deck.axis))

    @property
    def axes(self) -> tuple[AxisId, ...]:
        return tuple(deck.axis for deck in self.ordered)

    def deck(self, axis: str) -> Deck | None:
        """The deck holding ``axis``, or None."""
        return next((deck for deck in self.decks if deck.axis == axis), None)

    def card(self, card_id: str) -> Card | None:
        """The card with ``card_id`` from whichever deck holds it, or None."""
        return next((c for deck in self.decks if (c := deck.card(card_id)) is not None), None)
