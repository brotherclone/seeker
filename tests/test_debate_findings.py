"""Caching prosecutor finds as works (debate-ideas task 6.4)."""

from datetime import date
from pathlib import Path

import pytest

from seeker.debate.findings import NormalUrl, NoteName, ProsecutorFindings
from seeker.ontology import CaptureSource, Citation, Critique, CritiqueTarget, RoleName, Severity, Usage
from seeker.works.catalog import WorkNotes
from vault_fixtures import repo_decks, work_note

TODAY = date(2026, 11, 12)
USAGE = Usage(input_tokens=1, output_tokens=1, cache_read_tokens=0, cache_write_tokens=0)


def prosecution(*citations: Citation) -> Critique:
    return Critique(
        role_name=RoleName.PROSECUTOR,
        model="claude-sonnet-5-5",
        target=CritiqueTarget.SUBJECT,
        severity=Severity.SERIOUS,
        failure="A 2019 NIME paper already drives grain density from audience speech in a hall.",
        argument="Close neighbour.",
        citations=citations,
        usage=USAGE,
    )


def web(url: str, title: str = "Congregational Sampler", cards: tuple[str, ...] = ("granular-synthesis",)) -> Citation:
    return Citation(title=title, url=url, relevance="Speech-driven grains in a hall.", embodied_cards=cards)


def works(folder: Path) -> WorkNotes:
    return WorkNotes(folder=folder, deck_set=repo_decks())


def test_new_finding_becomes_a_valid_prosecutor_work(tmp_path: Path) -> None:
    found = ProsecutorFindings.capture(prosecution(web("https://nime.org/p/42")), works(tmp_path), TODAY)
    (captured,) = found.captured
    assert captured.path == tmp_path / "Congregational Sampler.md"
    work = works(tmp_path).catalog().work(captured.work_id)
    assert work.captured_by is CaptureSource.PROSECUTOR and work.captured_on == TODAY
    assert str(work.url) == "https://nime.org/p/42" and work.cards == ("granular-synthesis",)
    assert work.kind.value == "other" and work.summary == "Speech-driven grains in a hall."
    assert found.critique.citations[0].url == "https://nime.org/p/42"


def test_known_url_writes_nothing_and_cites_the_work(tmp_path: Path) -> None:
    work_note(tmp_path, "Sampler paper", extra="url: https://NIME.org/p/42/?utm_source=x\n")
    before = {p: p.read_bytes() for p in tmp_path.iterdir()}
    found = ProsecutorFindings.capture(prosecution(web("https://nime.org/p/42")), works(tmp_path), TODAY)
    assert found.captured == ()
    (citation,) = found.critique.citations
    assert citation.cited_work == "sampler-paper" and citation.url is None
    assert {p: p.read_bytes() for p in tmp_path.iterdir()} == before


def test_taken_name_gets_a_suffix_and_existing_notes_are_untouched(tmp_path: Path) -> None:
    existing = work_note(tmp_path, "Congregational Sampler", extra="url: https://other.org/a\n")
    original = existing.read_bytes()
    found = ProsecutorFindings.capture(prosecution(web("https://nime.org/p/42")), works(tmp_path), TODAY)
    assert found.captured[0].path.name == "Congregational Sampler (2).md"
    assert found.captured[0].work_id == "congregational-sampler-2"
    assert existing.read_bytes() == original
    assert len(works(tmp_path).catalog()) == 2


def test_same_url_twice_in_one_critique_is_captured_once(tmp_path: Path) -> None:
    found = ProsecutorFindings.capture(
        prosecution(web("https://nime.org/p/42"), web("https://nime.org/p/42/", title="Same page")), works(tmp_path), TODAY
    )
    assert len(found.captured) == 1
    assert found.critique.citations[1].cited_work == found.captured[0].work_id


def test_catalog_citations_pass_through(tmp_path: Path) -> None:
    work_note(tmp_path, "Oramics tape")
    catalog_cite = Citation(title="Oramics tape", cited_work="oramics-tape", relevance="r")
    found = ProsecutorFindings.capture(prosecution(catalog_cite), works(tmp_path), TODAY)
    assert found.captured == () and found.critique.citations == (catalog_cite,)


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("https://NIME.org/p/42/", "https://nime.org/p/42"),
        ("https://nime.org/p/42?utm_source=x&id=3", "https://nime.org/p/42?id=3"),
        ("https://nime.org/p/42#section", "https://nime.org/p/42"),
    ],
)
def test_url_normalisation(a: str, b: str) -> None:
    assert NormalUrl(a) == NormalUrl(b)


def test_note_names_are_file_safe() -> None:
    assert NoteName('Sound: "drawn" / on [film]?').stem == "Sound drawn on film"
    assert NoteName("///").stem == "Untitled work"
