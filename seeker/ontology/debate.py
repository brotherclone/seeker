"""The debate classes from schema/seeker.yaml: ``Citation``, ``Critique``,
``Reply``, ``IdeaRevision``, ``Defense``, ``Debate`` and ``DebateFailure``, and
the enums ``CritiqueTarget``, ``Severity``, ``DefenseMove`` and ``DefenseOutcome``."""

from __future__ import annotations

from typing import ClassVar

from pydantic import ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

from seeker.ontology.base import DescribedStrEnum, SeekerModel
from seeker.ontology.generation import Usage
from seeker.ontology.reading import RoleName
from seeker.ontology.types import CardId, ModelId, Url, WorkId


class CritiqueTarget(DescribedStrEnum):
    """Which part of an idea a critique says fails. Naming the part keeps a
    critique from being a general complaint."""

    SUBJECT = "subject", "The thing being made (the X) is wrong, vague or not new."
    BEHAVIOR = "behavior", "What the thing does (the Y) fails or cannot be done."
    RATIONALE = "rationale", "The reason (the Z) is false, circular or does not matter."
    CARD_READING = "card_reading", "One card was read in a way the idea does not earn."
    CONSTRAINT = "constraint", "The idea does not satisfy its constraint card."


class Severity(DescribedStrEnum):
    """How badly a critic says an idea fails. Critics set it themselves, so the
    judge never sees it."""

    FATAL = "fatal", "If true, the idea should not survive as stated."
    SERIOUS = "serious", "A real problem the idea must answer, short of killing it."
    MINOR = "minor", "A small or speculative problem, or no prior art found."


class DefenseMove(DescribedStrEnum):
    """How the advocate answers one critique."""

    CONCEDE = "concede", "The critique is right."
    REBUT = "rebut", "The critique is wrong or does not matter, with an argument why."


class DefenseOutcome(DescribedStrEnum):
    """What the advocate does with the idea after answering every critique."""

    DEFENDED = "defended", "The idea stands as stated."
    REVISED = "revised", "The idea is restated to survive the critiques."
    WITHDRAWN = "withdrawn", "The advocate gives the idea up; it does not compete."


def _invalid(code: str, message: str) -> PydanticCustomError:
    return PydanticCustomError(code, message)


class Citation(SeekerModel):
    """One piece of prior-art evidence: a web page the prosecutor's searches
    returned, or a work already in the vault's catalog."""

    model_config = ConfigDict(title="Citation", json_schema_extra={"class_uri": "seeker:Citation"})

    title: str = Field(
        title="title",
        min_length=1,
        description="The work's title as its creators give it.",
        examples=["Congregational Sampler (NIME 2019)"],
        json_schema_extra={"slot_uri": "dcterms:title"},
    )
    url: Url | None = Field(
        default=None,
        title="url",
        description='Where the work can be found or was captured from.',
        examples=["https://nime.org/proceedings/2019/nime2019_paper042.pdf"],
        json_schema_extra={"slot_uri": "seeker:url"},
    )
    cited_work: WorkId | None = Field(
        default=None,
        title="cited_work",
        description='A captured work cited as prior art, referenced by work id.',
        examples=["oramics-demo-tape-1962"],
        json_schema_extra={"slot_uri": "seeker:citedWork"},
    )
    relevance: str = Field(
        title="relevance",
        min_length=1,
        description='One sentence on how close the cited work is to the idea.',
        examples=["Uses audience speech to drive a granular engine, though not in liturgy."],
        json_schema_extra={"slot_uri": "seeker:relevance"},
    )
    embodied_cards: tuple[CardId, ...] = Field(
        default=(),
        title="embodied_cards",
        description=(
            "The cards of the idea's draw that the cited work already embodies, referenced by"
            ' card id.'
        ),
        examples=["granular-synthesis"],
        json_schema_extra={"slot_uri": "seeker:embodiedCards"},
    )

    @model_validator(mode="after")
    def _one_source(self) -> Citation:
        if (self.url is None) == (self.cited_work is None):
            raise _invalid("citation_source", "a citation has exactly one of url and cited_work")
        return self


