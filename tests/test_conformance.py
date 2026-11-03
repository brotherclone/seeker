"""The Pydantic ontology models must mirror schema/seeker.yaml exactly.

The schema is the source of truth. These tests fail on drift in either
direction: a schema class, slot, type or enum value with no matching model
element, or a model element (anything declaring a ``class_uri`` or subclassing
LinkMLString) with no schema counterpart.
"""

import types
import typing
from pathlib import Path

import pytest
from linkml_runtime.utils.schemaview import SchemaView
from pydantic import ConfigDict, Field

import seeker.ontology as ontology
from seeker.ontology import LinkMLString, SeekerModel

SCHEMA = Path(__file__).resolve().parent.parent / "schema" / "seeker.yaml"
VIEW = SchemaView(str(SCHEMA))
PRIMITIVES = {"string": str}


def norm(text: str | None) -> str:
    return " ".join((text or "").split())


def exported(kind: type) -> dict[str, type]:
    return {
        name: obj
        for name in ontology.__all__
        if isinstance(obj := getattr(ontology, name), type) and issubclass(obj, kind) and obj is not kind
    }


def linkml_models() -> dict[str, type[SeekerModel]]:
    """Exported models that claim to mirror a LinkML class."""
    return {
        name: model
        for name, model in exported(SeekerModel).items()
        if "class_uri" in (model.model_config.get("json_schema_extra") or {})
    }


def unwrap(annotation: object) -> tuple[object, bool, bool]:
    """Return (item type, multivalued, optional) for a field annotation."""
    optional = False
    origin = typing.get_origin(annotation)
    if origin in (typing.Union, types.UnionType):
        members = [a for a in typing.get_args(annotation) if a is not type(None)]
        optional = len(members) < len(typing.get_args(annotation))
        (annotation,) = members
        origin = typing.get_origin(annotation)
    if origin is tuple:
        item, ellipsis = typing.get_args(annotation)
        assert ellipsis is Ellipsis
        return item, True, optional
    return annotation, False, optional


def expected_python_type(range_name: str) -> object:
    if range_name in PRIMITIVES:
        return PRIMITIVES[range_name]
    return getattr(ontology, range_name, None)


def class_problems(class_name: str, model: type[SeekerModel]) -> list[str]:
    """Every way ``model`` differs from the schema class ``class_name``."""
    problems: list[str] = []
    cls = VIEW.get_class(class_name)
    extra = model.model_config.get("json_schema_extra") or {}
    if model.model_config.get("title") != class_name:
        problems.append(f"{class_name}: model title {model.model_config.get('title')!r}")
    if extra.get("class_uri") != cls.class_uri:
        problems.append(f"{class_name}: class_uri {extra.get('class_uri')!r} != {cls.class_uri!r}")
    if norm(model.__doc__) != norm(cls.description):
        problems.append(f"{class_name}: docstring differs from class description")

    slot_names = set(VIEW.class_slots(class_name))
    field_names = set(model.model_fields)
    problems += [f"{class_name}: model lacks slot {s!r}" for s in sorted(slot_names - field_names)]
    problems += [f"{class_name}: field {f!r} not in schema" for f in sorted(field_names - slot_names)]

    for slot_name in sorted(slot_names & field_names):
        slot = VIEW.induced_slot(slot_name, class_name)
        field = model.model_fields[slot_name]
        where = f"{class_name}.{slot_name}"
        item, multivalued, optional = unwrap(field.annotation)
        required = bool(slot.required or slot.identifier)
        field_extra = field.json_schema_extra or {}
        if field.is_required() != required:
            problems.append(f"{where}: required {field.is_required()} != {required}")
        if multivalued != bool(slot.multivalued):
            problems.append(f"{where}: multivalued {multivalued} != {bool(slot.multivalued)}")
        if optional and required:
            problems.append(f"{where}: optional annotation on a required slot")
        expected = expected_python_type(slot.range)
        if item is not expected:
            problems.append(f"{where}: type {item!r} != range {slot.range!r}")
        if norm(field.description) != norm(slot.description):
            problems.append(f"{where}: description differs")
        if field.title != slot_name:
            problems.append(f"{where}: title {field.title!r}")
        if field_extra.get("slot_uri") != slot.slot_uri:
            problems.append(f"{where}: slot_uri {field_extra.get('slot_uri')!r} != {slot.slot_uri!r}")
        if bool(field_extra.get("identifier")) != bool(slot.identifier):
            problems.append(f"{where}: identifier flag differs")
        if not field.examples and not issubclass_safe(item, SeekerModel):
            problems.append(f"{where}: no examples")
    return problems


def issubclass_safe(item: object, kind: type) -> bool:
    return isinstance(item, type) and issubclass(item, kind)


def test_every_schema_class_has_a_model_and_back() -> None:
    schema_classes = set(VIEW.all_classes(imports=False))
    assert set(linkml_models()) == schema_classes


@pytest.mark.parametrize("class_name", sorted(VIEW.all_classes(imports=False)))
def test_model_matches_schema_class(class_name: str) -> None:
    assert class_problems(class_name, getattr(ontology, class_name)) == []


def test_every_schema_type_has_a_named_type_and_back() -> None:
    assert set(exported(LinkMLString)) == set(VIEW.all_types(imports=False))


@pytest.mark.parametrize("type_name", sorted(VIEW.all_types(imports=False)))
def test_named_type_matches_schema_type(type_name: str) -> None:
    schema_type = VIEW.get_type(type_name)
    named = getattr(ontology, type_name)
    assert schema_type.typeof == "string"
    assert named.PATTERN == schema_type.pattern
    assert norm(named.DESCRIPTION) == norm(schema_type.description)
    assert named.TYPE_URI == schema_type.uri
    assert [e.value for e in schema_type.examples] == list(named.EXAMPLES)


def test_enums_match_schema() -> None:
    assert set(VIEW.all_enums(imports=False)) == {"CreativeField"}
    enum = VIEW.get_enum("CreativeField")
    assert norm(ontology.CreativeField.__doc__) == norm(enum.description)
    schema_values = {name: norm(pv.description) for name, pv in enum.permissible_values.items()}
    model_values = {member.value: norm(member.description) for member in ontology.CreativeField}
    assert model_values == schema_values


def test_conformance_catches_a_dropped_slot() -> None:
    class Card(SeekerModel):
        """One topic card, the atom of a draw. A draw takes one card from each of
        several decks and asks whether the collision is a real idea."""

        model_config = ConfigDict(title="Card", json_schema_extra={"class_uri": "seeker:Card"})
        id: ontology.CardId = Field(
            title="id",
            description="The card's stable identifier, unique across the deck set.",
            examples=["x"],
            json_schema_extra={"slot_uri": "seeker:id", "identifier": True},
        )

    problems = class_problems("Card", Card)
    assert "Card: model lacks slot 'name'" in problems
    assert "Card: model lacks slot 'synonyms'" in problems


def test_conformance_catches_a_changed_description() -> None:
    drifted = type(
        "Deck",
        (ontology.Deck,),
        {"__doc__": "Something else entirely.", "__module__": __name__},
    )
    assert "Deck: docstring differs from class description" in class_problems("Deck", drifted)
