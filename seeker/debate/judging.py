"""What the judge sees, blinded, and how its verdicts are checked.

The judge gets two debated ideas labelled only A and B. Objections are shown in
a seeded shuffled order, with no role names, models, personas or severities:
severity is self-reported by critics, and showing it would let the judge count
labels instead of reading arguments.
"""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import ConfigDict, Field, ValidationError

from seeker.debate.schedule import Pairing, TournamentStream
from seeker.generate.draft import DraftProblem, StrictSchema
from seeker.models import OutputSpec
from seeker.ontology import (
    AxisVerdict,
    Comparison,
    Critique,
    Debate,
    DefenseMove,
    Idea,
    ModelId,
    ScoreAxis,
    SeekerModel,
    Usage,
)


class Entrant(SeekerModel):
    """One debated idea as it competes: the original idea and its debate."""

    model_config = ConfigDict(title="Entrant")

    idea: Idea
    debate: Debate

    @property
    def position(self) -> int:
        return self.idea.position

    def parts(self) -> tuple[str, str, str]:
        source = self.debate.defense.revision or self.idea
        return (source.subject, source.behavior, source.rationale)


class BlindEntry:
    """One side of a comparison, rendered with nothing that names who argued what."""

    def __init__(self, label: str, entrant: Entrant, seed: int, pairing: Pairing) -> None:
        self.label = label
        self.entrant = entrant
        salt = f"objections:{pairing.first}:{pairing.second}:{entrant.position}"
        critiques = entrant.debate.critiques
        self.order = TournamentStream(seed, salt).permutation(len(critiques))

    def lines(self) -> list[str]:
        subject, behavior, rationale = self.entrant.parts()
        lines = [
            f"Idea {self.label}: {self.entrant.debate.final_statement}",
            f"- subject (X): {subject}",
            f"- behavior (Y): {behavior}",
            f"- rationale (Z): {rationale}",
            "- card readings:",
        ]
        lines += [f"  - {r.card}: {r.interpretation}" for r in self.entrant.idea.card_readings]
        for number, index in enumerate(self.order, start=1):
            critique = self.entrant.debate.critiques[index]
            lines += self._objection(number, critique)
        return lines

    def _objection(self, number: int, critique: Critique) -> list[str]:
        lines = [f"Objection {number}: {critique.failure}", f"  Argument: {critique.argument}"]
        if critique.none_found:
            lines.append("  Evidence: a search for prior art found none.")
        for citation in critique.citations:
            source = citation.url or "a work in the catalog"
            lines.append(f"  Evidence: {citation.title} <{source}>: {citation.relevance}")
        reply = self.entrant.debate.defense.reply_to(critique.role_name)
        if reply is not None:
            verb = "concedes" if reply.move is DefenseMove.CONCEDE else "rebuts"
            lines.append(f"  Reply ({verb}): {reply.argument}")
        return lines


class JudgePrompt:
    """Both sides of one comparison."""

    def __init__(self, pairing: Pairing, a: Entrant, b: Entrant, seed: int) -> None:
        self.pairing = pairing
        self.a = BlindEntry("A", a, seed, pairing)
        self.b = BlindEntry("B", b, seed, pairing)

    def render(self) -> str:
        return "\n".join(
            [
                *self.a.lines(),
                "",
                *self.b.lines(),
                "",
                "Pick A or B on each of novelty, feasibility and promise, each with a one-sentence reason. "
                "No ties. Answer with the JSON object only.",
            ]
        )


class AxisChoice(SeekerModel):
    """The judge's pick on one axis."""

    model_config = ConfigDict(title="AxisChoice")

    winner: Literal["A", "B"] = Field(description="A or B. No ties.")
    reason: str = Field(min_length=1, description="One sentence naming something specific in the winner or its debate.")


class JudgmentDraft(SeekerModel):
    """The judge's answer: one pick per score axis."""

    model_config = ConfigDict(title="JudgmentDraft")

    AXES: ClassVar[tuple[ScoreAxis, ...]] = tuple(ScoreAxis)

    novelty: AxisChoice = Field(description="Which is further from anything that already exists.")
    feasibility: AxisChoice = Field(description="Which one person could more plausibly build.")
    promise: AxisChoice = Field(description="Which has more in it worth making.")

    @classmethod
    def output_spec(cls) -> OutputSpec:
        return OutputSpec(name="judgment_draft", json_schema_text=StrictSchema(cls.model_json_schema()).json())

    @classmethod
    def parse(cls, output_json: str) -> tuple[JudgmentDraft | None, tuple[DraftProblem, ...]]:
        try:
            return cls.model_validate_json(output_json), ()
        except ValidationError as error:
            return None, DraftProblem.from_validation(error)

    def problems(self) -> tuple[DraftProblem, ...]:
        return tuple(
            DraftProblem(field=axis.value, message="give a one-sentence reason")
            for axis in self.AXES
            if not getattr(self, axis.value).reason.strip()
        )

    def to_comparison(self, pairing: Pairing, model: ModelId, usage: Usage) -> Comparison:
        sides = {"A": pairing.first, "B": pairing.second}
        verdicts = tuple(
            AxisVerdict(axis_name=axis, winner=sides[getattr(self, axis.value).winner], ruling=getattr(self, axis.value).reason)
            for axis in self.AXES
        )
        return Comparison(first=pairing.first, second=pairing.second, verdicts=verdicts, model=model, usage=usage)

    @staticmethod
    def failed(pairing: Pairing, model: ModelId, usage: Usage) -> Comparison:
        return Comparison(first=pairing.first, second=pairing.second, failed=True, model=model, usage=usage)
