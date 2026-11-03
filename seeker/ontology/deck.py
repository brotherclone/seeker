"""The ``Deck`` class from schema/seeker.yaml."""

from __future__ import annotations

from collections import Counter

from pydantic import ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

from seeker.ontology.base import SeekerModel
from seeker.ontology.card import Card
from seeker.ontology.fields import CreativeField
from seeker.ontology.types import AxisId, CardId


class Deck(SeekerModel):
    """All the cards on one axis of the morphological box, loaded from one file
    in decks/. Axes are independent, so cards from different decks combine
    freely."""

    model_config = ConfigDict(title="Deck", json_schema_extra={"class_uri": "seeker:Deck"})

    axis: AxisId = Field(
        title="axis",
        description="The axis this deck holds; must match the deck file's name.",
        examples=["technique"],
        json_schema_extra={"slot_uri": "seeker:axis", "identifier": True},
    )
    name: str = Field(
        title="name",
        min_length=1,
        description="Human-readable name, as it should appear in prompts and reports.",
        examples=["Technique"],
        json_schema_extra={"slot_uri": "skos:prefLabel"},
    )
    description: str = Field(
        title="description",
        min_length=1,
        description="One line on what the axis contributes to a draw.",
        examples=["How something is made."],
        json_schema_extra={"slot_uri": "dcterms:description"},
    )
    cards: tuple[Card, ...] = Field(
        title="cards",
        min_length=1,
        description="The cards on this axis, in a meaningful order.",
        json_schema_extra={"slot_uri": "seeker:cards"},
    )

    @model_validator(mode="after")
    def _card_ids_are_unique(self) -> Deck:
        counts = Counter(card.id for card in self.cards)
        duplicates = sorted(card_id for card_id, count in counts.items() if count > 1)
        if duplicates:
            raise PydanticCustomError(
                "duplicate_card_id",
                "duplicate card id {ids} in deck '{axis}'",
                {"ids": ", ".join(f"'{d}'" for d in duplicates), "axis": str(self.axis)},
            )
        return self

    def __len__(self) -> int:
        return len(self.cards)

    @property
    def card_ids(self) -> tuple[CardId, ...]:
        """Every card id in deck order."""
        return tuple(card.id for card in self.cards)

    def card(self, card_id: str) -> Card | None:
        """The card with ``card_id``, or None if this deck has no such card."""
        return next((card for card in self.cards if card.id == card_id), None)

    def by_field(self, field: CreativeField) -> tuple[Card, ...]:
        """Cards that apply to ``field``, including cross-cutting cards."""
        return tuple(card for card in self.cards if card.in_field(field))

    def listing(self, field: CreativeField) -> tuple[Card, ...]:
        """Cards that explicitly list ``field``."""
        return tuple(card for card in self.cards if card.lists_field(field))
