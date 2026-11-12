"""NoteFile: frontmatter parsing, surgical edits, managed blocks, atomic saves."""

from pathlib import Path

import pytest

from seeker.works.note import ManagedBlock, NoteFile, NoteFormatError

HAND_WRITTEN = """\
---
# my own comment
title: "Oramics demo tape"
cards:
  - "[[oramics]]"
rating: 5   # out of 5
tags: [listen, archive]
---
Daphne Oram drawing sound on 35mm film. — naïve café ✓

More thoughts.
"""


def note_at(tmp_path: Path, text: str, name: str = "note.md") -> NoteFile:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return NoteFile.read(path)


def test_parses_frontmatter_and_body(tmp_path: Path) -> None:
    note = note_at(tmp_path, HAND_WRITTEN)
    assert note.frontmatter.keys == ("title", "cards", "rating", "tags")
    assert note.frontmatter.get("cards") == ["[[oramics]]"]
    assert note.body.startswith("Daphne Oram")
    assert note.text == HAND_WRITTEN


def test_unchanged_note_is_not_rewritten(tmp_path: Path) -> None:
    note = note_at(tmp_path, HAND_WRITTEN)
    before = note.path.stat().st_mtime_ns
    assert note.save() is False
    assert note.with_value("rating", 5).save() is False
    assert note.path.stat().st_mtime_ns == before


def test_changing_one_key_leaves_every_other_line_alone(tmp_path: Path) -> None:
    note = note_at(tmp_path, HAND_WRITTEN)
    updated = note.with_value("cards", ["[[oramics]]", "[[tape]]"])
    assert updated.save() is True
    text = note.path.read_text(encoding="utf-8")
    assert text == HAND_WRITTEN.replace(
        'cards:\n  - "[[oramics]]"\n', "cards:\n- '[[oramics]]'\n- '[[tape]]'\n"
    )
    assert NoteFile.read(note.path).frontmatter.get("cards") == ["[[oramics]]", "[[tape]]"]


def test_new_key_is_appended(tmp_path: Path) -> None:
    note = note_at(tmp_path, HAND_WRITTEN).with_value("kind", "recording")
    assert note.frontmatter.keys[-1] == "kind"
    assert note.text.endswith("kind: recording\n---\n" + HAND_WRITTEN.split("---\n", 2)[2])


def test_note_without_frontmatter_gets_some(tmp_path: Path) -> None:
    note = note_at(tmp_path, "Just a body.\n").with_value("type", "card")
    assert note.text == "---\ntype: card\n---\nJust a body.\n"


def test_new_note(tmp_path: Path) -> None:
    path = tmp_path / "sub" / "new.md"
    note = NoteFile.read_or_new(path).with_value("type", "card").with_block(ManagedBlock(name="card"), "Hello")
    assert note.save() is True
    assert path.read_text() == "---\ntype: card\n---\n\n<!-- seeker:card -->\nHello\n<!-- /seeker:card -->\n"
    assert not list(path.parent.glob("*.tmp"))


def test_unicode_survives(tmp_path: Path) -> None:
    note = note_at(tmp_path, HAND_WRITTEN).with_value("creators", ["[[Daphne Oram]]", "Délia Derbyshire"])
    note.save()
    reread = NoteFile.read(note.path)
    assert reread.frontmatter.get("creators") == ["[[Daphne Oram]]", "Délia Derbyshire"]
    assert "naïve café ✓" in reread.body


def test_managed_block_is_replaced_in_place(tmp_path: Path) -> None:
    block = ManagedBlock(name="card")
    text = "---\ntype: card\n---\nAbove.\n\n<!-- seeker:card -->\nold\n<!-- /seeker:card -->\n\nMine below.\n"
    note = note_at(tmp_path, text).with_block(block, "new\nlines")
    assert note.body == "Above.\n\n<!-- seeker:card -->\nnew\nlines\n<!-- /seeker:card -->\n\nMine below.\n"


def test_missing_block_goes_on_top(tmp_path: Path) -> None:
    note = note_at(tmp_path, "---\na: 1\n---\nMine.\n").with_block(ManagedBlock(name="card"), "x")
    assert note.body == "\n<!-- seeker:card -->\nx\n<!-- /seeker:card -->\n\nMine.\n"


@pytest.mark.parametrize("bad", ["---\n: : :\n  - [\n---\nbody\n", "---\n- just\n- a list\n---\n"])
def test_bad_frontmatter_raises(tmp_path: Path, bad: str) -> None:
    with pytest.raises(NoteFormatError):
        note_at(tmp_path, bad).frontmatter


def test_unterminated_fence_is_body(tmp_path: Path) -> None:
    note = note_at(tmp_path, "---\nnot closed\n")
    assert not note.has_frontmatter
    assert note.frontmatter.entries == ()


def test_saving_twice_writes_once(tmp_path: Path) -> None:
    note = note_at(tmp_path, HAND_WRITTEN).with_value("rating", 4)
    assert note.save() is True
    stamp = note.path.stat().st_mtime_ns
    assert not note.changed
    assert note.save() is False
    assert note.path.stat().st_mtime_ns == stamp


def test_edits_carry_what_is_on_disk(tmp_path: Path) -> None:
    note = note_at(tmp_path, "---\nrating: 5\n---\nbody\n")
    assert note.with_value("rating", 4).changed
    assert not note.with_value("rating", 4).with_value("rating", 5).changed  # edited back to what's on disk


def test_new_note_saved_twice(tmp_path: Path) -> None:
    note = NoteFile.new(tmp_path / "n.md").with_value("type", "card")
    assert note.save() is True and note.save() is False
