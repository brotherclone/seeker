"""The ``Reading`` and ``RoleName`` enums from schema/seeker.yaml."""

from __future__ import annotations

from seeker.ontology.base import DescribedStrEnum


class Reading(DescribedStrEnum):
    """How freely the generator may interpret the cards it is dealt. Round 1
    reads literally; round 2 varies only this setting."""

    LITERAL = "literal", "Cards mean exactly what they name."
    LOOSE = "loose", "Cards may be taken by their spirit as well as their letter."
    METAPHORICAL = "metaphorical", "Cards may stand for something they evoke rather than what they name."


class RoleName(DescribedStrEnum):
    """The agent roles in Seeker's pipeline. Each role is defined by a YAML file
    in prompts/. Only the generator exists so far; the debate adds the rest."""

    GENERATOR = "generator", "Turns one draw into one idea stated as a single sentence."
