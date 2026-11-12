"""Card notes synced into the vault."""

from pathlib import Path

from seeker.decks.loader import DeckDirectory
from seeker.works.cards_sync import CardNotes
from seeker.works.note import NoteFile
from vault_fixtures import ROOT, repo_decks


def test_first_sync_creates_one_note_per_card(tmp_path: Path) -> None:
    report = CardNotes(folder=tmp_path).sync(repo_decks())
    assert len(report.created) == 153 and not report.updated and not report.unchanged
    assert len(list(tmp_path.glob("*.md"))) == 153
    note = NoteFile.read(tmp_path / "granular-synthesis.md")
    fm = note.frontmatter
    assert fm.get("type") == "card" and fm.get("card_id") == "granular-synthesis" and fm.get("axis") == "technique"
    assert fm.get("aliases") == ["granular synthesis", "microsound", "grain cloud", "granulation"]
    assert "<!-- seeker:card -->" in note.body and "[[Seeker]]" in note.body


def test_second_sync_writes_nothing(tmp_path: Path) -> None:
    CardNotes(folder=tmp_path).sync(repo_decks())
    stamps = {p: p.stat().st_mtime_ns for p in tmp_path.glob("*.md")}
    report = CardNotes(folder=tmp_path).sync(repo_decks())
    assert report.written == 0 and len(report.unchanged) == 153
    assert {p: p.stat().st_mtime_ns for p in tmp_path.glob("*.md")} == stamps


def edited_decks(tmp_path: Path, old: str, new: str) -> Path:
    decks = tmp_path / "decks"
    decks.mkdir()
    for source in (ROOT / "decks").glob("*.yaml"):
        text = source.read_text().replace(old, new)
        (decks / source.name).write_text(text)
    return decks


def test_resync_keeps_gabes_edits_and_updates_synonyms(tmp_path: Path) -> None:
    vault = tmp_path / "Cards"
    CardNotes(folder=vault).sync(repo_decks())
    path = vault / "granular-synthesis.md"
    text = path.read_text()
    text = text.replace("type: card\n", "type: card\nrating: 4\n") + "\nMy own paragraph about grains.\n"
    path.write_text(text)

    decks = edited_decks(tmp_path, "grain cloud", "grain cloud, sound particles")
    changed = DeckDirectory(decks).load()
    assert changed.card("granular-synthesis").synonyms != repo_decks().card("granular-synthesis").synonyms
    report = CardNotes(folder=vault).sync(changed)
    assert report.updated == ("granular-synthesis",)

    after = NoteFile.read(path)
    assert "sound particles" in after.frontmatter.get("aliases")
    assert after.frontmatter.get("rating") == 4
    assert after.body.endswith("\nMy own paragraph about grains.\n")
    assert "Also known as: microsound, grain cloud, sound particles" in after.body


def test_removed_card_keeps_its_note(tmp_path: Path) -> None:
    vault = tmp_path / "Cards"
    (vault).mkdir()
    orphan = vault / "retired-card.md"
    orphan.write_text("---\ntype: card\ncard_id: retired-card\n---\nStill mine.\n")
    before = orphan.read_text()
    CardNotes(folder=vault).sync(repo_decks())
    assert orphan.read_text() == before


def test_unparseable_card_note_is_skipped_not_overwritten(tmp_path: Path) -> None:
    vault = tmp_path / "Cards"
    vault.mkdir()
    broken = vault / "tape.md"
    broken.write_text("---\naliases: [unclosed\n---\nmine\n")
    report = CardNotes(folder=vault).sync(repo_decks())
    assert report.skipped == ("tape",)
    assert broken.read_text() == "---\naliases: [unclosed\n---\nmine\n"
