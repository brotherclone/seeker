"""The ``Reading``, ``Effort`` and ``RoleName`` enums from schema/seeker.yaml."""

from __future__ import annotations

from seeker.ontology.base import DescribedStrEnum


class Reading(DescribedStrEnum):
    """How freely the generator may interpret the cards it is dealt. Round 1
    reads literally; round 2 varies only this setting."""

    LITERAL = "literal", "Cards mean exactly what they name."
    LOOSE = "loose", "Cards may be taken by their spirit as well as their letter."
    METAPHORICAL = "metaphorical", "Cards may stand for something they evoke rather than what they name."


class Effort(DescribedStrEnum):
    """How much effort a model puts into a response, as the Claude API's
    output_config.effort. Higher effort is more thorough, slower and costlier."""

    LOW = "low", "Quickest and cheapest; minimal deliberation."
    MEDIUM = "medium", "Balanced speed and thoroughness."
    HIGH = "high", "Thorough; the default for creative roles."
    XHIGH = "xhigh", "More thorough than high, at higher cost."
    MAX = "max", "The most thorough the model offers; slowest and costliest."


class RoleName(DescribedStrEnum):
    """The agent roles in Seeker's pipeline. Each role is defined by a YAML file
    in prompts/. The generator states ideas; the critics, advocate and judge
    debate and rank them."""

    GENERATOR = "generator", "Turns one draw into one idea stated as a single sentence."
    PROSECUTOR = "prosecutor", "Argues an idea has been done, citing catalog works and web results."
    SKEPTIC = "skeptic", "Argues an idea cannot be built with Gabe's gear, stack and time."
    TASTE_CRITIC = "taste_critic", "Argues an idea is boring even if it is new and buildable."
    ADVOCATE = "advocate", "Answers every critique and may revise or withdraw the idea."
    JUDGE = "judge", "Compares two debated ideas blind and picks a winner on each axis."