class Critique(SeekerModel):
    """One critic's attack on one idea, naming the part that fails, how badly, and
    the failure in one sentence."""

    model_config = ConfigDict(title="Critique", json_schema_extra={"class_uri": "seeker:Critique"})

    role_name: RoleName = Field(
        title="role_name",
        description='Which role in the pipeline this is.',
        examples=["skeptic"],
        json_schema_extra={"slot_uri": "seeker:roleName"},
    )
    model: ModelId = Field(
        title="model",
        description='The Claude model the role runs on.',
        examples=["claude-haiku-5-5"],
        json_schema_extra={"slot_uri": "seeker:model"},
    )
    target: CritiqueTarget = Field(
        title="target",
        description='Which part of the idea the critique says fails.',
        examples=["behavior"],
        json_schema_extra={"slot_uri": "seeker:target"},
    )
    target_card: CardId | None = Field(
        default=None,
        title="target_card",
        description='The card whose reading fails, when the target is a card reading.',
        examples=["lumigraph"],
        json_schema_extra={"slot_uri": "seeker:targetCard"},
    )
    severity: Severity = Field(
        title="severity",
        description='How badly the critic says the idea fails.',
        examples=["serious"],
        json_schema_extra={"slot_uri": "seeker:severity"},
    )
    failure: str = Field(
        title="failure",
        min_length=1,
        description=(
            "The specific failure, in one sentence that says something the idea's statement "
            'does not.'
        ),
        examples=["Real-time grain density from untrained crowd speech needs a mic array no church has."],
        json_schema_extra={"slot_uri": "seeker:failure"},
    )
    argument: str = Field(
        title="argument",
        min_length=1,
        description='The reasoning behind a critique or a reply.',
        examples=["Crowd speech is diffuse and reverberant; isolating responses needs beamforming or close mics."],
        json_schema_extra={"slot_uri": "seeker:argument"},
    )
    citations: tuple[Citation, ...] = Field(
        default=(),
        title="citations",
        description='The evidence a prior-art critique rests on.',
        json_schema_extra={"slot_uri": "seeker:citations"},
    )
    none_found: bool = Field(
        default=False,
        title="none_found",
        description=(
            'True when the prosecutor searched and found no prior art. Such a critique '
            'carries no citations and is minor.'
        ),
        examples=[False],
        json_schema_extra={"slot_uri": "seeker:noneFound"},
    )
    usage: Usage = Field(
        title="usage",
        description='Tokens consumed by the model calls this record accounts for.',
        json_schema_extra={"slot_uri": "seeker:usage"},
    )

    @model_validator(mode="after")
    def _evidence_matches_target(self) -> Critique:
        if (self.target is CritiqueTarget.CARD_READING) != (self.target_card is not None):
            raise _invalid("target_card", "target_card is required exactly when the target is card_reading")
        if self.none_found:
            if self.role_name is not RoleName.PROSECUTOR:
                raise _invalid("none_found", "only the prosecutor reports that no prior art was found")
            if self.citations or self.severity is not Severity.MINOR:
                raise _invalid("none_found", "a critique that found no prior art has no citations and is minor")
        elif self.role_name is RoleName.PROSECUTOR and not self.citations:
            raise _invalid("citations", "a prior-art critique cites its evidence or declares none found")
        elif self.role_name is not RoleName.PROSECUTOR and self.citations:
            raise _invalid("citations", "only the prosecutor cites prior art")
        return self


