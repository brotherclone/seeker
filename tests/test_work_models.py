"""Work, WorkKind, CaptureSource, WorkId and Url models."""

from datetime import date

import pytest
from pydantic import ValidationError

from seeker.ontology import CaptureSource, CardId, Url, Work, WorkId, WorkKind


def minimal(**overrides: object) -> Work:
    values: dict[str, object] = {
        "id": "oramics-demo-tape-1962",
        "title": "Oramics demo tape",
        "kind": "recording",
        "captured_by": "gabe",
        "captured_on": "2026-11-05",
    }
    values.update(overrides)
    return Work.model_validate(values)


def test_minimal_work_defaults() -> None:
    work = minimal()
    assert work.cards == () and work.fields == () and work.creators == ()
    assert work.year is None and work.url is None and work.summary is None
    assert work.kind is WorkKind.RECORDING and work.captured_by is CaptureSource.GABE
    assert work.captured_on == date(2026, 11, 5)
    assert isinstance(work.id, WorkId)


def test_cards_are_card_ids() -> None:
    work = minimal(cards=["oramics", "tape"])
    assert all(isinstance(card, CardId) for card in work.cards)
    assert work.links("tape") and not work.links("lumigraph")
    assert work.shared_cards((CardId("lumigraph"), CardId("tape"), CardId("oramics"))) == ("tape", "oramics")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", "Not Kebab"),
        ("title", ""),
        ("year", "soon"),
        ("url", "daphneoram.org"),
        ("kind", "sculpture"),
        ("captured_by", "robot"),
        ("captured_on", "yesterday"),
        ("cards", ["Granular Synthesis"]),
        ("cards", ["tape", "tape"]),
    ],
)
def test_bad_values_are_rejected(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        minimal(**{field: value})


def test_unknown_keys_are_rejected() -> None:
    with pytest.raises(ValidationError):
        minimal(rating=5)


def test_url_accepts_http_and_https() -> None:
    assert minimal(url="http://example.org/x").url == "http://example.org/x"
    assert isinstance(minimal(url="https://example.org").url, Url)


@pytest.mark.parametrize(
    ("stem", "expected"),
    [
        ("Oramics demo tape (1962)", "oramics-demo-tape-1962"),
        ("Brian Eno — Music for Airports", "brian-eno-music-for-airports"),
        ("already-kebab", "already-kebab"),
        ("  !!  ", None),
    ],
)
def test_work_id_from_note_name(stem: str, expected: str | None) -> None:
    assert WorkId.from_note_name(stem) == expected
