"""Unit tests for the Draw and DrawBatch ontology models."""

import pytest
from pydantic import TypeAdapter, ValidationError

from seeker.ontology import CardId, CreativeField, Draw, DrawBatch, Sha256Digest

DIGEST = "a" * 64


def draw(position: int = 1, **overrides: object) -> dict:
    return {
        "position": position,
        "axes": ["constraint", "medium", "historical-artifact"],
        "home_field": "comics",
        "drawn_cards": ["wordless", "risograph-print", "screentone"],
        **overrides,
    }


def test_draw_holds_card_references() -> None:
    model = Draw(**draw())
    assert model.home_field is CreativeField.COMICS
    assert all(isinstance(card, CardId) for card in model.drawn_cards)
    assert model.card_for("medium") == "risograph-print"
    assert model.card_for("domain") is None
    assert model.shape == ("constraint", "medium", "historical-artifact")


@pytest.mark.parametrize(
    ("overrides", "kind"),
    [
        ({"position": 0}, "greater_than_equal"),
        ({"axes": ["constraint", "medium"]}, "too_short"),
        ({"drawn_cards": ["a", "b", "c", "d"]}, "too_long"),
        ({"axes": ["constraint", "medium", "medium"]}, "repeated_axis"),
        ({"drawn_cards": ["a", "a", "b"]}, "repeated_card"),
        ({"home_field": "dance"}, "enum"),
    ],
)
def test_draw_bounds(overrides: dict, kind: str) -> None:
    with pytest.raises(ValidationError) as exc:
        Draw(**draw(**overrides))
    assert exc.value.errors()[0]["type"] == kind


def test_batch_properties() -> None:
    batch = DrawBatch(
        seed=7,
        deck_set_digest=DIGEST,
        draws=[draw(1), draw(2, drawn_cards=["one-page", "chapbook", "aaron"])],
    )
    assert batch.size == 2
    assert batch.card_ids[:3] == ("wordless", "risograph-print", "screentone")
    assert isinstance(batch.deck_set_digest, Sha256Digest)
    assert batch.deck_set_digest.short == "a" * 12


@pytest.mark.parametrize(
    "bad",
    [
        {"seed": -1},
        {"deck_set_digest": "A" * 64},
        {"deck_set_digest": "abc"},
        {"draws": []},
        {"draws": [draw(2)]},
        {"draws": [draw(1), draw(1)]},
    ],
)
def test_batch_bounds(bad: dict) -> None:
    fields = {"seed": 7, "deck_set_digest": DIGEST, "draws": [draw(1)], **bad}
    with pytest.raises(ValidationError):
        DrawBatch(**fields)


def test_sha256_digest_type() -> None:
    assert TypeAdapter(Sha256Digest).validate_python(DIGEST) == DIGEST
    with pytest.raises(ValidationError):
        TypeAdapter(Sha256Digest).validate_python("g" * 64)