class Reply(SeekerModel):
    """The advocate's answer to one critique."""

    model_config = ConfigDict(title="Reply", json_schema_extra={"class_uri": "seeker:Reply"})

    answers: RoleName = Field(
        title="answers",
        description='The critic role whose critique this reply answers.',
        examples=["skeptic"],
        json_schema_extra={"slot_uri": "seeker:answers"},
    )
    move: DefenseMove = Field(
        title="move",
        description='Whether the advocate concedes or rebuts the critique.',
        examples=["rebut"],
        json_schema_extra={"slot_uri": "seeker:move"},
    )
    argument: str = Field(
        title="argument",
        min_length=1,
        description='The reasoning behind a critique or a reply.',
        examples=["Crowd speech is diffuse and reverberant; isolating responses needs beamforming or close mics."],
        json_schema_extra={"slot_uri": "seeker:argument"},
    )


class IdeaRevision(SeekerModel):
    """An idea restated by the advocate to survive its critiques, in the same
    one-sentence form and from the same draw."""

    model_config = ConfigDict(title="IdeaRevision", json_schema_extra={"class_uri": "seeker:IdeaRevision"})

    statement: str = Field(
        title="statement",
        min_length=1,
        description=(
            'The idea as one sentence of the form "a/an X that does Y because Z", at most 60 '
            'words.'
        ),
        examples=["A webcomic that plays a chord as you scroll because panels are bars of time."],
        json_schema_extra={"slot_uri": "seeker:statement"},
    )
    subject: str = Field(
        title="subject",
        min_length=1,
        description='The X of the statement, meaning the thing being made.',
        examples=["a webcomic"],
        json_schema_extra={"slot_uri": "seeker:subject"},
    )
    behavior: str = Field(
        title="behavior",
        min_length=1,
        description='The Y of the statement, meaning what the thing does.',
        examples=["plays a chord as you scroll"],
        json_schema_extra={"slot_uri": "seeker:behavior"},
    )
    rationale: str = Field(
        title="rationale",
        min_length=1,
        description=(
            'The Z of the statement, meaning why the idea works or matters, as a real reason '
            'rather than a restatement.'
        ),
        examples=["panels are bars of time"],
        json_schema_extra={"slot_uri": "seeker:rationale"},
    )


class Defense(SeekerModel):
    """The advocate's answer to every critique of one idea, and what became of the
    idea."""

    model_config = ConfigDict(title="Defense", json_schema_extra={"class_uri": "seeker:Defense"})

    model: ModelId = Field(
        title="model",
        description='The Claude model the role runs on.',
        examples=["claude-haiku-5-5"],
        json_schema_extra={"slot_uri": "seeker:model"},
    )
    replies: tuple[Reply, ...] = Field(
        title="replies",
        min_length=1, max_length=3,
        description='One reply per critique, in critique order.',
        json_schema_extra={"slot_uri": "seeker:replies"},
    )
    outcome: DefenseOutcome = Field(
        title="outcome",
        description='What the advocate did with the idea.',
        examples=["revised"],
        json_schema_extra={"slot_uri": "seeker:outcome"},
    )
    revision: IdeaRevision | None = Field(
        default=None,
        title="revision",
        description='The restated idea, present exactly when the outcome is revised.',
        json_schema_extra={"slot_uri": "seeker:revision"},
    )
    usage: Usage = Field(
        title="usage",
        description='Tokens consumed by the model calls this record accounts for.',
        json_schema_extra={"slot_uri": "seeker:usage"},
    )

    @model_validator(mode="after")
    def _revision_matches_outcome(self) -> Defense:
        if (self.outcome is DefenseOutcome.REVISED) != (self.revision is not None):
            raise _invalid("revision", "a revision is given exactly when the outcome is revised")
        answered = [reply.answers for reply in self.replies]
        if len(set(answered)) != len(answered):
            raise _invalid("replies", "each critique gets exactly one reply")
        return self

    def reply_to(self, role: RoleName) -> Reply | None:
        return next((reply for reply in self.replies if reply.answers is role), None)


