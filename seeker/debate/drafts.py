"""Critic and advocate answers before they become ontology records, and how they are checked.

Strict structured output wants every property required and no nulls, so optional
parts are sent as empty strings or lists and turned into absent values here.
"""

from __future__ import annotations

import re
from typing import ClassVar

from pydantic import ConfigDict, Field, ValidationError

from seeker.generate.draft import DraftProblem, Sentence, StrictSchema
from seeker.models import OutputSpec
from seeker.ontology import (
    Card,
    CardId,
    Citation,
    Critique,
    CritiqueTarget,
    Defense,
    DefenseMove,
    DefenseOutcome,
    Draw,
    Idea,
    IdeaRevision,
    ModelId,
    Reply,
    RoleName,
    SeekerModel,
    Severity,
    Usage,
    WorkId,
)


class Wording:
    """Word-level comparison between a critique's failure and the idea it attacks."""

    STOP_WORDS: ClassVar[frozenset[str]] = frozenset(
        """a an the and or but of to in on at by for with from as is are be been being it its this that these
        those which who whom what when where why how than then so because not no nor can could would should will
        may might must do does did has have had into onto over under about it's idea one""".split()
    )
    WORD: ClassVar[re.Pattern[str]] = re.compile(r"[a-z0-9]+(?:['-][a-z0-9]+)*")
    RESTATEMENT_OVERLAP: ClassVar[float] = 0.7

    def __init__(self, text: str) -> None:
        self.words = frozenset(self.WORD.findall(text.lower()))

    @property
    def content(self) -> frozenset[str]:
        return self.words - self.STOP_WORDS

    def overlap(self, other: Wording) -> float:
        """Jaccard overlap of content words."""
        union = self.content | other.content
        return len(self.content & other.content) / len(union) if union else 1.0

    def restates(self, statement: Wording, card_words: frozenset[str]) -> bool:
        """True when the failure says nothing the statement and the card names do not."""
        if self.overlap(statement) >= self.RESTATEMENT_OVERLAP:
            return True
        return not (self.content - statement.content - card_words)


class CritiqueDraft(SeekerModel):
    """A critique as a critic submits it, before its role, model and usage are known."""

    model_config = ConfigDict(title="CritiqueDraft")

    NAME: ClassVar[str] = "critique_draft"
    MIN_WORDS: ClassVar[int] = 8
    MAX_WORDS: ClassVar[int] = 40

    target: CritiqueTarget = Field(
        description="Which part of the idea fails: subject, behavior, rationale, card_reading or constraint."
    )
    target_card: str = Field(
        default="", description="The card id whose reading fails when target is card_reading; otherwise empty."
    )
    severity: Severity = Field(description="fatal, serious or minor.")
    failure: str = Field(
        min_length=1,
        description="The specific failure in ONE sentence of 8-40 words that says something the idea does not.",
    )
    argument: str = Field(min_length=1, description="The reasoning behind the failure.")

    @classmethod
    def output_spec(cls) -> OutputSpec:
        return OutputSpec(name=cls.NAME, json_schema_text=StrictSchema(cls.model_json_schema()).json())

    @classmethod
    def parse(cls, output_json: str) -> tuple[CritiqueDraft | None, tuple[DraftProblem, ...]]:
        try:
            return cls.model_validate_json(output_json), ()
        except ValidationError as error:
            return None, DraftProblem.from_validation(error)

    def problems_for(self, idea: Idea, draw: Draw, card_words: frozenset[str]) -> tuple[DraftProblem, ...]:
        """Named-failure rules: one sentence, a sensible length, not a restatement, a valid target."""
        problems: list[DraftProblem] = []
        sentence = Sentence(self.failure)
        if sentence.boundaries():
            problems.append(DraftProblem(field="failure", message="must be one sentence"))
        if not self.MIN_WORDS <= sentence.words <= self.MAX_WORDS:
            problems.append(
                DraftProblem(
                    field="failure",
                    message=(
                        f"must be {self.MIN_WORDS}-{self.MAX_WORDS} words naming a specific failure, "
                        f"but has {sentence.words}"
                    ),
                )
            )
        elif Wording(self.failure).restates(Wording(idea.statement), card_words):
            problems.append(
                DraftProblem(
                    field="failure",
                    message="restates the idea; name a specific failure the statement does not already say",
                )
            )
        if self.target is CritiqueTarget.CARD_READING:
            if self.target_card not in draw.drawn_cards:
                problems.append(
                    DraftProblem(
                        field="target_card",
                        message=f"must be one of the draw's cards: {', '.join(draw.drawn_cards)}",
                    )
                )
        elif self.target_card:
            problems.append(DraftProblem(field="target_card", message="must be empty unless target is card_reading"))
        if not self.argument.strip():
            problems.append(DraftProblem(field="argument", message="must not be blank"))
        return tuple(problems)

    def to_critique(
        self,
        role: RoleName,
        model: ModelId,
        usage: Usage,
        citations: tuple[Citation, ...] = (),
        none_found: bool = False,
    ) -> Critique:
        return Critique(
            role_name=role,
            model=model,
            target=self.target,
            target_card=self.target_card or None,
            severity=self.severity,
            failure=" ".join(self.failure.split()),
            argument=self.argument,
            citations=citations,
            none_found=none_found,
            usage=usage,
        )


