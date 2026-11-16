"""What a mutation round will make: every child's draw and lineage, then the carried parents.

A plan is a pure function of the parent run, its generation, the deck set, the
mutation seed and the number of reworkings. Card swaps draw from a SHA-256
counter stream salted ``mutation``, so a plan replays identically.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml
from pydantic import ConfigDict, Field

from seeker.debate.runner import GenerationInput
from seeker.debate.schedule import TournamentStream
from seeker.decks import DeckSetDigest
from seeker.draw.shapes import CONSTRAINT
from seeker.ontology import (
    AxisId,
    Card,
    CardId,
    Debate,
    DebateRun,
    DeckSet,
    Draw,
    DrawBatch,
    Idea,
    Lineage,
    MutationKind,
    MutationOrigin,
    SeekerModel,
    Sha256Digest,
    StopReason,
)

STREAM_SALT = "mutation"


class MutationError(Exception):
    """A mutation cannot be planned or resumed."""


class UnfinishedRun(MutationError):
    def __init__(self, path: str, reason: str) -> None:
        super().__init__(f"cannot mutate {path}: {reason}; finish its tournament first")


class ParentGenerationChanged(MutationError):
    def __init__(self, path: str) -> None:
        super().__init__(f"{path} no longer matches the generation digest its debate run recorded")


class NoReplacement(MutationError):
    def __init__(self, parent: int, axis: str) -> None:
        super().__init__(f"no unused card is left on the {axis} deck to swap into parent {parent}'s draw")


class RunInput(SeekerModel):
    """A debate-run record as mutation reads it: where it is, its bytes' digest, and its content."""

    model_config = ConfigDict(title="RunInput")

    label: str = Field(description="The path recorded as the parent, relative to the repository when inside it.")
    digest: Sha256Digest = Field(description="SHA-256 of the file's bytes.")
    run: DebateRun

    @classmethod
    def read(cls, path: Path, root: Path) -> RunInput:
        data = path.read_bytes()
        resolved = path.resolve()
        label = str(resolved.relative_to(root)) if resolved.is_relative_to(root) else str(resolved)
        run = DebateRun.model_validate(yaml.safe_load(data.decode("utf-8")))
        return cls(label=label, digest=hashlib.sha256(data).hexdigest(), run=run)


class Parent(SeekerModel):
    """One survivor as mutation sees it: its idea, its debate and its draw, at its parent-run position."""

    model_config = ConfigDict(title="Parent")

    idea: Idea
    debate: Debate
    draw: Draw

    @property
    def position(self) -> int:
        return self.idea.position


class PlannedIdea(SeekerModel):
    """One position of a mutated generation: its draw, its lineage and the parent it came from."""

    model_config = ConfigDict(title="PlannedIdea")

    draw: Draw
    lineage: Lineage
    parent: Parent
    attempt: int = Field(default=1, ge=1, description="For a reworking, which of the parent's reworkings this is.")

    @property
    def position(self) -> int:
        return self.draw.position

    @property
    def kind(self) -> MutationKind:
        return self.lineage.mutation_kind

    @property
    def new_card(self) -> CardId | None:
        """The card a swap brought in, or None."""
        if self.lineage.swapped_axis is None:
            return None
        return self.draw.card_for(self.lineage.swapped_axis)


