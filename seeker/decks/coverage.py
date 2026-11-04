"""How well a deck set covers each creative field."""

from __future__ import annotations

from pydantic import ConfigDict, Field

from seeker.ontology import AxisId, CreativeField, Deck, DeckSet, SeekerModel


class FieldCoverage(SeekerModel):
    """How many cards in one deck explicitly list one creative field.
    Cross-cutting cards (no fields) are not counted."""

    model_config = ConfigDict(title="FieldCoverage")

    axis: AxisId = Field(description="The deck's axis.")
    field: CreativeField = Field(description="The creative field counted.")
    count: int = Field(ge=0, description="Cards in the deck that list the field.")

    @classmethod
    def of_deck(cls, deck: Deck) -> tuple[FieldCoverage, ...]:
        return tuple(
            cls(axis=deck.axis, field=field, count=len(deck.listing(field))) for field in CreativeField
        )

    @classmethod
    def of_set(cls, deck_set: DeckSet) -> tuple[FieldCoverage, ...]:
        return tuple(row for deck in deck_set.ordered for row in cls.of_deck(deck))
