"""The idea-generation classes from schema/seeker.yaml: ``Usage``,
``CardReading``, ``Idea``, ``GenerationFailure`` and ``Generation``."""

from __future__ import annotations

from datetime import datetime

from pydantic import ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

from seeker.ontology.base import SeekerModel
from seeker.ontology.draw import DrawBatch
from seeker.ontology.reading import Reading, RoleName
from seeker.ontology.types import CardId, GitCommit, ModelId, Sha256Digest

_COUNT_EXAMPLES = [1200]


class Usage(SeekerModel):
    """Token counts for one or more model calls, split the way they are billed."""

    model_config = ConfigDict(title="Usage", json_schema_extra={"class_uri": "seeker:Usage"})

    input_tokens: int = Field(
        title="input_tokens",
        ge=0,
        description="Uncached input tokens billed at the model's input rate.",
        examples=_COUNT_EXAMPLES,
        json_schema_extra={"slot_uri": "seeker:inputTokens"},
    )
    output_tokens: int = Field(
        title="output_tokens",
        ge=0,
        description="Output tokens billed at the model's output rate.",
        examples=[450],
        json_schema_extra={"slot_uri": "seeker:outputTokens"},
    )
    cache_read_tokens: int = Field(
        title="cache_read_tokens",
        ge=0,
        description="Input tokens served from the prompt cache.",
        examples=[900],
        json_schema_extra={"slot_uri": "seeker:cacheReadTokens"},
    )
    cache_write_tokens: int = Field(
        title="cache_write_tokens",
        ge=0,
        description="Input tokens written to the prompt cache.",
        examples=[900],
        json_schema_extra={"slot_uri": "seeker:cacheWriteTokens"},
    )
    web_search_requests: int = Field(
        default=0,
        title="web_search_requests",
        ge=0,
        description=(
            "Web searches the model ran through the server-side search tool, billed per search on top "
            "of tokens. Absent in records written before searches existed, which means none."
        ),
        examples=[2],
        json_schema_extra={"slot_uri": "seeker:webSearchRequests"},
    )

    @classmethod
    def zero(cls) -> Usage:
        return cls(input_tokens=0, output_tokens=0, cache_read_tokens=0, cache_write_tokens=0)

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
            cache_write_tokens=self.cache_write_tokens + other.cache_write_tokens,
            web_search_requests=self.web_search_requests + other.web_search_requests,
        )

    @classmethod
    def total(cls, usages: tuple[Usage, ...]) -> Usage:
        result = cls.zero()
        for usage in usages:
            result = result + usage
        return result


class CardReading(SeekerModel):
    """How the generator interpreted one drawn card. Under a metaphorical
    reading this is the only record of what a card was taken to mean."""

    model_config = ConfigDict(title="CardReading", json_schema_extra={"class_uri": "seeker:CardReading"})

    card: CardId = Field(
        title="card",
        description="The card being interpreted, referenced by card id.",
        examples=["oramics"],
        json_schema_extra={"slot_uri": "seeker:card"},
    )
    interpretation: str = Field(
        title="interpretation",
        min_length=1,
        description="One line on how the card was taken in this idea.",
        examples=["Drawing as a way of composing: the score is the instrument."],
        json_schema_extra={"slot_uri": "seeker:interpretation"},
    )


class Idea(SeekerModel):
    """One idea generated from one draw: a single sentence of the form "a/an X
    that does Y because Z", its three parts, and how each card was read."""

    model_config = ConfigDict(title="Idea", json_schema_extra={"class_uri": "seeker:Idea"})

    position: int = Field(
        title="position",
        ge=1,
        description="The draw's 1-based position within its batch.",
        examples=[1],
        json_schema_extra={"slot_uri": "seeker:position"},
    )
    statement: str = Field(
        title="statement",
        min_length=1,
        description=(
            'The idea as one sentence of the form "a/an X that does Y because Z", at '
            "most 60 words."
        ),
        examples=["A webcomic that plays a chord as you scroll because panels are bars of time."],
        json_schema_extra={"slot_uri": "seeker:statement"},
    )
    subject: str = Field(
        title="subject",
        min_length=1,
        description="The X of the statement, meaning the thing being made.",
        examples=["a webcomic"],
        json_schema_extra={"slot_uri": "seeker:subject"},
    )
    behavior: str = Field(
        title="behavior",
        min_length=1,
        description="The Y of the statement, meaning what the thing does.",
        examples=["plays a chord as you scroll"],
        json_schema_extra={"slot_uri": "seeker:behavior"},
    )
    rationale: str = Field(
        title="rationale",
        min_length=1,
        description=(
            "The Z of the statement, meaning why the idea works or matters, as a real "
            "reason rather than a restatement."
        ),
        examples=["panels are bars of time"],
        json_schema_extra={"slot_uri": "seeker:rationale"},
    )
    card_readings: tuple[CardReading, ...] = Field(
        title="card_readings",
        min_length=3,
        max_length=3,
        description="How the generator read each drawn card, in the draw's card order.",
        json_schema_extra={"slot_uri": "seeker:cardReadings"},
    )
    usage: Usage = Field(
        title="usage",
        description="Tokens consumed by the model calls this record accounts for.",
        json_schema_extra={"slot_uri": "seeker:usage"},
    )

    @property
    def cards(self) -> tuple[CardId, ...]:
        return tuple(reading.card for reading in self.card_readings)


