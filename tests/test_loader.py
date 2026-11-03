"""Loading and validating deck directories (spec: card-decks loading and validation)."""

from pathlib import Path

import pytest

from deck_fixtures import deck_body, valid_directory, write_deck
from seeker.decks import DeckDirectory, DeckValidationFailed
from seeker.ontology import CreativeField


def messages(directory: Path) -> list[str]:
    return [str(error) for error in DeckDirectory(directory).validate().errors]


def test_valid_directory_loads(tmp_path: Path) -> None:
    directory = valid_directory(tmp_path)
    write_deck(
        directory,
        "technique",
        deck_body(
            "technique",
            {"id": "granular-synthesis", "name": "granular synthesis", "synonyms": ["microsound"]},
            {"id": "cellular-automata", "name": "cellular automata", "fields": ["music", "games"]},
        ),
    )
    deck_set = DeckDirectory(directory).load()
    technique = deck_set.deck("technique")
    assert technique is not None
    assert technique.card_ids == ("granular-synthesis", "cellular-automata")
    assert deck_set.card("cellular-automata").fields == (CreativeField.MUSIC, CreativeField.GAMES)


def test_extra_axis_loads(tmp_path: Path) -> None:
    directory = valid_directory(tmp_path)
    write_deck(directory, "tuning", deck_body("tuning"))
    assert len(DeckDirectory(directory).load().decks) == 6


def test_axis_does_not_match_file_name(tmp_path: Path) -> None:
    directory = valid_directory(tmp_path)
    write_deck(directory, "medium", deck_body("media"))
    assert messages(directory) == [
        "decks/medium.yaml: axis: axis 'media' does not match file name 'medium'"
    ]


@pytest.mark.parametrize("cards", [[], None])
def test_deck_with_no_cards(tmp_path: Path, cards: list | None) -> None:
    directory = valid_directory(tmp_path)
    body = deck_body("domain")
    if cards is None:
        del body["cards"]
    else:
        body["cards"] = cards
    write_deck(directory, "domain", body)
    (message,) = messages(directory)
    assert message.startswith("decks/domain.yaml: cards: ")


def test_card_id_not_kebab_case(tmp_path: Path) -> None:
    directory = valid_directory(tmp_path)
    write_deck(directory, "technique", deck_body("technique", {"id": "Granular_Synthesis", "name": "g"}))
    (message,) = messages(directory)
    assert message.startswith("decks/technique.yaml: card 'Granular_Synthesis': id: String should match pattern")


def test_unknown_card_slot(tmp_path: Path) -> None:
    directory = valid_directory(tmp_path)
    write_deck(directory, "technique", deck_body("technique", {"id": "fm", "name": "FM", "weight": 2}))
    assert messages(directory) == ["decks/technique.yaml: card 'fm': weight: unknown slot 'weight'"]


def test_unknown_field(tmp_path: Path) -> None:
    directory = valid_directory(tmp_path)
    write_deck(directory, "technique", deck_body("technique", {"id": "tango", "name": "tango", "fields": ["dance"]}))
    (message,) = messages(directory)
    assert message.startswith("decks/technique.yaml: card 'tango': fields: ")
    assert "'dance'" in message


def test_repeated_synonym(tmp_path: Path) -> None:
    directory = valid_directory(tmp_path)
    card = {"id": "granular-synthesis", "name": "granular synthesis", "synonyms": ["Granular Synthesis"]}
    write_deck(directory, "technique", deck_body("technique", card))
    (message,) = messages(directory)
    assert message.startswith("decks/technique.yaml: card 'granular-synthesis': synonyms: ")
    assert "'Granular Synthesis'" in message


def test_duplicate_within_deck(tmp_path: Path) -> None:
    directory = valid_directory(tmp_path)
    card = {"id": "fm-synthesis", "name": "FM synthesis"}
    write_deck(directory, "technique", deck_body("technique", card, card))
    (message,) = messages(directory)
    assert message.startswith("decks/technique.yaml: cards: ")
    assert "'fm-synthesis'" in message


