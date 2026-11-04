"""The generator's answer before it becomes an Idea, and how it is checked."""

from __future__ import annotations

import json
import re
from typing import ClassVar

from pydantic import ConfigDict, Field, ValidationError

from seeker.models import OutputSpec
from seeker.ontology import CardReading, Draw, Idea, SeekerModel, Usage


class DraftProblem(SeekerModel):
    """One reason a draft is not acceptable, phrased so the model can fix it."""

    model_config = ConfigDict(title="DraftProblem")

    field: str = Field(description="Which part of the draft is wrong.")
    message: str = Field(description="What is wrong and how to fix it.")

    def __str__(self) -> str:
        return f"{self.field}: {self.message}"

    @classmethod
    def from_validation(cls, error: ValidationError) -> tuple[DraftProblem, ...]:
        return tuple(
            cls(field=".".join(str(p) for p in detail["loc"]) or "input", message=detail["msg"])
            for detail in error.errors()
        )

    @staticmethod
    def feedback(problems: tuple[DraftProblem, ...]) -> str:
        bullet_list = "\n".join(f"- {problem}" for problem in problems)
        return f"That answer was rejected:\n{bullet_list}\nAnswer again with one corrected idea as the JSON object."


class StrictSchema:
    """A JSON Schema reduced to what strict structured output accepts.

    Pydantic schemas carry titles, examples, patterns, length bounds and $refs.
    Structured output wants plain types with every property required and no
    extra properties, so this keeps only ``type``, ``properties``, ``required``,
    ``items``, ``enum`` and ``description``, inlines ``$defs``, and closes every
    object. Patterns and counts are still enforced locally by Pydantic and
    ``problems_for``.
    """

    KEPT: ClassVar[frozenset[str]] = frozenset({"type", "properties", "items", "enum", "description"})

    def __init__(self, pydantic_schema: object) -> None:
        self.source = pydantic_schema
        self.definitions = getattr(pydantic_schema, "get", lambda _k, d=None: d)("$defs", {})

    def json(self) -> str:
        return json.dumps(self._clean(self.source), sort_keys=True)

    def _clean(self, node: object) -> object:
        if isinstance(node, list):
            return [self._clean(item) for item in node]
        if not hasattr(node, "items"):
            return node
        reference = node.get("$ref")
        if isinstance(reference, str):
            return self._clean(self.definitions[reference.rsplit("/", 1)[-1]])
        cleaned = {key: self._clean(value) for key, value in node.items() if key in self.KEPT}
        if "properties" in node:
            cleaned["properties"] = {name: self._clean(value) for name, value in node["properties"].items()}
            cleaned["required"] = sorted(node["properties"])
            cleaned["additionalProperties"] = False
            cleaned.setdefault("type", "object")
        return cleaned


class Sentence:
    """Heuristic single-sentence and length checks for an idea statement."""

    MAX_WORDS: ClassVar[int] = 60
    ABBREVIATIONS: ClassVar[frozenset[str]] = frozenset(
        {"e.g", "i.e", "etc", "vs", "cf", "dr", "mr", "mrs", "ms", "st", "no", "approx", "ca", "fig", "vol"}
    )
    BOUNDARY: ClassVar[re.Pattern[str]] = re.compile(r"([^\s]*?)[.!?][\"'”’)\]]*\s+(?=\S)")

    def __init__(self, text: str) -> None:
        self.text = " ".join(text.split())

    @property
    def words(self) -> int:
        return len(self.text.split())

    def boundaries(self) -> int:
        """Sentence breaks inside the text, ignoring abbreviations and initials."""
        count = 0
        for match in self.BOUNDARY.finditer(self.text):
            word = match.group(1).lower().rstrip(".")
            is_initial = len(word) == 1 and word.isalpha()
            if word in self.ABBREVIATIONS or is_initial:
                continue
            count += 1
        return count


class IdeaDraft(SeekerModel):
    """An idea as the model submits it: the statement, its X/Y/Z parts and a
    reading of each card. Position and usage are known locally and added later."""

    model_config = ConfigDict(title="IdeaDraft")

    statement: str = Field(
        min_length=1,
        description='The idea as ONE sentence of the form "a/an X that does Y because Z", at most 60 words.',
    )
    subject: str = Field(min_length=1, description="X: the thing being made.")
    behavior: str = Field(min_length=1, description="Y: what it does.")
    rationale: str = Field(min_length=1, description="Z: why it works or matters. A real reason, not a restatement.")
    card_readings: tuple[CardReading, ...] = Field(
        min_length=3,
        max_length=3,
        description="One reading per drawn card, in the order the card ids were given.",
    )

    @classmethod
    def output_spec(cls) -> OutputSpec:
        return OutputSpec(name="idea_draft", json_schema_text=StrictSchema(cls.model_json_schema()).json())

    @classmethod
    def parse(cls, output_json: str) -> tuple[IdeaDraft | None, tuple[DraftProblem, ...]]:
        """The draft, or the shape problems that stopped it parsing."""
        try:
            return cls.model_validate_json(output_json), ()
        except ValidationError as error:
            return None, DraftProblem.from_validation(error)

    def problems_for(self, draw: Draw) -> tuple[DraftProblem, ...]:
        """Meaning-level problems: one sentence, length, and card coverage and order."""
        problems: list[DraftProblem] = []
        sentence = Sentence(self.statement)
        breaks = sentence.boundaries()
        if breaks:
            problems.append(
                DraftProblem(field="statement", message=f"must be one sentence, but has {breaks + 1}")
            )
        if sentence.words > Sentence.MAX_WORDS:
            problems.append(
                DraftProblem(
                    field="statement", message=f"must be at most {Sentence.MAX_WORDS} words, but has {sentence.words}"
                )
            )
        for part in ("statement", "subject", "behavior", "rationale"):
            if not getattr(self, part).strip():
                problems.append(DraftProblem(field=part, message="must not be blank"))
        given = tuple(reading.card for reading in self.card_readings)
        if given != draw.drawn_cards:
            problems.append(
                DraftProblem(
                    field="card_readings",
                    message=(
                        f"must read exactly these cards in this order: {', '.join(draw.drawn_cards)}; "
                        f"got {', '.join(given)}"
                    ),
                )
            )
        if any(not reading.interpretation.strip() for reading in self.card_readings):
            problems.append(DraftProblem(field="card_readings", message="every interpretation must be non-blank"))
        return tuple(problems)

    def to_idea(self, position: int, usage: Usage) -> Idea:
        return Idea(
            position=position,
            statement=" ".join(self.statement.split()),
            subject=self.subject,
            behavior=self.behavior,
            rationale=self.rationale,
            card_readings=self.card_readings,
            usage=usage,
        )
