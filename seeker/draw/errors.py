"""Why a draw can fail. Every failure names what the person needs to fix."""

from __future__ import annotations

from seeker.ontology import CreativeField, Sha256Digest


class DrawError(Exception):
    """Base for every draw failure."""


class SizeOutOfRange(DrawError):
    def __init__(self, size: int, capacity: int, limiting_axis: str) -> None:
        self.size = size
        self.capacity = capacity
        super().__init__(
            f"batch size {size} is out of range: these decks support 1 to {capacity} draws "
            f"(limited by the {limiting_axis} deck)"
        )


class UnsatisfiableHomeField(DrawError):
    def __init__(self, position: int, field: CreativeField) -> None:
        self.position = position
        self.field = field
        super().__init__(
            f"draw {position} needs a card listing '{field}', but no unused card on its axes lists it"
        )


class DecksChanged(DrawError):
    def __init__(self, recorded: Sha256Digest, current: Sha256Digest) -> None:
        self.recorded = recorded
        self.current = current
        super().__init__(
            f"decks changed since this batch was drawn: recorded deck-set digest {recorded.short}, "
            f"current {current.short}"
        )


class ReplayMismatch(DrawError):
    def __init__(self, position: int) -> None:
        self.position = position
        super().__init__(
            f"replay differs from the record at draw {position} although the decks are unchanged; "
            "the draw algorithm has changed"
        )