def test_duplicate_across_decks(tmp_path: Path) -> None:
    directory = valid_directory(tmp_path)
    write_deck(directory, "medium", deck_body("medium", {"id": "tape", "name": "tape"}))
    write_deck(directory, "historical-artifact", deck_body("historical-artifact", {"id": "tape", "name": "tape machine"}))
    (message,) = messages(directory)
    assert "card 'tape'" in message
    assert "historical-artifact (decks/historical-artifact.yaml)" in message
    assert "medium (decks/medium.yaml)" in message


def test_missing_required_axis(tmp_path: Path) -> None:
    directory = valid_directory(tmp_path)
    (directory / "constraint.yaml").unlink()
    assert messages(directory) == [
        "decks: missing required axis 'constraint' (expected decks/constraint.yaml or .yml)"
    ]


def test_errors_in_two_files_reported_together(tmp_path: Path) -> None:
    directory = valid_directory(tmp_path)
    write_deck(directory, "technique", deck_body("technique", {"id": "Bad_Id", "name": "bad"}))
    body = deck_body("domain")
    del body["description"]
    write_deck(directory, "domain", body)
    found = messages(directory)
    assert len(found) == 2
    assert found[0] == "decks/domain.yaml: description: missing required slot 'description'"
    assert found[1].startswith("decks/technique.yaml: card 'Bad_Id': id: ")


def test_duplicate_yaml_key(tmp_path: Path) -> None:
    directory = valid_directory(tmp_path)
    write_deck(
        directory,
        "domain",
        "axis: domain\nname: Domain\nname: Domains\ndescription: d\ncards:\n  - {id: tides, name: tide tables}\n",
    )
    (message,) = messages(directory)
    assert message.startswith("decks/domain.yaml: invalid YAML:")
    assert "duplicate key 'name'" in message


def test_non_mapping_file(tmp_path: Path) -> None:
    directory = valid_directory(tmp_path)
    write_deck(directory, "domain", "- just\n- a list\n")
    assert messages(directory) == [
        "decks/domain.yaml: a deck file must be a mapping with axis, name, description and cards"
    ]


def test_missing_directory(tmp_path: Path) -> None:
    assert messages(tmp_path / "nope") == [f"decks: deck directory {tmp_path / 'nope'} does not exist"]


def test_load_raises_with_full_report(tmp_path: Path) -> None:
    directory = valid_directory(tmp_path)
    (directory / "domain.yaml").unlink()
    (directory / "medium.yaml").unlink()
    with pytest.raises(DeckValidationFailed) as exc:
        DeckDirectory(directory).load()
    assert len(exc.value.report.errors) == 2


# --- review follow-ups (PR #1) ---------------------------------------------


def test_yml_files_load(tmp_path: Path) -> None:
    directory = valid_directory(tmp_path)
    technique = directory / "technique.yaml"
    technique.rename(technique.with_suffix(".yml"))
    assert DeckDirectory(directory).load().deck("technique") is not None


def test_empty_directory_message_names_both_suffixes(tmp_path: Path) -> None:
    (tmp_path / "decks").mkdir()
    assert messages(tmp_path / "decks") == [
        f"decks: no deck files (*.yaml or *.yml) in {tmp_path / 'decks'}"
    ]


def test_missing_axis_message_names_both_suffixes(tmp_path: Path) -> None:
    directory = valid_directory(tmp_path)
    (directory / "domain.yaml").unlink()
    assert messages(directory) == [
        "decks: missing required axis 'domain' (expected decks/domain.yaml or .yml)"
    ]


def test_same_axis_in_yaml_and_yml_is_reported_not_raised(tmp_path: Path) -> None:
    directory = valid_directory(tmp_path)
    (directory / "technique.yml").write_text((directory / "technique.yaml").read_text())
    report = DeckDirectory(directory).validate()
    assert not report.ok
    assert [str(e) for e in report.errors] == [
        "decks: axis 'technique' has more than one deck file: decks/technique.yaml, decks/technique.yml"
    ]


def test_unhashable_yaml_key_is_reported_not_raised(tmp_path: Path) -> None:
    directory = valid_directory(tmp_path)
    write_deck(directory, "domain", "? [axis, name]\n: domain\n")
    (message,) = messages(directory)
    assert message.startswith("decks/domain.yaml: invalid YAML:")
    assert "unhashable key" in message
