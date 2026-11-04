"""Unit tests for the ontology models: named types, CreativeField, Card, Deck, DeckSet."""

import pytest
from pydantic import TypeAdapter, ValidationError

from seeker.ontology import (
    AxisId,
    Card,
    CardId,
    CreativeField,
    Deck,
    DeckSet,
    Synonym,
    Tag,
)


def error_types(exc: ValidationError) -> list[tuple[tuple[object, ...], str]]:
    return [(tuple(e["loc"]), e["type"]) for e in exc.errors()]


# --- 3.1 named types and CreativeField -------------------------------------


@pytest.mark.parametrize("named_type", [CardId, AxisId, Tag])
@pytest.mark.parametrize("value", ["granular-synthesis", "fm", "tms5100", "a-1-b"])
def test_kebab_types_accept_kebab_case(named_type: type, value: str) -> None:
    validated = TypeAdapter(named_type).validate_python(value)
    assert validated == value
    assert type(validated) is named_type


@pytest.mark.parametrize("named_type", [CardId, AxisId, Tag])
@pytest.mark.parametrize("value", ["Granular_Synthesis", "granular synthesis", "-fm", "fm-", "a--b", ""])
def test_kebab_types_reject_other_shapes(named_type: type, value: str) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(named_type).validate_python(value)


@pytest.mark.parametrize("value", ["microsound", "grain cloud", "TMS5100"])
def test_synonym_accepts_trimmed_text(value: str) -> None:
    assert TypeAdapter(Synonym).validate_python(value) == value


def test_synonym_strips_whitespace_and_rejects_empty() -> None:
    assert TypeAdapter(Synonym).validate_python("  microsound ") == "microsound"
    with pytest.raises(ValidationError):
        TypeAdapter(Synonym).validate_python("   ")


def test_named_types_carry_linkml_metadata() -> None:
    schema = TypeAdapter(CardId).json_schema()
    assert schema["title"] == "CardId"
    assert schema["type_uri"] == "seeker:CardId"
    assert schema["pattern"] == CardId.PATTERN
    assert "granular-synthesis" in schema["examples"]


def test_creative_field_values_and_descriptions() -> None:
    assert [f.value for f in CreativeField] == [
        "music",
        "visual-art",
        "film",
        "electronics",
        "writing",
        "comics",
        "games",
    ]
    assert CreativeField("visual-art") is CreativeField.VISUAL_ART
    assert all(f.description for f in CreativeField)
    assert CreativeField.GAMES == "games"


# --- 3.2 Card, Deck, DeckSet ------------------------------------------------


def test_minimal_card() -> None:
    card = Card(id="granular-synthesis", name="granular synthesis")
    assert card.synonyms == () and card.fields == () and card.tags == ()
    assert card.note is None
    assert isinstance(card.id, CardId)


def test_card_id_not_kebab_case() -> None:
    with pytest.raises(ValidationError) as exc:
        Card(id="Granular_Synthesis", name="granular synthesis")
    assert error_types(exc.value) == [(("id",), "string_pattern_mismatch")]


def test_unknown_card_slot() -> None:
    with pytest.raises(ValidationError) as exc:
        Card(id="fm-synthesis", name="FM synthesis", weight=3)
    assert error_types(exc.value) == [(("weight",), "extra_forbidden")]


def test_unknown_field() -> None:
    with pytest.raises(ValidationError) as exc:
        Card(id="tango", name="tango", fields=["dance"])
    assert error_types(exc.value) == [(("fields", 0), "enum")]


def test_card_in_several_fields() -> None:
    card = Card(
        id="cellular-automata",
        name="cellular automata",
        fields=["music", "visual-art", "games"],
    )
    assert card.fields == (CreativeField.MUSIC, CreativeField.VISUAL_ART, CreativeField.GAMES)
    assert card.in_field(CreativeField.GAMES)
    assert not card.in_field(CreativeField.FILM)


def test_cross_cutting_card_is_in_every_field() -> None:
    card = Card(id="mono", name="mono")
    assert card.is_cross_cutting
    assert all(card.in_field(f) for f in CreativeField)
    assert not any(card.lists_field(f) for f in CreativeField)