class Debate(SeekerModel):
    """One idea's round of debate: the critiques it faced, the advocate's defense,
    and the statement that goes on to compete."""

    model_config = ConfigDict(title="Debate", json_schema_extra={"class_uri": "seeker:Debate"})

    position: int = Field(
        title="position",
        ge=1,
        description="The draw's 1-based position within its batch.",
        examples=[1],
        json_schema_extra={"slot_uri": "seeker:position"},
    )
    critiques: tuple[Critique, ...] = Field(
        title="critiques",
        min_length=1, max_length=3,
        description=(
            'The critiques the idea faced, in role order. Fewer than three means a critic '
            'failed and is recorded as a debate failure.'
        ),
        json_schema_extra={"slot_uri": "seeker:critiques"},
    )
    defense: Defense = Field(
        title="defense",
        description="The advocate's answer to the critiques.",
        json_schema_extra={"slot_uri": "seeker:defense"},
    )
    final_statement: str = Field(
        title="final_statement",
        min_length=1,
        description=(
            "The statement that competes, the revision's when the idea was revised."
        ),
        examples=["A webcomic that plays a chord as you scroll because panels are bars of time."],
        json_schema_extra={"slot_uri": "seeker:finalStatement"},
    )

    CRITICS: ClassVar[tuple[RoleName, ...]] = (RoleName.PROSECUTOR, RoleName.SKEPTIC, RoleName.TASTE_CRITIC)

    @model_validator(mode="after")
    def _replies_match_critiques(self) -> Debate:
        roles = [critique.role_name for critique in self.critiques]
        if len(set(roles)) != len(roles) or not set(roles) <= set(self.CRITICS):
            raise _invalid("critiques", "a debate holds at most one critique per critic role")
        if sorted(r.answers for r in self.defense.replies) != sorted(roles):
            raise _invalid("replies", "the defense answers exactly the critiques the idea faced")
        if self.defense.revision is not None and self.final_statement != self.defense.revision.statement:
            raise _invalid("final_statement", "a revised idea competes as its revision")
        return self

    @property
    def competes(self) -> bool:
        return self.defense.outcome is not DefenseOutcome.WITHDRAWN

    @property
    def short_a_critique(self) -> bool:
        return len(self.critiques) < len(self.CRITICS)

    def critique_by(self, role: RoleName) -> Critique | None:
        return next((critique for critique in self.critiques if critique.role_name is role), None)


class DebateFailure(SeekerModel):
    """A debate role that produced no valid answer for one idea, even after a
    retry."""

    model_config = ConfigDict(title="DebateFailure", json_schema_extra={"class_uri": "seeker:DebateFailure"})

    position: int = Field(
        title="position",
        ge=1,
        description="The draw's 1-based position within its batch.",
        examples=[1],
        json_schema_extra={"slot_uri": "seeker:position"},
    )
    role_name: RoleName = Field(
        title="role_name",
        description='Which role in the pipeline this is.',
        examples=["skeptic"],
        json_schema_extra={"slot_uri": "seeker:roleName"},
    )
    model: ModelId = Field(
        title="model",
        description='The Claude model the role runs on.',
        examples=["claude-haiku-5-5"],
        json_schema_extra={"slot_uri": "seeker:model"},
    )
    failure_reason: str = Field(
        title="failure_reason",
        min_length=1,
        description='Why a role produced no valid answer, even after a retry.',
        examples=["invalid after retry: failure restates the idea"],
        json_schema_extra={"slot_uri": "seeker:failureReason"},
    )
    discarded_critiques: tuple[Critique, ...] = Field(
        default=(),
        title="discarded_critiques",
        description=(
            "When the advocate fails, the critiques it would have answered. The idea does not "
            "compete, but they are kept so every call made stays recorded."
        ),
        json_schema_extra={"slot_uri": "seeker:discardedCritiques"},
    )
    usage: Usage = Field(
        title="usage",
        description='Tokens consumed by the model calls this record accounts for.',
        json_schema_extra={"slot_uri": "seeker:usage"},
    )
