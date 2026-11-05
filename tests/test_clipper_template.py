"""The Obsidian Web Clipper template matches the Work ontology."""

import json
from pathlib import Path

from seeker.config import VaultFolders
from seeker.ontology import CaptureSource, Work, WorkKind
from seeker.works.catalog import WorkNotes
from vault_fixtures import ROOT, repo_decks

TEMPLATE = ROOT / "capture" / "seeker-work.clipper.json"


def template() -> object:
    return json.loads(TEMPLATE.read_text(encoding="utf-8"))


def properties() -> list:
    return template()["properties"]


def test_properties_are_type_or_work_slots() -> None:
    names = [prop["name"] for prop in properties()]
    assert len(names) == len(set(names))
    assert set(names) - {"type"} <= set(Work.model_fields) - {"id"}
    assert "id" not in names  # the id comes from the note's file name


def test_path_is_the_default_works_folder() -> None:
    assert template()["path"] == str(VaultFolders().works)
    assert template()["behavior"] == "create"


def test_fixed_values_are_valid_enum_values() -> None:
    fixed = {prop["name"]: prop["value"] for prop in properties()}
    assert fixed["type"] == "work"
    assert WorkKind(fixed["kind"]) is WorkKind.OTHER
    assert CaptureSource(fixed["captured_by"]) is CaptureSource.GABE


def test_a_freshly_clipped_note_validates(tmp_path: Path) -> None:
    """What the Clipper writes for a page with no author, date or description."""
    (tmp_path / "Some page.md").write_text(
        "---\n"
        "type: work\n"
        'title: "Some page"\n'
        "creators:\n"
        "year:\n"
        'url: "https://example.org/some-page"\n'
        "kind: other\n"
        "fields:\n"
        "cards:\n"
        'summary: ""\n'
        "captured_by: gabe\n"
        "captured_on: 2026-11-05\n"
        "---\n"
        "A page about drawn sound.\n"
    )
    report = WorkNotes(folder=tmp_path, deck_set=repo_decks()).load()
    assert report.ok, report.problems
