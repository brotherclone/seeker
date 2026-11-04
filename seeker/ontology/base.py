"""Base classes shared by every model mirroring the Seeker LinkML schema."""

from __future__ import annotations

from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, GetCoreSchemaHandler, GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema, core_schema

SEEKER_PREFIX = "seeker"


class SeekerModel(BaseModel):
    """Base for every class in the Seeker ontology.

    Models are immutable, reject undeclared slots, and trim surrounding
    whitespace from strings. Each subclass mirrors one LinkML class: its
    docstring is the class description and its ``class_uri`` is declared in
    ``model_config``.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        use_enum_values=False,
        validate_default=True,
    )


class LinkMLString(str):
    """A named string type mirroring a LinkML ``type`` with ``typeof: string``.

    Subclasses declare the LinkML type's URI, pattern, description and examples
    as class variables. Values validate against the pattern and remain
    instances of the subclass, so a ``CardId`` is never just a ``str``.
    """

    TYPE_URI: ClassVar[str]
    PATTERN: ClassVar[str]
    DESCRIPTION: ClassVar[str]
    EXAMPLES: ClassVar[tuple[str, ...]] = ()

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: object, handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        return core_schema.no_info_after_validator_function(
            cls,
            core_schema.str_schema(pattern=cls.PATTERN, strip_whitespace=True),
            serialization=core_schema.plain_serializer_function_ser_schema(
                str, return_schema=core_schema.str_schema()
            ),
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls, schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        json_schema = handler(schema)
        json_schema.update(
            title=cls.__name__,
            description=cls.DESCRIPTION,
            examples=list(cls.EXAMPLES),
            type_uri=cls.TYPE_URI,
        )
        return json_schema


class DescribedStrEnum(StrEnum):
    """Base for enums mirroring a LinkML enum. Members are declared as
    ``NAME = "value", "description"`` so every permissible value carries its
    schema description."""

    description: str

    def __new__(cls, value: str, description: str) -> DescribedStrEnum:
        member = str.__new__(cls, value)
        member._value_ = value
        member.description = description
        return member
