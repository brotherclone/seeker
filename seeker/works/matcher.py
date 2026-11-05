"""Suggesting card links for works by finding card names and synonyms in their text.

Matching is local, free and deterministic: whole words, case-insensitive,
with hyphens and spaces inside a term treated alike ("Karplus Strong" finds
Karplus-Strong). Single-word terms of three characters or fewer (FDN, SMF)
match only in their exact case, so they don't fire inside ordinary prose.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import ClassVar

from pydantic import ConfigDict, Field

from seeker.ontology import Card, CardId, DeckSet, SeekerModel, WorkId
from seeker.works.catalog import WorkNote, Wikilink
from seeker.works.note import NoteFile

_SEPARATORS = re.compile(r"[\s\-]+")


class TermPattern(SeekerModel):
    """The compiled search for one card term."""

    model_config = ConfigDict(title="TermPattern", arbitrary_types_allowed=True)

    SHORT_LENGTH: ClassVar[int] = 3

    term: str = Field(description="The name or synonym searched for.")
    pattern: re.Pattern[str] = Field(description="Whole-word regex for the term.")

    @classmethod
    def of(cls, term: str) -> TermPattern:
        words = [re.escape(word) for word in _SEPARATORS.split(term.strip()) if word]
        body = r"[\s\-]+".join(words)
        exact_case = len(words) == 1 and len(term.strip()) <= cls.SHORT_LENGTH
        flags = 0 if exact_case else re.IGNORECASE
        return cls(term=term, pattern=re.compile(rf"(?<!\w){body}(?!\w)", flags))

    def find(self, text: str) -> str | None:
        """The first matching text, as written, or None."""
        match = self.pattern.search(text)
        return match.group(0) if match else None


class CardTerms(SeekerModel):
    """One card's search patterns: its name, then its synonyms."""

    model_config = ConfigDict(title="CardTerms")

    card: CardId = Field(description="The card.")
    patterns: tuple[TermPattern, ...] = Field(description="Name first, then synonyms.")

    def find(self, text: str) -> str | None:
        return next((match for pattern in self.patterns if (match := pattern.find(text)) is not None), None)


class CardSuggestion(SeekerModel):
    """A card a work's text mentions but the work doesn't link yet."""

    model_config = ConfigDict(title="CardSuggestion")

    card: CardId = Field(description="The suggested card.")
    found: str = Field(description="The text that matched, as written in the note.")


class WorkSuggestions(SeekerModel):
    """Every card suggested for one work note."""

    model_config = ConfigDict(title="WorkSuggestions")

    work_id: WorkId = Field(description="The work.")
    note: NoteFile = Field(description="The work's note.")
    suggestions: tuple[CardSuggestion, ...] = Field(default=(), description="In deck order.")

    @property
    def cards(self) -> tuple[CardId, ...]:
        return tuple(suggestion.card for suggestion in self.suggestions)

    @property
    def path(self) -> Path:
        return self.note.path

    def applied(self) -> NoteFile:
        """The note with the suggested cards appended to its ``cards`` property
        as wikilinks. Every other byte of the note is unchanged."""
        if not self.suggestions:
            return self.note
        current = self.note.frontmatter.get("cards")
        existing = current if isinstance(current, list) else ([] if current in (None, "") else [current])
        added = [Wikilink.to(card) for card in self.cards]
        return self.note.with_value("cards", [*existing, *added])

    def apply(self) -> bool:
        """Write the applied note. True when the note changed."""
        return self.applied().save()


class CardMatcher(SeekerModel):
    """Card terms compiled once per deck set, ready to search work text."""

    model_config = ConfigDict(title="CardMatcher")

    cards: tuple[CardTerms, ...] = Field(description="Every card's terms, in deck order.")

    @classmethod
    def of(cls, deck_set: DeckSet) -> CardMatcher:
        cards: tuple[Card, ...] = tuple(card for deck in deck_set.ordered for card in deck.cards)
        return cls(
            cards=tuple(
                CardTerms(card=card.id, patterns=tuple(TermPattern.of(str(term)) for term in card.search_terms))
                for card in cards
            )
        )

    def matches(self, text: str) -> tuple[CardSuggestion, ...]:
        """Every card whose name or a synonym appears in ``text``."""
        found: list[CardSuggestion] = []
        for terms in self.cards:
            hit = terms.find(text)
            if hit is not None:
                found.append(CardSuggestion(card=terms.card, found=hit))
        return tuple(found)

    def suggest(self, entry: WorkNote) -> WorkSuggestions:
        """Cards mentioned in a work's title, summary or body that it doesn't link yet."""
        fresh = tuple(s for s in self.matches(entry.searchable_text) if not entry.work.links(s.card))
        return WorkSuggestions(work_id=entry.work.id, note=entry.note, suggestions=fresh)
