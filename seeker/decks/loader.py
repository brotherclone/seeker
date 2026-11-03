"""Loading and validating a directory of deck files.

Validation runs in two passes and reports every error from both:

1. each file is parsed strictly and validated as a ``Deck``;
2. set-level rules run across the files: each axis matches its file name, the
   required axes are present, and card ids are unique across decks.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError
from pydantic_core import ErrorDetails

from seeker.decks.report import DeckError, DeckValidationFailed, ValidationReport
from seeker.decks.yaml_source import DeckSource
from seeker.ontology import Deck, DeckSet

ERROR_SLOTS = {
    "duplicate_synonym": "synonyms",
    "duplicate_card_id": "cards",
}


class LoadedDeck:
    """A deck file that passed pass one, kept with the source it came from."""

    def __init__(self, source: DeckSource, deck: Deck) -> None:
        self.source = source
        self.deck = deck


class DeckDirectory:
    """A directory of deck files, one per axis."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def _display(self, source: DeckSource) -> Path:
        return Path(self.path.name) / source.path.name

    def validate(self) -> ValidationReport:
        """Validate every deck file and return all errors at once."""
        if not self.path.is_dir():
            return ValidationReport(
                directory=self.path,
                errors=(DeckError(message=f"deck directory {self.path} does not exist"),),
            )
        sources = DeckSource.in_directory(self.path)
        if not sources:
            return ValidationReport(
                directory=self.path,
                errors=(DeckError(message=f"no deck files ({DeckSource.patterns()}) in {self.path}"),),
            )

        errors: list[DeckError] = []
        loaded: list[LoadedDeck] = []
        for source in sources:
            deck, file_errors = self._load_one(source)
            errors += file_errors
            if deck is not None:
                loaded.append(LoadedDeck(source, deck))

        errors += self._set_errors(sources, loaded)
        if errors:
            return ValidationReport(directory=self.path, errors=tuple(errors))
        return ValidationReport(
            directory=self.path, deck_set=DeckSet(decks=tuple(item.deck for item in loaded))
        )

    def load(self) -> DeckSet:
        """The validated deck set; raises DeckValidationFailed with every error."""
        report = self.validate()
        if not report.ok or report.deck_set is None:
            raise DeckValidationFailed(report)
        return report.deck_set

    # -- pass one -----------------------------------------------------------

    def _load_one(self, source: DeckSource) -> tuple[Deck | None, list[DeckError]]:
        file = self._display(source)
        try:
            raw = source.read()
        except yaml.YAMLError as exc:
            return None, [DeckError(file=file, message=f"invalid YAML: {' '.join(str(exc).split())}")]
        if not isinstance(raw, dict):
            return None, [DeckError(file=file, message="a deck file must be a mapping with axis, name, description and cards")]

        errors: list[DeckError] = []
        declared_axis = raw.get("axis")
        if isinstance(declared_axis, str) and declared_axis != source.axis:
            errors.append(
                DeckError(
                    file=file,
                    slot="axis",
                    message=f"axis {declared_axis!r} does not match file name {source.axis!r}",
                )
            )
        try:
            deck = Deck.model_validate(raw)
        except ValidationError as exc:
            details = exc.errors()
            # pydantic counts only cards that validated toward min_length, so an
            # invalid card would also trip "at least 1 card"; report the card only.
            card_failed = any(len(d["loc"]) > 1 and d["loc"][0] == "cards" for d in details)
            errors += [
                self._from_pydantic(file, raw, d)
                for d in details
                if not (card_failed and tuple(d["loc"]) == ("cards",) and d["type"] == "too_short")
            ]
            return None, errors
        return (None if errors else deck), errors

    @staticmethod
    def _from_pydantic(file: Path, raw: object, error: ErrorDetails) -> DeckError:
        loc = tuple(error["loc"])
        kind = error["type"]
        message = error["msg"]
        bad_input = error.get("input")

        card_id: str | None = None
        slot: str | None = ERROR_SLOTS.get(kind)
        if len(loc) >= 2 and loc[0] == "cards" and isinstance(loc[1], int):
            cards = raw.get("cards") if isinstance(raw, dict) else None
            card = cards[loc[1]] if isinstance(cards, list) and loc[1] < len(cards) else None
            card_id = str(card.get("id")) if isinstance(card, dict) and "id" in card else f"#{loc[1] + 1}"
            rest = loc[2:]
        else:
            rest = loc
        if rest and isinstance(rest[0], str):
            slot = rest[0]

        if kind == "extra_forbidden":
            message = f"unknown slot {slot!r}"
        elif kind == "missing":
            message = f"missing required slot {slot!r}"
        elif kind in ("enum", "string_pattern_mismatch", "string_type", "too_short"):
            message = f"{message} (got {bad_input!r})"
        return DeckError(file=file, card_id=card_id, slot=slot, message=message)

    # -- pass two -----------------------------------------------------------

    def _set_errors(self, sources: tuple[DeckSource, ...], loaded: list[LoadedDeck]) -> list[DeckError]:
        errors = [
            DeckError(
                message=f"axis {axis!r} has more than one deck file: "
                + ", ".join(str(self._display(source)) for source in sources if source.axis == axis)
            )
            for axis in DeckSource.duplicated_axes(sources)
        ]
        errors += [
            DeckError(message=f"missing required axis {axis!r} (expected {self.path.name}/{axis}.yaml or .yml)")
            for axis in DeckSet.missing_axes(source.axis for source in sources)
        ]
        files = {item.deck.axis: self._display(item.source) for item in loaded}
        for shared in DeckSet.shared_card_ids(item.deck for item in loaded):
            where = ", ".join(f"{axis} ({files[axis]})" for axis in shared.axes)
            errors.append(
                DeckError(
                    file=files[shared.axes[0]],
                    card_id=shared.card_id,
                    slot="id",
                    message=f"card id is used in more than one deck: {where}",
                )
            )
        return errors