class CitationDraft(SeekerModel):
    """One citation as the prosecutor submits it: a search result URL or a catalog work id."""

    model_config = ConfigDict(title="CitationDraft")

    title: str = Field(min_length=1, description="The cited page's or work's title.")
    url: str = Field(default="", description="A URL your searches returned, exactly; empty when citing a work id.")
    work_id: str = Field(default="", description="A catalog work id you were given; empty when citing a URL.")
    relevance: str = Field(min_length=1, description="One sentence on how close it is to the idea.")
    embodied_cards: tuple[str, ...] = Field(
        default=(), description="Which of the draw's card ids the cited work already embodies."
    )

    def problems(self, index: int, result_urls: frozenset[str], work_ids: frozenset[str]) -> list[DraftProblem]:
        where = f"citations.{index}"
        if bool(self.url) == bool(self.work_id):
            return [DraftProblem(field=where, message="give exactly one of url and work_id")]
        if self.url and self.url not in result_urls:
            return [DraftProblem(field=f"{where}.url", message=f"{self.url} was not among this call's search results")]
        if self.work_id and self.work_id not in work_ids:
            return [DraftProblem(field=f"{where}.work_id", message=f"{self.work_id} is not a catalog work id you were given")]
        return []

    def to_citation(self, draw: Draw) -> Citation:
        """Card links outside the draw are dropped, not rejected."""
        cards = tuple(CardId(card) for card in self.embodied_cards if card in draw.drawn_cards)
        return Citation(
            title=self.title,
            url=self.url or None,
            cited_work=WorkId(self.work_id) if self.work_id else None,
            relevance=self.relevance,
            embodied_cards=tuple(dict.fromkeys(cards)),
        )


class ProsecutorDraft(CritiqueDraft):
    """A prior-art critique: a critique plus its evidence, or a declaration that none was found."""

    model_config = ConfigDict(title="ProsecutorDraft")

    NAME: ClassVar[str] = "prosecutor_draft"

    citations: tuple[CitationDraft, ...] = Field(
        default=(), description="Your evidence: search results by exact URL, catalog works by work id."
    )
    none_found: bool = Field(
        default=False, description="True only if you found no prior art; then give no citations and severity minor."
    )

    def evidence_problems(self, result_urls: frozenset[str], work_ids: frozenset[str]) -> tuple[DraftProblem, ...]:
        problems: list[DraftProblem] = []
        if self.none_found:
            if self.citations or self.severity is not Severity.MINOR:
                problems.append(
                    DraftProblem(field="none_found", message="no prior art found means no citations and severity minor")
                )
        elif not self.citations:
            problems.append(
                DraftProblem(
                    field="citations",
                    message="prior-art claims need evidence: cite a search result or a catalog work, or set none_found",
                )
            )
        for index, citation in enumerate(self.citations):
            problems += citation.problems(index, result_urls, work_ids)
        return tuple(problems)

    def to_prosecution(self, model: ModelId, usage: Usage, draw: Draw) -> Critique:
        citations = tuple(c.to_citation(draw) for c in self.citations)
        return self.to_critique(RoleName.PROSECUTOR, model, usage, citations, self.none_found)


class ReplyDraft(SeekerModel):
    """One reply as the advocate submits it."""

    model_config = ConfigDict(title="ReplyDraft")

    answers: RoleName = Field(description="The critic role whose critique this answers: prosecutor, skeptic or taste_critic.")
    move: DefenseMove = Field(description="concede or rebut.")
    argument: str = Field(min_length=1, description="Why the critique is right, or why it is wrong or does not matter.")