class GenerationFailure(SeekerModel):
    """A draw for which no valid idea was produced, even after a retry."""

    model_config = ConfigDict(title="GenerationFailure", json_schema_extra={"class_uri": "seeker:GenerationFailure"})

    position: int = Field(
        title="position",
        ge=1,
        description="The draw's 1-based position within its batch.",
        examples=[4],
        json_schema_extra={"slot_uri": "seeker:position"},
    )
    reason: str = Field(
        title="reason",
        min_length=1,
        description="Why no idea was recorded for this draw.",
        examples=["statement has 2 sentences after retry"],
        json_schema_extra={"slot_uri": "seeker:reason"},
    )
    usage: Usage = Field(
        title="usage",
        description="Tokens consumed by the model calls this record accounts for.",
        json_schema_extra={"slot_uri": "seeker:usage"},
    )


class Generation(SeekerModel):
    """One generator pass over a draw batch: the ideas and failures it
    produced, every input pinned (batch, reading, model, role digest,
    commit), and its token usage and estimated cost."""

    model_config = ConfigDict(title="Generation", json_schema_extra={"class_uri": "seeker:Generation"})

    draw_batch: DrawBatch = Field(
        title="draw_batch",
        description="The batch the ideas were generated from, embedded so the record stands alone.",
        json_schema_extra={"slot_uri": "seeker:drawBatch"},
    )
    reading: Reading = Field(
        title="reading",
        description="How freely the cards may be interpreted.",
        examples=["literal"],
        json_schema_extra={"slot_uri": "seeker:reading"},
    )
    role_name: RoleName = Field(
        title="role_name",
        description="Which role in the pipeline this is.",
        examples=["generator"],
        json_schema_extra={"slot_uri": "seeker:roleName"},
    )
    model: ModelId = Field(
        title="model",
        description="The Claude model the role runs on.",
        examples=["claude-opus-5-5"],
        json_schema_extra={"slot_uri": "seeker:model"},
    )
    role_digest: Sha256Digest = Field(
        title="role_digest",
        description="SHA-256 of the role file's bytes, so any prompt edit is visible.",
        examples=[Sha256Digest.EXAMPLES[0]],
        json_schema_extra={"slot_uri": "seeker:roleDigest"},
    )
    git_commit: GitCommit | None = Field(
        default=None,
        title="git_commit",
        description="The repository commit the generation ran from, when known.",
        examples=[GitCommit.EXAMPLES[0]],
        json_schema_extra={"slot_uri": "seeker:gitCommit"},
    )
    generated_at: datetime = Field(
        title="generated_at",
        description="When the generation started.",
        examples=["2026-11-04T23:00:00-05:00"],
        json_schema_extra={"slot_uri": "seeker:generatedAt"},
    )
    ideas: tuple[Idea, ...] = Field(
        default=(),
        title="ideas",
        description="The ideas produced, in draw position order.",
        json_schema_extra={"slot_uri": "seeker:ideas"},
    )
    failures: tuple[GenerationFailure, ...] = Field(
        default=(),
        title="failures",
        description="Draws that produced no valid idea, in position order.",
        json_schema_extra={"slot_uri": "seeker:failures"},
    )
    usage: Usage = Field(
        title="usage",
        description="Tokens consumed by the model calls this record accounts for.",
        json_schema_extra={"slot_uri": "seeker:usage"},
    )
    estimated_cost_usd: float = Field(
        title="estimated_cost_usd",
        ge=0,
        description=(
            "The total usage priced with the configured price table. It is an "
            "estimate, because prices change and are kept as data."
        ),
        examples=[0.21],
        json_schema_extra={"slot_uri": "seeker:estimatedCostUsd"},
    )

    @model_validator(mode="after")
    def _consistent(self) -> Generation:
        positions = [record.position for record in (*self.ideas, *self.failures)]
        if len(positions) != len(set(positions)):
            raise PydanticCustomError("duplicate_position", "a position has more than one idea or failure")
        if any(p > self.draw_batch.size for p in positions):
            raise PydanticCustomError(
                "position_out_of_batch", "a position exceeds the batch size {size}", {"size": self.draw_batch.size}
            )
        if [i.position for i in self.ideas] != sorted(i.position for i in self.ideas) or [
            f.position for f in self.failures
        ] != sorted(f.position for f in self.failures):
            raise PydanticCustomError("unordered", "ideas and failures must be in position order")
        if self.usage != Usage.total(tuple(r.usage for r in (*self.ideas, *self.failures))):
            raise PydanticCustomError("usage_total", "usage must equal the sum of the ideas' and failures' usage")
        return self

    @property
    def covered_positions(self) -> frozenset[int]:
        return frozenset(record.position for record in (*self.ideas, *self.failures))

    @property
    def remaining_positions(self) -> tuple[int, ...]:
        """Positions with neither an idea nor a failure yet."""
        return tuple(d.position for d in self.draw_batch.draws if d.position not in self.covered_positions)

    def idea_at(self, position: int) -> Idea | None:
        return next((idea for idea in self.ideas if idea.position == position), None)
