"""Deterministic content digests for decks and deck sets.

A digest hashes canonical JSON of the validated model (defaults filled in,
keys sorted), so comments, formatting and key order in the YAML never change
it, while any change to a card or to card order always does. Runs record the
set digest next to the git commit they used.
"""

from __future__ import annotations

import hashlib
import json

from pydantic import ConfigDict, Field

from seeker.ontology import AxisId, Deck, DeckSet, SeekerModel, Sha256Digest


def _sha256_of_json(value: object) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class DeckDigest(SeekerModel):
    """The content fingerprint of one deck."""

    model_config = ConfigDict(title="DeckDigest")

    axis: AxisId = Field(description="The axis of the digested deck.")
    card_count: int = Field(ge=1, description="How many cards the deck holds.")
    sha256: Sha256Digest = Field(description="SHA-256 of the deck's canonical JSON.")

    @classmethod
    def of(cls, deck: Deck) -> DeckDigest:
        return cls(
            axis=deck.axis,
            card_count=len(deck),
            sha256=_sha256_of_json(deck.model_dump(mode="json")),
        )

    @property
    def short(self) -> str:
        """The first 12 hex characters, for display."""
        return self.sha256.short


class DeckSetDigest(SeekerModel):
    """The content fingerprint of a whole deck set: a hash over the
    axis-ordered (axis, deck digest) pairs."""

    model_config = ConfigDict(title="DeckSetDigest")

    decks: tuple[DeckDigest, ...] = Field(description="One digest per deck, ordered by axis.")
    sha256: Sha256Digest = Field(description="SHA-256 over the ordered deck digests.")

    @classmethod
    def of(cls, deck_set: DeckSet) -> DeckSetDigest:
        decks = tuple(DeckDigest.of(deck) for deck in deck_set.ordered)
        return cls(
            decks=decks,
            sha256=_sha256_of_json([[str(d.axis), d.sha256] for d in decks]),
        )

    @property
    def card_count(self) -> int:
        return sum(d.card_count for d in self.decks)

    @property
    def short(self) -> str:
        return self.sha256.short

    def for_axis(self, axis: str) -> DeckDigest | None:
        return next((d for d in self.decks if d.axis == axis), None)
