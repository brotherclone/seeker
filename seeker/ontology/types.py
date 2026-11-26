"""Named scalar types mirroring the ``types`` section of schema/seeker.yaml."""

from __future__ import annotations

import re

from seeker.ontology.base import LinkMLString

KEBAB_CASE = "^[a-z0-9]+(-[a-z0-9]+)*$"
_NON_ALNUM = re.compile("[^a-z0-9]+")


class CardId(LinkMLString):
    """Stable identifier for a card, unique across every deck in a deck set so a
    card id alone identifies a card in run records. Lowercase kebab-case."""

    TYPE_URI = "seeker:CardId"
    PATTERN = KEBAB_CASE
    DESCRIPTION = (
        "Stable identifier for a card, unique across every deck in a deck set so a "
        "card id alone identifies a card in run records. Lowercase kebab-case."
    )
    EXAMPLES = ("granular-synthesis", "ben-day-dots")


class AxisId(LinkMLString):
    """Identifier for an axis of the morphological box. Each deck holds exactly
    one axis, and a deck file is named after its axis. Lowercase kebab-case."""

    TYPE_URI = "seeker:AxisId"
    PATTERN = KEBAB_CASE
    DESCRIPTION = (
        "Identifier for an axis of the morphological box. Each deck holds exactly "
        "one axis, and a deck file is named after its axis. Lowercase kebab-case."
    )
    EXAMPLES = ("technique", "historical-artifact")


class Tag(LinkMLString):
    """Free-form lowercase kebab-case label for grouping or filtering cards,
    outside the controlled creative-field vocabulary."""

    TYPE_URI = "seeker:Tag"
    PATTERN = KEBAB_CASE
    DESCRIPTION = (
        "Free-form lowercase kebab-case label for grouping or filtering cards, "
        "outside the controlled creative-field vocabulary."
    )
    EXAMPLES = ("demoscene",)


class Synonym(LinkMLString):
    """An alternative name a card goes by in some specialist literature."""

    TYPE_URI = "seeker:Synonym"
    PATTERN = "^\\S(.*\\S)?$"
    DESCRIPTION = (
        "An alternative name a card goes by in some specialist literature. Synonyms "
        "drive prior-art query expansion, so they should be the words another "
        "community would actually search for. Non-empty with no leading or "
        "trailing whitespace."
    )
    EXAMPLES = ("microsound",)

    @property
    def folded(self) -> str:
        """Case- and whitespace-insensitive form used for duplicate checks."""
        return " ".join(self.split()).casefold()


class Sha256Digest(LinkMLString):
    """A SHA-256 content digest as 64 lowercase hex characters. Used to pin
    exactly which deck content a draw or run used."""

    TYPE_URI = "seeker:Sha256Digest"
    PATTERN = "^[0-9a-f]{64}$"
    DESCRIPTION = (
        "A SHA-256 content digest as 64 lowercase hex characters. Used to pin "
        "exactly which deck content a draw or run used."
    )
    EXAMPLES = ("41909d46fec8a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a",)
    SHORT_LENGTH = 12

    @property
    def short(self) -> str:
        """The first 12 hex characters, for display."""
        return self[: self.SHORT_LENGTH]


class ModelId(LinkMLString):
    """Identifier of a Claude model as the API names it. Recorded on every
    generation so results can be attributed to the model that produced them."""

    TYPE_URI = "seeker:ModelId"
    PATTERN = "^claude-[a-z0-9-]+$"
    DESCRIPTION = (
        "Identifier of a Claude model as the API names it. Recorded on every "
        "generation so results can be attributed to the model that produced them."
    )
    EXAMPLES = ("claude-opus-5-5",)


class GitCommit(LinkMLString):
    """A full git commit hash, suffixed with -dirty when the working tree had
    uncommitted changes, pinning the code, decks and prompts a run used."""

    TYPE_URI = "seeker:GitCommit"
    PATTERN = "^[0-9a-f]{40}(-dirty)?$"
    DESCRIPTION = (
        "A full git commit hash, suffixed with -dirty when the working tree had "
        "uncommitted changes, pinning the code, decks and prompts a run used."
    )
    EXAMPLES = ("5085562a1b2c3d4e5f60718293a4b5c6d7e8f90a",)

    @property
    def is_dirty(self) -> bool:
        return self.endswith("-dirty")


class WorkId(LinkMLString):
    """Stable identifier for a work, derived from its note's file name reduced
    to lowercase kebab-case, so renaming the note renames the work."""

    TYPE_URI = "seeker:WorkId"
    PATTERN = KEBAB_CASE
    DESCRIPTION = (
        "Stable identifier for a work, derived from its note's file name reduced "
        "to lowercase kebab-case, so renaming the note renames the work."
    )
    EXAMPLES = ("oramics-demo-tape-1962",)

    @classmethod
    def from_note_name(cls, stem: str) -> WorkId | None:
        """The id for a note named ``stem``: lowercase, with every run of
        characters outside [a-z0-9] collapsed to one hyphen. None if nothing
        usable is left."""
        reduced = "-".join(_NON_ALNUM.split(stem.lower())).strip("-")
        return cls(reduced) if reduced else None


class Url(LinkMLString):
    """An absolute http or https web address, such as the page a work was
    captured from."""

    TYPE_URI = "seeker:Url"
    PATTERN = "^https?://\\S+$"
    DESCRIPTION = (
        "An absolute http or https web address, such as the page a work was "
        "captured from."
    )
    EXAMPLES = ("https://daphneoram.org/",)