class DefenseDraft(SeekerModel):
    """The advocate's answer as it submits it. The revision fields are empty unless the outcome is revised."""

    model_config = ConfigDict(title="DefenseDraft")

    replies: tuple[ReplyDraft, ...] = Field(min_length=1, description="Exactly one reply per critique.")
    outcome: DefenseOutcome = Field(description="defended, revised or withdrawn.")
    statement: str = Field(
        default="",
        description='When revised: the idea as ONE sentence "a/an X that does Y because Z", at most 60 words; else empty.',
    )
    subject: str = Field(default="", description="When revised: X, the thing being made; else empty.")
    behavior: str = Field(default="", description="When revised: Y, what it does; else empty.")
    rationale: str = Field(default="", description="When revised: Z, why it works or matters; else empty.")

    PARTS: ClassVar[tuple[str, ...]] = ("statement", "subject", "behavior", "rationale")

    @classmethod
    def output_spec(cls) -> OutputSpec:
        return OutputSpec(name="defense_draft", json_schema_text=StrictSchema(cls.model_json_schema()).json())

    @classmethod
    def parse(cls, output_json: str) -> tuple[DefenseDraft | None, tuple[DraftProblem, ...]]:
        try:
            return cls.model_validate_json(output_json), ()
        except ValidationError as error:
            return None, DraftProblem.from_validation(error)

    def problems_for(self, critiques: tuple[Critique, ...], foreign_cards: tuple[Card, ...]) -> tuple[DraftProblem, ...]:
        """Coverage, the conceded-fatal rules and the revision's form.

        ``foreign_cards`` are cards from outside the draw; a revision that names
        one has left its draw.
        """
        problems: list[DraftProblem] = []
        faced = [critique.role_name for critique in critiques]
        answered = [reply.answers for reply in self.replies]
        for role in faced:
            if answered.count(role) != 1:
                problems.append(
                    DraftProblem(field="replies", message=f"answer the {role.value} critique exactly once")
                )
        for role in sorted(set(answered) - set(faced)):
            problems.append(DraftProblem(field="replies", message=f"there is no {role.value} critique to answer"))
        conceded_fatal = any(
            reply.move is DefenseMove.CONCEDE
            and any(c.role_name is reply.answers and c.severity is Severity.FATAL for c in critiques)
            for reply in self.replies
        )
        if conceded_fatal and self.outcome is DefenseOutcome.DEFENDED:
            problems.append(
                DraftProblem(field="outcome", message="a conceded fatal critique means revised or withdrawn, not defended")
            )
        if self.outcome is DefenseOutcome.REVISED:
            problems += self._revision_problems(foreign_cards)
        elif any(getattr(self, part) for part in self.PARTS):
            problems.append(DraftProblem(field="statement", message="leave the revision fields empty unless revised"))
        return tuple(problems)

    def _revision_problems(self, foreign_cards: tuple[Card, ...]) -> list[DraftProblem]:
        problems = [
            DraftProblem(field=part, message="must not be blank when the outcome is revised")
            for part in self.PARTS
            if not getattr(self, part).strip()
        ]
        sentence = Sentence(self.statement)
        breaks = sentence.boundaries()
        if breaks:
            problems.append(DraftProblem(field="statement", message=f"must be one sentence, but has {breaks + 1}"))
        if sentence.words > Sentence.MAX_WORDS:
            problems.append(
                DraftProblem(
                    field="statement", message=f"must be at most {Sentence.MAX_WORDS} words, but has {sentence.words}"
                )
            )
        named = [card.name for card in foreign_cards if CardMention(card.name).found_in(self.statement)]
        if named:
            problems.append(
                DraftProblem(
                    field="statement",
                    message=f"must stay with the draw's three cards, but names {', '.join(named)}",
                )
            )
        return problems

    def to_defense(self, model: ModelId, usage: Usage) -> Defense:
        revision = None
        if self.outcome is DefenseOutcome.REVISED:
            revision = IdeaRevision(
                statement=" ".join(self.statement.split()),
                subject=self.subject,
                behavior=self.behavior,
                rationale=self.rationale,
            )
        return Defense(
            model=model,
            replies=tuple(Reply(answers=r.answers, move=r.move, argument=r.argument) for r in self.replies),
            outcome=self.outcome,
            revision=revision,
            usage=usage,
        )


class CardMention:
    """Whether a card's name appears in a text. Only distinctive names count:
    two or more words, or one word of at least seven letters, so common words
    such as "tape" do not trip it."""

    MIN_SINGLE_WORD: ClassVar[int] = 7

    def __init__(self, name: str) -> None:
        self.name = name
        self.words = name.lower().split()

    @property
    def distinctive(self) -> bool:
        return len(self.words) > 1 or len(self.name) >= self.MIN_SINGLE_WORD

    def found_in(self, text: str) -> bool:
        if not self.distinctive:
            return False
        pattern = r"\b" + r"\s+".join(re.escape(word) for word in self.words) + r"\b"
        return re.search(pattern, text.lower()) is not None
