"""Card suggestions from a work's text, and applying them to the note."""

from pathlib import Path

import pytest

from seeker.decks.loader import DeckDirectory
from seeker.works.catalog import WorkNotes
from seeker.works.matcher import CardMatcher, TermPattern
from seeker.works.note import NoteFile
from vault_fixtures import repo_decks, work_note
from deck_fixtures import deck_body, valid_directory, write_deck


@pytest.fixture(scope="module")
def matcher() -> CardMatcher:
    return CardMatcher.of(repo_decks())


def suggestions_for(folder: Path, matcher: CardMatcher) -> dict[str, tuple[str, ...]]:
    report = WorkNotes(folder=folder, deck_set=repo_decks()).load()
    assert report.ok, report.problems
    return {str(entry.work.id): matcher.suggest(entry).cards for entry in report.notes}


def test_synonym_in_the_body(tmp_path: Path, matcher: CardMatcher) -> None:
    work_note(tmp_path, "demo", body="Daphne Oram's experiments in Drawn Sound, recorded to tape.\n")
    assert "oramics" in suggestions_for(tmp_path, matcher)["demo"]


def test_hyphens_and_spaces_are_interchangeable(matcher: CardMatcher) -> None:
    cards = [s.card for s in matcher.matches("A Karplus Strong string, plus karplus-strong again.")]
    assert "karplus-strong" in cards
    assert [s.found for s in matcher.matches("Karplus-Strong") if s.card == "karplus-strong"] == ["Karplus-Strong"]


def test_whole_words_only(matcher: CardMatcher) -> None:
    assert "tape" not in [s.card for s in matcher.matches("A reading of the tapestry.")]
    assert "zine" not in [s.card for s in matcher.matches("A magazine feature.")]


def test_short_terms_need_exact_case() -> None:
    assert TermPattern.of("CA").find("The ca. 1960 recordings, the CAD files") is None
    assert TermPattern.of("CA").find("A 1D CA rule") == "CA"
    assert TermPattern.of("FDN").find("an fdn reverb") is None
    assert TermPattern.of("riso").find("Printed on a RISO") == "RISO"


def test_short_synonym_on_a_real_card(tmp_path: Path) -> None:
    decks = valid_directory(tmp_path)
    write_deck(decks, "technique", deck_body("technique", {"id": "cellular-automata", "name": "cellular automata", "synonyms": ["CA"]}))
    matcher = CardMatcher.of(DeckDirectory(decks).load())
    assert [s.card for s in matcher.matches("ca. 1970, the decade of CAD")] == []
    assert [s.card for s in matcher.matches("an elementary CA, rule 110")] == ["cellular-automata"]


def test_already_linked_cards_are_skipped(tmp_path: Path, matcher: CardMatcher) -> None:
    work_note(tmp_path, "demo", cards='["[[oramics]]"]', body="Oramics and drawn sound on cassette tape.\n")
    assert suggestions_for(tmp_path, matcher)["demo"] == ("tape",)


def test_title_and_summary_are_searched(tmp_path: Path, matcher: CardMatcher) -> None:
    work_note(tmp_path, "w", title="Microsound", extra="summary: A webcomic.\n")
    assert set(suggestions_for(tmp_path, matcher)["w"]) == {"granular-synthesis", "webcomic"}


def test_apply_adds_wikilinks_and_keeps_everything_else(tmp_path: Path, matcher: CardMatcher) -> None:
    path = tmp_path / "demo.md"
    original = (
        "---\n"
        "type: work\n"
        "title: Oramics demo  # hand comment\n"
        "cards:\n"
        '  - "[[oramics]]"\n'
        "kind: recording\n"
        "rating: 5\n"
        "captured_by: gabe\n"
        "captured_on: 2026-11-05\n"
        "---\n"
        "Drawn sound, then a cassette tape copy. naïve ✓\n"
    )
    path.write_text(original, encoding="utf-8")
    (entry,) = WorkNotes(folder=tmp_path, deck_set=repo_decks()).load().notes
    suggestions = matcher.suggest(entry)
    assert suggestions.cards == ("tape",)
    assert suggestions.apply() is True
    expected = original.replace("cards:\n  - \"[[oramics]]\"\n", "cards:\n- '[[oramics]]'\n- '[[tape]]'\n")
    assert path.read_text(encoding="utf-8") == expected
    (again,) = WorkNotes(folder=tmp_path, deck_set=repo_decks()).load().notes
    assert again.work.cards == ("oramics", "tape")
    assert matcher.suggest(again).apply() is False


def test_apply_to_an_empty_clipper_cards_value(tmp_path: Path, matcher: CardMatcher) -> None:
    path = work_note(tmp_path, "clip", cards='""', body="Grain cloud textures.\n")
    (entry,) = WorkNotes(folder=tmp_path, deck_set=repo_decks()).load().notes
    matcher.suggest(entry).apply()
    assert NoteFile.read(path).frontmatter.get("cards") == ["[[granular-synthesis]]"]
