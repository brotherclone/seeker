"""The ``Draw`` and ``DrawBatch`` classes from schema/seeker.yaml."""

from __future__ import annotations

from pydantic import ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

from seeker.ontology.base import SeekerModel
from seeker.ontology.fields import CreativeField
from seeker.ontology.types import AxisId, CardId, Sha256Digest

CARDS_PER_DRAW = 3


class Draw(SeekerModel):
    """One collision: three cards, one from each of three axes, always
    including a constraint. The raw material the generator turns into a
    one-sentence idea."""

    model_config = ConfigDict(title="Draw", json_schema_extra={"class_uri": "seeker:Draw"})

    position: int = Field(
        title="position",
        ge=1,
        description="The draw's 1-based position within its batch.",
        examples=[1],
        json_schema_extra={"slot_uri": "seeker:position"},
    )
    axes: tuple[AxisId, ...] = Field(
        title="axes",
        min_length=CARDS_PER_DRAW,
        max_length=CARDS_PER_DRAW,
        description=(
            "The three axes the draw's cards come from, constraint first, then the "
            "other two in canonical order (technique, medium, historical-artifact, "
            "domain). This is the draw's shape."
        ),
        examples=[["constraint", "technique", "domain"]],
        json_schema_extra={"slot_uri": "seeker:axes"},
    )
    home_field: CreativeField = Field(
        title="home_field",
        description=(
            "The creative field this draw is anchored in. At least one of its cards "
            "explicitly lists this field."
        ),
        examples=["comics"],
        json_schema_extra={"slot_uri": "seeker:homeField"},
    )
    drawn_cards: tuple[CardId, ...] = Field(
        title="drawn_cards",
        min_length=CARDS_PER_DRAW,
        max_length=CARDS_PER_DRAW,
        description=(
            "The drawn cards, referenced by card id, one per axis in the same order "
            "as axes."
        ),
        examples=[["wordless", "risograph-print", "screentone"]],
        json_schema_extra={"slot_uri": "seeker:drawnCards"},
    )

    @model_validator(mode="after")
    def _distinct(self) -> Draw:
        if len(set(self.axes)) != len(self.axes):
            raise PydanticCustomError("repeated_axis", "a draw's axes must be distinct")
        if len(set(self.drawn_cards)) != len(self.drawn_cards):
            raise PydanticCustomError("repeated_card", "a draw's cards must be distinct")
        return self

    @property
    def shape(self) -> tuple[AxisId, ...]:
        """The draw's shape: its axes, constraint first."""
        return self.axes

    def card_for(self, axis: str) -> CardId | None:
        """The card drawn from ``axis``, or None if the draw doesn't use that axis."""
        return next((card for a, card in zip(self.axes, self.drawn_cards) if a == axis), None)


class DrawBatch(SeekerModel):
    """A balanced set of draws produced from one seed and one deck set: shapes
    evenly represented, no card repeated, home fields rotating through the
    creative fields. Fully reproducible from its seed and deck-set digest."""

    model_config = ConfigDict(title="DrawBatch", json_schema_extra={"class_uri": "seeker:DrawBatch"})

    seed: int = Field(
        title="seed",
        ge=0,
        description=(
            "The non-negative integer the draw's random stream is derived from. The "
            "same seed, deck content and batch size always produce the same batch."
        ),
        examples=[7],
        json_schema_extra={"slot_uri": "seeker:seed"},
    )
    deck_set_digest: Sha256Digest = Field(
        title="deck_set_digest",
        description=(
            "Digest of the deck set the batch was drawn from. Replaying against decks "
            "with a different digest is an error."
        ),
        examples=[Sha256Digest.EXAMPLES[0]],
        json_schema_extra={"slot_uri": "seeker:deckSetDigest"},
    )
    draws: tuple[Draw, ...] = Field(
        title="draws",
        min_length=1,
        description="The draws in the batch, in position order.",
        json_schema_extra={"slot_uri": "seeker:draws"},
    )

    @model_validator(mode="after")
    def _positions_are_sequential(self) -> DrawBatch:
        positions = [draw.position for draw in self.draws]
        if positions != list(range(1, len(self.draws) + 1)):
            raise PydanticCustomError(
                "bad_positions", "draw positions must run 1..{size} in order", {"size": len(self.draws)}
            )
        return self

    @property
    def size(self) -> int:
        return len(self.draws)

    @property
    def card_ids(self) -> tuple[CardId, ...]:
        """Every drawn card id, in draw then axis order."""
        return tuple(card for draw in self.draws for card in draw.drawn_cards)
