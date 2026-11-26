"""Card notes: one vault note per deck card, kept in step with the decks.

Seeker owns a fixed set of frontmatter keys and the ``card`` managed block in
each card note. Everything else in the note is Gabe's and survives every
resync. Sync never deletes: a card dropped from the decks keeps its note.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from pydantic import ConfigDict, Field

from seeker.config import VaultLayout
from seeker.ontology import Card, CardId, Deck, DeckSet, SeekerModel
from seeker.works.note import FrontmatterEntry, ManagedBlock, NoteFile, NoteFormatError

CARD_TYPE = "card"
HUB = "Seeker"


class CardNote(SeekerModel):
    """What Seeker writes into one card's note: its owned properties and the
    content of its managed block."""

    model_config = ConfigDict(title="CardNote")

    BLOCK: ClassVar[ManagedBlock] = ManagedBlock(name="card")
    OWNED_KEYS: ClassVar[tuple[str, ...]] = ("type", "card_id", "axis", "fields", "tags", "aliases")

    card: Card = Field(description="The card the note describes.")
    deck: Deck = Field(description="The deck holding the card.")

    @property
    def file_name(self) -> str:
        return f"{self.card.id}.md"

    @property
    def aliases(self) -> list[str]:
        """The name and every synonym, so wikilinks by any of them resolve here."""
        return [str(term) for term in self.card.search_terms]

    @property
    def properties(self) -> tuple[FrontmatterEntry, ...]:
        values = (
            CARD_TYPE,
            str(self.card.id),
            str(self.deck.axis),
            [str(field) for field in self.card.fields],
            [str(tag) for tag in self.card.tags],
            self.aliases,
        )
        return tuple(FrontmatterEntry(key=key, value=value) for key, value in zip(self.OWNED_KEYS, values))

    @property
    def block_content(self) -> str:
        fields = ", ".join(str(field) for field in self.card.fields) or "cross-cutting (every field)"
        lines = [
            f"**{self.card.name}** · {self.deck.name} card (`{self.deck.axis}`) · Back to [[{HUB}]]",
            "",
            f"Fields: {fields}",
        ]
        if self.card.synonyms:
            lines.append(f"Also known as: {', '.join(str(s) for s in self.card.synonyms)}")
        if self.card.tags:
            lines.append(f"Tags: {', '.join('#' + str(tag) for tag in self.card.tags)}")
        if self.card.note:
            lines += ["", self.card.note]
        return "\n".join(lines)

    def applied_to(self, note: NoteFile) -> NoteFile:
        return note.with_values(self.properties).with_block(self.BLOCK, self.block_content)


class CardSyncReport(SeekerModel):
    """What a sync did, card by card."""

    model_config = ConfigDict(title="CardSyncReport")

    folder: Path = Field(description="The cards folder.")
    created: tuple[CardId, ...] = Field(default=(), description="Cards that had no note before.")
    updated: tuple[CardId, ...] = Field(default=(), description="Cards whose note changed.")
    unchanged: tuple[CardId, ...] = Field(default=(), description="Cards whose note was already current.")
    skipped: tuple[CardId, ...] = Field(
        default=(), description="Cards whose note has frontmatter Seeker cannot parse; left untouched."
    )

    @property
    def written(self) -> int:
        return len(self.created) + len(self.updated)


class CardNotes(SeekerModel):
    """The cards folder of a vault."""

    model_config = ConfigDict(title="CardNotes")

    folder: Path = Field(description="Where card notes live.")

    @classmethod
    def of(cls, layout: VaultLayout) -> CardNotes:
        return cls(folder=layout.cards)

    def planned(self, deck_set: DeckSet) -> tuple[CardNote, ...]:
        return tuple(CardNote(card=card, deck=deck) for deck in deck_set.ordered for card in deck.cards)

    def sync(self, deck_set: DeckSet) -> CardSyncReport:
        created: list[CardId] = []
        updated: list[CardId] = []
        unchanged: list[CardId] = []
        skipped: list[CardId] = []
        for card_note in self.planned(deck_set):
            path = self.folder / card_note.file_name
            existed = path.is_file()
            try:
                note = card_note.applied_to(NoteFile.read_or_new(path))
            except NoteFormatError:
                skipped.append(card_note.card.id)
                continue
            if not note.save():
                unchanged.append(card_note.card.id)
            elif existed:
                updated.append(card_note.card.id)
            else:
                created.append(card_note.card.id)
        return CardSyncReport(
            folder=self.folder, created=tuple(created), updated=tuple(updated),
            unchanged=tuple(unchanged),
            skipped=tuple(skipped),
        )
