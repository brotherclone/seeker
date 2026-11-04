"""Draw shapes and batch capacity (spec: Draw shape, Batch size limits)."""

from pathlib import Path

import pytest

from deck_fixtures import deck_body, valid_directory, write_deck
from seeker.decks import DeckDirectory
from seeker.draw.shapes import CONSTRAINT, DrawCapacity, DrawShape

ROOT = Path(__file__).resolve().parent.parent


def test_six_canonical_shapes_constraint_first() -> None:
    shapes = DrawShape.all()
    assert len(shapes) == 6
    assert len({shape.axes for shape in shapes}) == 6
    assert all(shape.axes[0] == CONSTRAINT for shape in shapes)
    assert shapes[0].axes == ("constraint", "technique", "medium")
    assert shapes[-1].axes == ("constraint", "historical-artifact", "domain")
    assert not any("tuning" in shape.axes for shape in shapes)


def test_seeded_deck_capacity_is_thirty() -> None:
    capacity = DrawCapacity.of(DeckDirectory(ROOT / "decks").load())
    assert (capacity.largest, capacity.limiting_axis) == (30, "domain")


@pytest.mark.parametrize(
    ("axis", "size", "usage"),
    [("constraint", 12, 12), ("domain", 12, 6), ("domain", 8, 5), ("domain", 31, 16), ("medium", 6, 3)],
)
def test_worst_usage(axis: str, size: int, usage: int) -> None:
    assert DrawCapacity.worst_usage(axis, size) == usage


def test_small_fixture_capacity(tmp_path: Path) -> None:
    # Every deck holds 2 cards: constraint caps the batch at 2.
    directory = valid_directory(tmp_path)
    for axis in ("technique", "medium", "historical-artifact", "constraint", "domain"):
        write_deck(
            directory,
            axis,
            deck_body(axis, {"id": f"{axis}-a", "name": "a"}, {"id": f"{axis}-b", "name": "b"}),
        )
    capacity = DrawCapacity.of(DeckDirectory(directory).load())
    assert (capacity.largest, capacity.limiting_axis) == (2, "constraint")
