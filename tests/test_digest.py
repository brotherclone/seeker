"""Deterministic deck and deck-set digests (spec: Deterministic deck digests)."""

from pathlib import Path

from deck_fixtures import deck_body, valid_directory, write_deck
from seeker.decks import DeckDirectory, DeckSetDigest

CARDS = (
    {"id": "granular-synthesis", "name": "granular synthesis", "synonyms": ["microsound"]},
    {"id": "slit-scan", "name": "slit-scan", "fields": ["film"]},
)


def digest_of(directory: Path) -> DeckSetDigest:
    return DeckSetDigest.of(DeckDirectory(directory).load())


def build(tmp_path: Path, technique: dict | str) -> Path:
    directory = valid_directory(tmp_path)
    write_deck(directory, "technique", technique)
    return directory


def test_digests_are_hex_and_stable(tmp_path: Path) -> None:
    directory = build(tmp_path, deck_body("technique", *CARDS))
    first, second = digest_of(directory), digest_of(directory)
    assert first == second
    assert len(first.sha256) == 64 and len(first.short) == 12
    assert [d.axis for d in first.decks] == sorted(d.axis for d in first.decks)
    assert first.for_axis("technique").card_count == 2


def test_reformatting_and_key_order_leave_digest_unchanged(tmp_path: Path) -> None:
    plain = digest_of(build(tmp_path / "a", deck_body("technique", *CARDS)))
    reformatted = digest_of(
        build(
            tmp_path / "b",
            "# reordered keys, comments, flow style and explicit defaults\n"
            "cards:\n"
            "  - {name: granular synthesis,   id: granular-synthesis, synonyms: [microsound], tags: []}\n"
            "  - fields: [film]   # moving image\n"
            "    name: slit-scan\n"
            "    id: slit-scan\n"
            "    note: null\n"
            "description: The technique axis.\n"
            "name: Technique\n"
            "axis: technique\n",
        )
    )
    assert reformatted.sha256 == plain.sha256
    assert reformatted.for_axis("technique") == plain.for_axis("technique")


def test_editing_a_card_changes_only_its_deck_and_the_set(tmp_path: Path) -> None:
    before = digest_of(build(tmp_path / "a", deck_body("technique", *CARDS)))
    edited = ({**CARDS[0], "synonyms": ["microsound", "grain cloud"]}, CARDS[1])
    after = digest_of(build(tmp_path / "b", deck_body("technique", *edited)))
    assert after.sha256 != before.sha256
    assert after.for_axis("technique").sha256 != before.for_axis("technique").sha256
    for deck in before.decks:
        if deck.axis != "technique":
            assert after.for_axis(deck.axis) == deck


def test_reordering_cards_changes_the_digest(tmp_path: Path) -> None:
    forward = digest_of(build(tmp_path / "a", deck_body("technique", *CARDS)))
    reversed_ = digest_of(build(tmp_path / "b", deck_body("technique", *reversed(CARDS))))
    assert forward.for_axis("technique").sha256 != reversed_.for_axis("technique").sha256
    assert forward.sha256 != reversed_.sha256


def test_moving_a_deck_directory_does_not_change_the_digest(tmp_path: Path) -> None:
    here = digest_of(build(tmp_path / "a", deck_body("technique", *CARDS)))
    there = digest_of(build(tmp_path / "b", deck_body("technique", *CARDS)))
    assert here == there
