"""The ``Work`` class and the ``WorkKind`` and ``CaptureSource`` enums from
schema/seeker.yaml."""

from __future__ import annotations

from datetime import date

from pydantic import ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

from seeker.ontology.base import DescribedStrEnum, SeekerModel
from seeker.ontology.fields import CreativeField
from seeker.ontology.types import CardId, Url, WorkId


class WorkKind(DescribedStrEnum):
    """What sort of thing a captured work is. Coarse on purpose: the cards a
    work links say what it is about, the kind says what form it takes."""

    PIECE = "piece", "A finished artwork, composition or comic not better described by another kind."
    RECORDING = "recording", "A released or archived audio or video recording."
    INSTRUMENT = "instrument", "A musical instrument or sound-making machine, built or designed."
    SOFTWARE = "software", "A program, plugin, tool or code library."
    GAME = "game", "A board, card, tabletop or electronic game."
    PUBLICATION = "publication", "A book, zine, magazine, album booklet or other edition."
    PERFORMANCE = "performance", "A live performance, concert or happening."
    INSTALLATION = "installation", "A site-specific or gallery installation."
    PAPER = "paper", "A research paper, thesis or technical report."
    PRODUCT = "product", "A commercial device or kit."
    OTHER = "other", "Anything else; the capture default until refined by hand."


class CaptureSource(DescribedStrEnum):
    """Who or what added a work to the vault, so hand-captured works can be told
    apart from ones agents found or imported in bulk."""

    GABE = "gabe", "Captured by hand, usually with the Web Clipper template."
    PROSECUTOR = "prosecutor", "Found by the prior-art prosecutor during a debate and cached."
    IMPORT = "import", "Imported in bulk from another catalog."


class Work(SeekerModel):
    """A creative work, instrument, game, publication or paper that already
    exists, captured as a note in the Obsidian vault and linked to the cards
    it embodies. Works are Seeker's offline prior art: a draw whose cards a
    work already combines is not new."""

    model_config = ConfigDict(
        title="Work",
        json_schema_extra={
            "class_uri": "seeker:Work",
            "see_also": ["https://en.wikipedia.org/wiki/Literature-based_discovery"],
        },
    )

    id: WorkId = Field(
        title="id",
        description="The work's identifier, derived from its note's file name.",
        examples=["oramics-demo-tape-1962"],
        json_schema_extra={"slot_uri": "seeker:id", "identifier": True},
    )
    title: str = Field(
        title="title",
        min_length=1,
        description="The work's title as its creators give it.",
        examples=["Oramics demo tape"],
        json_schema_extra={"slot_uri": "dcterms:title"},
    )
    creators: tuple[str, ...] = Field(
        default=(),
        title="creators",
        description=(
            "The people or groups who made the work, as plain names. Notes may write "
            "them as wikilinks so they show up in the vault's graph."
        ),
        examples=[["Daphne Oram"]],
        json_schema_extra={"slot_uri": "dcterms:creator"},
    )
    year: int | None = Field(
        default=None,
        title="year",
        description="The year the work was made, released or published, when known.",
        examples=[1962],
        json_schema_extra={"slot_uri": "dcterms:date"},
    )
    url: Url | None = Field(
        default=None,
        title="url",
        description="Where the work can be found or was captured from.",
        examples=[Url.EXAMPLES[0]],
        json_schema_extra={"slot_uri": "seeker:url"},
    )
    kind: WorkKind = Field(
        title="kind",
        description="What form the work takes.",
        examples=["recording"],
        json_schema_extra={"slot_uri": "dcterms:type"},
    )
    fields: tuple[CreativeField, ...] = Field(
        default=(),
        title="fields",
        description="The creative fields the work belongs to, when known.",
        examples=[["music"]],
        json_schema_extra={"slot_uri": "seeker:fields"},
    )
    cards: tuple[CardId, ...] = Field(
        default=(),
        title="cards",
        min_length=0,
        description=(
            "The cards the work embodies, referenced by card id. Empty until linked "
            "by hand or by card suggestions."
        ),
        examples=[["oramics", "tape"]],
        json_schema_extra={"slot_uri": "seeker:cards"},
    )
    summary: str | None = Field(
        default=None,
        title="summary",
        description=(
            "A short description of the work. Card suggestions search it along with "
            "the title and the note body."
        ),
        examples=["Daphne Oram demonstrating drawn sound on her Oramics machine."],
        json_schema_extra={"slot_uri": "dcterms:abstract"},
    )
    captured_by: CaptureSource = Field(
        title="captured_by",
        description="Who or what added the work to the vault.",
        examples=["gabe"],
        json_schema_extra={"slot_uri": "seeker:capturedBy"},
    )
    captured_on: date = Field(
        title="captured_on",
        description="The date the work was added to the vault.",
        examples=["2026-11-05"],
        json_schema_extra={"slot_uri": "seeker:capturedOn"},
    )

    @model_validator(mode="after")
    def _cards_are_distinct(self) -> Work:
        seen: set[CardId] = set()
        for card in self.cards:
            if card in seen:
                raise PydanticCustomError(
                    "repeated_card", "card '{card}' is linked more than once", {"card": str(card)}
                )
            seen.add(card)
        return self

    def links(self, card: str) -> bool:
        """True if the work links ``card``."""
        return card in self.cards

    def shared_cards(self, cards: tuple[CardId, ...]) -> tuple[CardId, ...]:
        """The cards in ``cards`` this work also links, in the order given."""
        return tuple(card for card in cards if card in self.cards)
