"""Batch drawing (spec: card-draws) against the seeded decks and fixtures."""

import shutil
from collections import Counter
from pathlib import Path

import pytest
import yaml

from deck_fixtures import deck_body, write_deck
from seeker.decks import DeckDirectory
from seeker.draw.drawer import BatchDrawer
from seeker.draw.errors import DecksChanged, SizeOutOfRange, UnsatisfiableHomeField
from seeker.draw.shapes import DrawShape
from seeker.ontology import CreativeField, DeckSet, DrawBatch

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
SHAPES = {shape.axes for shape in DrawShape.all()}


@pytest.fixture(scope="module")
def seeded() -> DeckSet:
    return DeckDirectory(ROOT / "decks").load()


@pytest.fixture(scope="module")
def drawer(seeded: DeckSet) -> BatchDrawer:
    return BatchDrawer(seeded)


def spread(counts: Counter) -> int:
    return max(counts.values()) - min(counts.values())


# --- shape, balance, no repeats, home field (3.2) ---------------------------


@pytest.mark.parametrize("size", [1, 8, 12, 30])
@pytest.mark.parametrize("seed", [0, 7, 2026])
def test_batch_invariants(seeded: DeckSet, drawer: BatchDrawer, seed: int, size: int) -> None:
    batch = drawer.draw(seed, size)
    assert batch.size == size
    assert [d.position for d in batch.draws] == list(range(1, size + 1))

    for draw in batch.draws:
        assert draw.axes in SHAPES and draw.axes[0] == "constraint"
        for axis, card_id in zip(draw.axes, draw.drawn_cards):
            assert seeded.deck(axis).card(card_id) is not None, f"{card_id} is not a {axis} card"
        assert any(seeded.card(c).lists_field(draw.home_field) for c in draw.drawn_cards)

    assert len(set(batch.card_ids)) == 3 * size

    shapes = Counter(draw.axes for draw in batch.draws)
    if size >= 6:
        assert set(shapes) == SHAPES
    assert max(shapes.values()) - min(shapes.values()) <= 1 if len(shapes) == 6 else max(shapes.values()) == 1

    fields = Counter(draw.home_field for draw in batch.draws)
    if size >= 7:
        assert set(fields) == set(CreativeField)
        assert spread(fields) <= 1
    else:
        assert max(fields.values()) == 1


def test_twelve_draws_use_each_shape_twice_and_balance_fields(drawer: BatchDrawer) -> None:
    batch = drawer.draw(7, 12)
    assert sorted(Counter(d.axes for d in batch.draws).values()) == [2] * 6
    assert sorted(Counter(d.home_field for d in batch.draws).values()) == [1, 1, 2, 2, 2, 2, 2]


def test_eight_draws_shape_split(drawer: BatchDrawer) -> None:
    counts = Counter(d.axes for d in drawer.draw(11, 8).draws)
    assert sorted(counts.values()) == [1, 1, 1, 1, 2, 2]


def test_home_field_comics_is_honored(seeded: DeckSet, drawer: BatchDrawer) -> None:
    comics = [d for d in drawer.draw(7, 30).draws if d.home_field is CreativeField.COMICS]
    assert comics
    for draw in comics:
        assert any("comics" in seeded.card(c).fields for c in draw.drawn_cards)


def test_extra_axis_is_never_drawn(tmp_path: Path) -> None:
    directory = tmp_path / "decks"
    shutil.copytree(ROOT / "decks", directory)
    write_deck(directory, "tuning", deck_body("tuning", {"id": "just-intonation", "name": "just intonation", "fields": ["music"]}))
    batch = BatchDrawer(DeckDirectory(directory).load()).draw(7, 30)
    assert "just-intonation" not in batch.card_ids
    assert not any("tuning" in d.axes for d in batch.draws)


# --- size limits and unsatisfiable home field (3.3) -------------------------


@pytest.mark.parametrize("size", [0, -1, 31])
def test_size_out_of_range_names_capacity(drawer: BatchDrawer, size: int) -> None:
    with pytest.raises(SizeOutOfRange) as exc:
        drawer.draw(7, size)
    assert "1 to 30" in str(exc.value) and "domain" in str(exc.value)


def test_unsatisfiable_home_field(tmp_path: Path) -> None:
    others = [f for f in CreativeField if f is not CreativeField.COMICS]
    directory = tmp_path / "decks"
    directory.mkdir()
    for axis, prefix in (("technique", "t"), ("medium", "m"), ("historical-artifact", "h"), ("constraint", "c")):
        cards = [{"id": f"{prefix}-{i}", "name": f"{prefix} {i}", "fields": [others[i % 6].value]} for i in range(14)]
        if axis == "constraint":
            cards[0]["fields"] = ["comics"]  # the only comics card anywhere
        write_deck(directory, axis, deck_body(axis, *cards))
    write_deck(directory, "domain", deck_body("domain", *({"id": f"d-{i}", "name": f"d {i}"} for i in range(8))))

    with pytest.raises(UnsatisfiableHomeField) as exc:
        BatchDrawer(DeckDirectory(directory).load()).draw(3, 14)
    assert exc.value.field is CreativeField.COMICS
    assert f"draw {exc.value.position}" in str(exc.value) and "'comics'" in str(exc.value)


# --- reproducibility and the golden batch (3.4) -----------------------------


def test_same_inputs_same_batch(seeded: DeckSet) -> None:
    assert BatchDrawer(seeded).draw(7, 12) == BatchDrawer(seeded).draw(7, 12)


def test_different_seed_differs(drawer: BatchDrawer) -> None:
    assert drawer.draw(7, 12).draws != drawer.draw(8, 12).draws


def test_golden_batch() -> None:
    expected = DrawBatch.model_validate(yaml.safe_load((FIXTURES / "golden-batch.yaml").read_text()))
    drawer = BatchDrawer(DeckDirectory(FIXTURES / "golden-decks").load())
    assert drawer.capacity.largest == 7
    assert drawer.draw(expected.seed, expected.size) == expected


# --- replay (3.5) -------------------------------------------------------------


def test_replay_on_unchanged_decks(drawer: BatchDrawer) -> None:
    record = drawer.draw(7, 12)
    assert drawer.replay(record) == record


def test_replay_after_editing_a_card(tmp_path: Path, drawer: BatchDrawer) -> None:
    record = drawer.draw(7, 12)
    directory = tmp_path / "decks"
    shutil.copytree(ROOT / "decks", directory)
    path = directory / "domain.yaml"
    path.write_text(path.read_text().replace("synonyms: [apiculture]", "synonyms: [apiculture, apiary]"))
    edited = BatchDrawer(DeckDirectory(directory).load())
    with pytest.raises(DecksChanged) as exc:
        edited.replay(record)
    assert record.deck_set_digest.short in str(exc.value)
    assert edited.digest.short in str(exc.value)
