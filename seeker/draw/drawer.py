"""Drawing balanced, reproducible batches of card triples from a deck set.

A batch is a pure function of (deck set, seed, size). Every random decision
goes through one DrawStream in a fixed order:

1. which shapes get the extra draws of an uneven batch (``permutation(6)``),
2. the order of the shape schedule (``permutation(size)``),
3. the home-field rotation offset (``below(7)``),
4. per draw, in position order: the axis that supplies the home-field card,
   that card, then one card for each remaining axis in ``axes`` order.
"""

from __future__ import annotations

from seeker.decks import DeckSetDigest
from seeker.draw.errors import DecksChanged, ReplayMismatch, SizeOutOfRange, UnsatisfiableHomeField
from seeker.draw.shapes import DrawCapacity, DrawShape
from seeker.draw.stream import DrawStream
from seeker.ontology import AxisId, Card, CreativeField, Deck, DeckSet, Draw, DrawBatch


class AxisPool:
    """The cards of one deck not yet used in the batch being drawn, in deck order."""

    def __init__(self, deck: Deck) -> None:
        self.axis: AxisId = deck.axis
        self.cards: list[Card] = list(deck.cards)

    def listing(self, field: CreativeField) -> list[Card]:
        """Unused cards that explicitly list ``field`` (cross-cutting cards don't)."""
        return [card for card in self.cards if card.lists_field(field)]

    def take(self, card: Card) -> Card:
        self.cards.remove(card)
        return card


class BatchDrawer:
    """Draws batches from one deck set."""

    def __init__(self, deck_set: DeckSet) -> None:
        self.deck_set = deck_set
        self.digest = DeckSetDigest.of(deck_set).sha256
        self.capacity = DrawCapacity.of(deck_set)

    def draw(self, seed: int, size: int) -> DrawBatch:
        """A balanced batch of ``size`` draws for ``seed``."""
        if not 1 <= size <= self.capacity.largest:
            raise SizeOutOfRange(size, self.capacity.largest, self.capacity.limiting_axis)
        stream = DrawStream(seed)
        schedule = self._shape_schedule(stream, size)
        fields = tuple(CreativeField)
        offset = stream.below(len(fields))
        pools = tuple(AxisPool(deck) for deck in self.deck_set.decks)

        draws = tuple(
            self._draw_one(stream, pools, position, shape, fields[(offset + position - 1) % len(fields)])
            for position, shape in enumerate(schedule, start=1)
        )
        return DrawBatch(seed=seed, deck_set_digest=self.digest, draws=draws)

    def replay(self, record: DrawBatch) -> DrawBatch:
        """Redraw ``record`` and check it is unchanged; raise if the decks changed."""
        if record.deck_set_digest != self.digest:
            raise DecksChanged(record.deck_set_digest, self.digest)
        redrawn = self.draw(record.seed, record.size)
        for ours, theirs in zip(redrawn.draws, record.draws):
            if ours != theirs:
                raise ReplayMismatch(theirs.position)
        return redrawn

    # -- internals -------------------------------------------------------------

    @staticmethod
    def _shape_schedule(stream: DrawStream, size: int) -> tuple[DrawShape, ...]:
        shapes = DrawShape.all()
        base, extra = divmod(size, len(shapes))
        lucky = set(stream.permutation(len(shapes))[:extra])
        planned = [shape for index, shape in enumerate(shapes) for _ in range(base + (index in lucky))]
        return tuple(planned[i] for i in stream.permutation(size))

    @staticmethod
    def _draw_one(
        stream: DrawStream,
        pools: tuple[AxisPool, ...],
        position: int,
        shape: DrawShape,
        field: CreativeField,
    ) -> Draw:
        shape_pools = tuple(next(pool for pool in pools if pool.axis == axis) for axis in shape.axes)
        suppliers = [pool for pool in shape_pools if pool.listing(field)]
        if not suppliers:
            raise UnsatisfiableHomeField(position, field)
        supplier = suppliers[stream.below(len(suppliers))]
        candidates = supplier.listing(field)
        chosen = {supplier.axis: supplier.take(candidates[stream.below(len(candidates))])}
        for pool in shape_pools:
            if pool is not supplier:
                chosen[pool.axis] = pool.take(pool.cards[stream.below(len(pool.cards))])
        return Draw(
            position=position,
            axes=shape.axes,
            home_field=field,
            drawn_cards=tuple(chosen[axis].id for axis in shape.axes),
        )
