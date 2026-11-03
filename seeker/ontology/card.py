"""The ``Card`` class from schema/seeker.yaml."""

from __future__ import annotations

from pydantic import ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

from seeker.ontology.base import SeekerModel
from seeker.ontology.fields import CreativeField
from seeker.ontology.types import CardId, Synonym, Tag


class Card(SeekerModel):
    """One topic card, the atom of a draw. A draw takes one card from each of
    several decks and asks whether the collision is a real idea."""

    model_config = ConfigDict(
        title="Card",
        json_schema_extra={
            "class_uri": "seeker:Card",
            "see_also": ["https://en.wikipedia.org/wiki/Morphological_analysis_(problem-solving)"],
        },
    )

    id: CardId = Field(
        title="id",
        description="The card's stable identifier, unique across the deck set.",
        examples=["granular-synthesis"],
        json_schema_extra={"slot_uri": "seeker:id", "identifier": True},
    )
    name: str = Field(
        title="name",
        min_length=1,
        description="Human-readable name, as it should appear in prompts and reports.",
        examples=["granular synthesis"],
        json_schema_extra={"slot_uri": "skos:prefLabel"},
    )
    synonyms: tuple[Synonym, ...] = Field(
        default=(),
        title="synonyms",
        description=(
            "Other names for the card in specialist literatures, used to expand "
            "prior-art searches. Must not repeat the name or each other, "
            "case-insensitively."
        ),
        examples=[["microsound", "grain cloud"]],
        json_schema_extra={"slot_uri": "skos:altLabel"},
    )
    fields: tuple[CreativeField, ...] = Field(
        default=(),
        title="fields",
        description=(
            "The creative fields the card belongs to. Empty means cross-cutting: "
            "the card applies to every field."
        ),
        examples=[["music", "visual-art"]],
        json_schema_extra={"slot_uri": "seeker:fields"},
    )
    tags: tuple[Tag, ...] = Field(
        default=(),
        title="tags",
        description="Free-form labels outside the creative-field vocabulary.",
        examples=[["demoscene"]],
        json_schema_extra={"slot_uri": "seeker:tags"},
    )
    note: str | None = Field(
        default=None,
        title="note",
        description="Optional clarification of what the card means or excludes.",
        examples=["The 1957 Daphne Oram machine, not the later software."],
        json_schema_extra={"slot_uri": "skos:scopeNote"},
    )

    @model_validator(mode="after")
    def _synonyms_are_distinct(self) -> Card:
        seen = {Synonym(self.name).folded} if self.name else set()
        for synonym in self.synonyms:
            if synonym.folded in seen:
                raise PydanticCustomError(
                    "duplicate_synonym",
                    "synonym '{synonym}' repeats the name or another synonym",
                    {"synonym": str(synonym)},
                )
            seen.add(synonym.folded)
        return self

    @property
    def search_terms(self) -> tuple[str, ...]:
        """The name followed by every synonym: the vocabulary for prior-art search."""
        return (self.name, *self.synonyms)

    @property
    def is_cross_cutting(self) -> bool:
        """True when the card lists no field and so applies to every field."""
        return not self.fields

    def in_field(self, field: CreativeField) -> bool:
        """True if the card lists ``field`` or is cross-cutting."""
        return self.is_cross_cutting or field in self.fields

    def lists_field(self, field: CreativeField) -> bool:
        """True only if the card explicitly lists ``field``."""
        return field in self.fields

    def matches(self, term: str) -> bool:
        """True if ``term`` is the card's name or one of its synonyms, ignoring
        case and surrounding or repeated whitespace."""
        folded = " ".join(term.split()).casefold()
        return any(" ".join(t.split()).casefold() == folded for t in self.search_terms)