@pytest.mark.parametrize(
    "synonyms",
    [["Granular Synthesis"], ["  granular   synthesis "], ["microsound", "MICROSOUND"]],
)
def test_repeated_synonym(synonyms: list[str]) -> None:
    with pytest.raises(ValidationError) as exc:
        Card(id="granular-synthesis", name="granular synthesis", synonyms=synonyms)
    assert error_types(exc.value) == [((), "duplicate_synonym")]


def test_card_matches_name_and_synonyms() -> None:
    card = Card(id="oramics", name="Oramics", synonyms=["drawn sound"])
    assert card.matches("oramics")
    assert card.matches("Drawn  Sound")
    assert not card.matches("optical sound")
    assert card.search_terms == ("Oramics", "drawn sound")


def test_cards_are_immutable() -> None:
    card = Card(id="fm-synthesis", name="FM synthesis")
    with pytest.raises(ValidationError):
        card.name = "frequency modulation"


def _deck(axis: str, *card_ids: str) -> Deck:
    return Deck(
        axis=axis,
        name=axis.title(),
        description=f"The {axis} axis.",
        cards=[{"id": card_id, "name": card_id.replace("-", " ")} for card_id in card_ids],
    )


def test_deck_lookup_and_fields() -> None:
    deck = Deck(
        axis="technique",
        name="Technique",
        description="How something is made.",
        cards=[
            {"id": "cellular-automata", "name": "cellular automata", "fields": ["music", "games"]},
            {"id": "slit-scan", "name": "slit-scan", "fields": ["film"]},
            {"id": "mono", "name": "mono"},
        ],
    )
    assert len(deck) == 3
    assert deck.card("slit-scan").name == "slit-scan"
    assert deck.card("nope") is None
    assert [c.id for c in deck.by_field(CreativeField.FILM)] == ["slit-scan", "mono"]
    assert [c.id for c in deck.listing(CreativeField.FILM)] == ["slit-scan"]


def test_deck_needs_cards() -> None:
    with pytest.raises(ValidationError) as exc:
        Deck(axis="technique", name="Technique", description="d", cards=[])
    assert error_types(exc.value) == [(("cards",), "too_short")]


def test_duplicate_card_within_deck() -> None:
    with pytest.raises(ValidationError) as exc:
        _deck("technique", "fm-synthesis", "fm-synthesis")
    assert "'fm-synthesis'" in exc.value.errors()[0]["msg"]
    assert error_types(exc.value) == [((), "duplicate_card_id")]


REQUIRED = ("technique", "medium", "historical-artifact", "constraint", "domain")


def _required_decks() -> list[Deck]:
    return [_deck(axis, f"{axis}-card") for axis in REQUIRED]


def test_deck_set_lookup() -> None:
    deck_set = DeckSet(decks=_required_decks())
    assert deck_set.axes == tuple(sorted(REQUIRED))
    assert deck_set.deck("medium").axis == "medium"
    assert deck_set.card("domain-card").id == "domain-card"
    assert deck_set.card("nope") is None


def test_deck_set_allows_extra_axis() -> None:
    deck_set = DeckSet(decks=[*_required_decks(), _deck("tuning", "just-intonation")])
    assert len(deck_set.decks) == 6


def test_deck_set_missing_axis() -> None:
    decks = [d for d in _required_decks() if d.axis != "constraint"]
    with pytest.raises(ValidationError) as exc:
        DeckSet(decks=decks)
    assert "constraint" in exc.value.errors()[0]["msg"]
    assert DeckSet.missing_axes(d.axis for d in decks) == ("constraint",)


def test_deck_set_shared_card_id() -> None:
    decks = [*_required_decks()[:-1], _deck("domain", "tape"), _deck("tuning", "tape")]
    with pytest.raises(ValidationError) as exc:
        DeckSet(decks=decks)
    assert error_types(exc.value) == [((), "shared_card_id")]
    shared = DeckSet.shared_card_ids(decks)
    assert [(s.card_id, s.axes) for s in shared] == [("tape", ("domain", "tuning"))]
