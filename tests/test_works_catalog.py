"""Loading and validating the works folder; the catalog digest."""

from pathlib import Path

import pytest

from seeker.works.catalog import WorkCatalog, WorkNotes, WorksInvalid
from vault_fixtures import repo_decks, work_note


def notes(folder: Path) -> WorkNotes:
    return WorkNotes(folder=folder, deck_set=repo_decks())


def test_wikilinked_cards_load(tmp_path: Path) -> None:
    work_note(
        tmp_path,
        "Oramics demo tape (1962)",
        cards='["[[oramics]]", "[[tape|a cassette]]"]',
        extra='creators: ["[[Daphne Oram]]"]\nyear: 1962\n',
    )
    report = notes(tmp_path).load()
    assert report.ok, report.problems
    (work,) = report.catalog.works
    assert work.id == "oramics-demo-tape-1962"
    assert work.cards == ("oramics", "tape")
    assert work.creators == ("Daphne Oram",)
    assert work.year == 1962


def test_plain_ids_and_empty_clipper_values(tmp_path: Path) -> None:
    work_note(tmp_path, "clip", cards="[oramics]", extra='year: ""\nurl: ""\nsummary:\nfields: []\ncreators: [""]\n')
    work = notes(tmp_path).catalog().works[0]
    assert work.cards == ("oramics",) and work.year is None and work.url is None and work.creators == ()


def test_non_work_notes_are_skipped(tmp_path: Path) -> None:
    (tmp_path / "loose.md").write_text("No frontmatter at all.\n")
    (tmp_path / "idea.md").write_text("---\ntype: note\ntitle: x\n---\n")
    (tmp_path / "untyped.md").write_text("---\ntitle: x\n---\n")
    work_note(tmp_path / ".trash", "deleted", cards="[[[nope]]]")
    report = notes(tmp_path).load()
    assert report.ok and len(report.catalog) == 0


def test_missing_folder_is_an_empty_catalog(tmp_path: Path) -> None:
    assert len(notes(tmp_path / "absent").catalog()) == 0


def test_unknown_card(tmp_path: Path) -> None:
    work_note(tmp_path, "grainy", cards='["[[granular-synth]]"]')
    (problem,) = notes(tmp_path).load().problems
    assert (problem.note, problem.slot, problem.value) == (Path("grainy.md"), "cards", "granular-synth")
    assert "unknown card" in problem.message


def test_problems_in_two_notes_are_reported_together(tmp_path: Path) -> None:
    work_note(tmp_path, "a", extra="year: soon\n")
    work_note(tmp_path, "b", cards='["[[not-a-card]]"]')
    work_note(tmp_path, "c", cards='["[[tape]]"]')
    report = notes(tmp_path).load()
    assert [(str(p.note), p.slot, p.value) for p in report.problems] == [
        ("a.md", "year", "soon"),
        ("b.md", "cards", "not-a-card"),
    ]
    assert report.catalog is None
    assert [entry.work.id for entry in report.notes] == ["c"]
    with pytest.raises(WorksInvalid):
        notes(tmp_path).catalog()


@pytest.mark.parametrize(
    ("line", "replacement", "slot"),
    [
        ("kind: recording", "kind: sculpture", "kind"),
        ("captured_on: 2026-11-05", "captured_on: soon", "captured_on"),
        ("type: work", "type: work\nurl: not a url", "url"),
    ],
)
def test_invalid_frontmatter_names_the_slot(tmp_path: Path, line: str, replacement: str, slot: str) -> None:
    path = work_note(tmp_path, "w")
    path.write_text(path.read_text().replace(line, replacement))
    assert [p.slot for p in notes(tmp_path).load().problems] == [slot]


def test_personal_properties_are_ignored(tmp_path: Path) -> None:
    work_note(tmp_path, "w", extra="rating: 5\nmood: [late-night]\n")
    assert notes(tmp_path).load().ok


def test_unparseable_note_is_reported_not_raised(tmp_path: Path) -> None:
    (tmp_path / "half-synced.md").write_text("---\ntype: work\ntitle: [unclosed\n---\n")
    (problem,) = notes(tmp_path).load().problems
    assert problem.note == Path("half-synced.md") and "YAML" in problem.message


def test_duplicate_ids(tmp_path: Path) -> None:
    work_note(tmp_path, "Music for Airports")
    work_note(tmp_path / "eno", "music-for-airports")
    (problem,) = notes(tmp_path).load().problems
    assert problem.slot == "id" and problem.value == "music-for-airports"
    assert "duplicate" in problem.message


def test_missing_required_slot(tmp_path: Path) -> None:
    (tmp_path / "bare.md").write_text("---\ntype: work\n---\n")
    slots = sorted(p.slot for p in notes(tmp_path).load().problems)
    assert slots == ["captured_by", "captured_on", "kind", "title"]


class TestDigest:
    def digest(self, folder: Path) -> str:
        return notes(folder).catalog().digest

    def test_stable_and_ignores_body_and_key_order(self, tmp_path: Path) -> None:
        path = work_note(tmp_path, "w", cards='["[[tape]]"]', body="First thoughts.\n")
        first = self.digest(tmp_path)
        assert self.digest(tmp_path) == first
        path.write_text(path.read_text().replace("First thoughts.", "Completely different prose."))
        assert self.digest(tmp_path) == first
        lines = path.read_text().split("\n")
        path.write_text("\n".join([lines[0], *reversed(lines[1:7]), *lines[7:]]))
        assert notes(tmp_path).load().ok
        assert self.digest(tmp_path) == first

    def test_changes_when_cards_change(self, tmp_path: Path) -> None:
        path = work_note(tmp_path, "w", cards='["[[tape]]"]')
        first = self.digest(tmp_path)
        path.write_text(path.read_text().replace('["[[tape]]"]', '["[[tape]]", "[[oramics]]"]'))
        assert self.digest(tmp_path) != first

    def test_empty_catalog_digest(self) -> None:
        assert len(WorkCatalog().digest) == 64