class MutationPlan(SeekerModel):
    """Every position of the next round, children first, then the carried parents."""

    model_config = ConfigDict(title="MutationPlan")

    origin: MutationOrigin
    deck_set_digest: Sha256Digest
    entries: tuple[PlannedIdea, ...]

    @classmethod
    def build(
        cls, parent: RunInput, source: GenerationInput, deck_set: DeckSet, seed: int, reworkings: int
    ) -> MutationPlan:
        run = parent.run
        cls._check_finished(parent)
        if source.digest != run.generation_digest:
            raise ParentGenerationChanged(source.label)
        parents = cls._parents(run, source)
        origin = MutationOrigin(
            parent_run_path=parent.label,
            parent_run_digest=parent.digest,
            mutation_seed=seed,
            round=source.generation.round + 1,
        )
        used = {card for draw in source.generation.draw_batch.draws for card in draw.drawn_cards}
        stream = TournamentStream(seed, STREAM_SALT)
        entries: list[PlannedIdea] = []
        for survivor in parents:
            for attempt in range(1, reworkings + 1):
                entries.append(cls._reworking(survivor, len(entries) + 1, attempt))
            for axis in survivor.draw.axes:
                if axis == CONSTRAINT:
                    continue
                swap = cls._swap(survivor, axis, len(entries) + 1, deck_set, used, stream)
                used.update(swap.draw.drawn_cards)
                entries.append(swap)
        for survivor in parents:
            entries.append(cls._carried(survivor, len(entries) + 1))
        return cls(origin=origin, deck_set_digest=DeckSetDigest.of(deck_set).sha256, entries=tuple(entries))

    # -- views -------------------------------------------------------------------------

    @property
    def batch(self) -> DrawBatch:
        return DrawBatch(
            seed=self.origin.mutation_seed,
            deck_set_digest=self.deck_set_digest,
            draws=tuple(entry.draw for entry in self.entries),
        )

    @property
    def children(self) -> tuple[PlannedIdea, ...]:
        return tuple(e for e in self.entries if e.kind is not MutationKind.CARRIED)

    @property
    def carried(self) -> tuple[PlannedIdea, ...]:
        return tuple(e for e in self.entries if e.kind is MutationKind.CARRIED)

    def entry_at(self, position: int) -> PlannedIdea | None:
        return next((e for e in self.entries if e.position == position), None)

    def siblings_before(self, entry: PlannedIdea) -> tuple[PlannedIdea, ...]:
        """Earlier reworkings of the same parent."""
        return tuple(
            e
            for e in self.entries
            if e.kind is MutationKind.REWORKING
            and e.parent.position == entry.parent.position
            and e.attempt < entry.attempt
        )

    # -- internals ---------------------------------------------------------------------

    @staticmethod
    def _check_finished(parent: RunInput) -> None:
        run = parent.run
        if run.stop_reason is not StopReason.FINISHED or run.tournament is None:
            reason = run.stop_reason.value if run.stop_reason is not None else "still running"
            raise UnfinishedRun(parent.label, f"the run stopped with reason {reason!r}")
        if run.tournament.skipped:
            raise UnfinishedRun(parent.label, "its tournament was skipped")
        if not run.tournament.survivors:
            raise UnfinishedRun(parent.label, "its tournament names no survivors")

    @staticmethod
    def _parents(run: DebateRun, source: GenerationInput) -> tuple[Parent, ...]:
        generation = source.generation
        draws = {draw.position: draw for draw in generation.draw_batch.draws}
        parents = []
        for position in run.tournament.survivors if run.tournament else ():
            idea = generation.idea_at(position)
            debate = run.debate_at(position)
            if idea is None or debate is None:
                raise MutationError(f"survivor {position} has no idea or no debate in the parent records")
            parents.append(Parent(idea=idea, debate=debate, draw=draws[position]))
        return tuple(parents)

    @staticmethod
    def _at(draw: Draw, position: int, cards: tuple[CardId, ...] | None = None) -> Draw:
        return Draw(
            position=position, axes=draw.axes, home_field=draw.home_field, drawn_cards=cards or draw.drawn_cards
        )

    @classmethod
    def _reworking(cls, parent: Parent, position: int, attempt: int) -> PlannedIdea:
        lineage = Lineage(parent_position=parent.position, mutation_kind=MutationKind.REWORKING)
        return PlannedIdea(draw=cls._at(parent.draw, position), lineage=lineage, parent=parent, attempt=attempt)

    @classmethod
    def _carried(cls, parent: Parent, position: int) -> PlannedIdea:
        lineage = Lineage(parent_position=parent.position, mutation_kind=MutationKind.CARRIED)
        return PlannedIdea(draw=cls._at(parent.draw, position), lineage=lineage, parent=parent)

    @classmethod
    def _swap(
        cls,
        parent: Parent,
        axis: AxisId,
        position: int,
        deck_set: DeckSet,
        used: set[CardId],
        stream: TournamentStream,
    ) -> PlannedIdea:
        draw = parent.draw
        replaced = draw.card_for(axis)
        deck = deck_set.deck(axis)
        if replaced is None or deck is None:
            raise MutationError(f"parent {parent.position}'s draw has no {axis} card to swap")
        candidates = [card for card in deck.cards if card.id not in used]
        if cls._only_home_card(draw, replaced, deck_set):
            candidates = [card for card in candidates if card.lists_field(draw.home_field)]
        if not candidates:
            raise NoReplacement(parent.position, axis)
        chosen: Card = candidates[stream.below(len(candidates))]
        cards = tuple(chosen.id if card == replaced else card for card in draw.drawn_cards)
        lineage = Lineage(
            parent_position=parent.position,
            mutation_kind=MutationKind.CARD_SWAP,
            swapped_axis=axis,
            replaced_card=replaced,
        )
        return PlannedIdea(draw=cls._at(draw, position, cards), lineage=lineage, parent=parent)

    @staticmethod
    def _only_home_card(draw: Draw, replaced: CardId, deck_set: DeckSet) -> bool:
        """True when ``replaced`` is the only card of ``draw`` that lists its home field."""
        listing = [
            card_id
            for card_id in draw.drawn_cards
            if (card := deck_set.card(card_id)) is not None and card.lists_field(draw.home_field)
        ]
        return listing == [replaced]
