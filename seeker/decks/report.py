"""Validation results for a deck directory: typed errors, not strings."""

from __future__ import annotations

from pathlib import Path

from pydantic import ConfigDict, Field

from seeker.ontology import DeckSet, SeekerModel


class DeckError(SeekerModel):
    """One problem found while validating deck files, located as precisely as
    the problem allows: the file, then the card, then the slot."""

    model_config = ConfigDict(title="DeckError")

    file: Path | None = Field(default=None, description="The deck file, relative to the deck directory's parent.")
    card_id: str | None = Field(
        default=None,
        description="The offending card's id as written, which may itself be invalid.",
    )
    slot: str | None = Field(default=None, description="The slot at fault, such as 'id' or 'synonyms'.")
    message: str = Field(description="What is wrong, in words a person can act on.")

    def __str__(self) -> str:
        location = [str(self.file) if self.file else "decks"]
        if self.card_id is not None:
            location.append(f"card {self.card_id!r}")
        if self.slot is not None:
            location.append(self.slot)
        return f"{': '.join(location)}: {self.message}"


class ValidationReport(SeekerModel):
    """The outcome of validating a deck directory: every error found across all
    files, and the loaded deck set when there were none."""

    model_config = ConfigDict(title="ValidationReport")

    directory: Path = Field(description="The directory that was validated.")
    errors: tuple[DeckError, ...] = Field(default=(), description="Every error, in file order.")
    deck_set: DeckSet | None = Field(default=None, description="The loaded decks, present only when valid.")

    @property
    def ok(self) -> bool:
        return not self.errors and self.deck_set is not None


class DeckValidationFailed(Exception):
    """Raised when a deck directory has errors; carries the full report."""

    def __init__(self, report: ValidationReport) -> None:
        self.report = report
        super().__init__(f"{len(report.errors)} deck error(s) in {report.directory}")
