"""The tournament classes from schema/seeker.yaml: ``AxisVerdict``,
``Comparison``, ``Rating`` and ``Tournament``, and the ``ScoreAxis`` enum."""

from __future__ import annotations

from typing import ClassVar

from pydantic import ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

from seeker.ontology.base import DescribedStrEnum, SeekerModel
from seeker.ontology.generation import Usage
from seeker.ontology.types import ModelId


class ScoreAxis(DescribedStrEnum):
    """The separate axes ideas are judged on. Each axis keeps its own rating;
    they are never blended into one score."""

    NOVELTY = "novelty", "How far the idea is from its nearest prior art."
    FEASIBILITY = "feasibility", "Whether one person can build it with Gabe's actual gear, stack and time."
    PROMISE = "promise", "Whether there is something there worth making."


def _invalid(code: str, message: str) -> PydanticCustomError:
    return PydanticCustomError(code, message)


class AxisVerdict(SeekerModel):
    """The judge's verdict on one score axis of one comparison."""

    model_config = ConfigDict(title="AxisVerdict", json_schema_extra={"class_uri": "seeker:AxisVerdict"})

    axis_name: ScoreAxis = Field(
        title="axis_name",
        description='The score axis this verdict or rating is on.',
        examples=["promise"],
        json_schema_extra={"slot_uri": "seeker:axisName"},
    )
    winner: int = Field(
        title="winner",
        ge=1,
        description='The position of the idea that won on this axis.',
        examples=[3],
        json_schema_extra={"slot_uri": "seeker:winner"},
    )
    ruling: str = Field(
        title="ruling",
        min_length=1,
        description="The judge's one-sentence reason for the verdict.",
        examples=["B names a real performance context; A is a demo."],
        json_schema_extra={"slot_uri": "seeker:ruling"},
    )


class Comparison(SeekerModel):
    """One blind pairwise judgment between two debated ideas, with a winner on each
    score axis."""

    model_config = ConfigDict(title="Comparison", json_schema_extra={"class_uri": "seeker:Comparison"})

    first: int = Field(
        title="first",
        ge=1,
        description='The position of the idea shown to the judge as A.',
        examples=[3],
        json_schema_extra={"slot_uri": "seeker:first"},
    )
    second: int = Field(
        title="second",
        ge=1,
        description='The position of the idea shown to the judge as B.',
        examples=[7],
        json_schema_extra={"slot_uri": "seeker:second"},
    )
    verdicts: tuple[AxisVerdict, ...] = Field(
        default=(),
        title="verdicts",
        max_length=3,
        description='One verdict per score axis; empty when the comparison failed.',
        json_schema_extra={"slot_uri": "seeker:verdicts"},
    )
    failed: bool = Field(
        default=False,
        title="failed",
        description=(
            'True when the judge gave no valid answer even after a retry; ratings are '
            'unchanged.'
        ),
        examples=[False],
        json_schema_extra={"slot_uri": "seeker:failed"},
    )
    model: ModelId = Field(
        title="model",
        description='The Claude model the role runs on.',
        examples=["claude-haiku-5-5"],
        json_schema_extra={"slot_uri": "seeker:model"},
    )
    usage: Usage = Field(
        title="usage",
        description='Tokens consumed by the model calls this record accounts for.',
        json_schema_extra={"slot_uri": "seeker:usage"},
    )

    @model_validator(mode="after")
    def _verdicts_cover_the_pair(self) -> Comparison:
        if self.first == self.second:
            raise _invalid("pair", "a comparison is between two different ideas")
        if self.failed:
            if self.verdicts:
                raise _invalid("verdicts", "a failed comparison has no verdicts")
            return self
        if sorted(v.axis_name for v in self.verdicts) != sorted(ScoreAxis):
            raise _invalid("verdicts", "a comparison has exactly one verdict per score axis")
        if any(v.winner not in self.pair for v in self.verdicts):
            raise _invalid("winner", "every verdict's winner is one of the two ideas compared")
        return self

    @property
    def pair(self) -> tuple[int, int]:
        return (self.first, self.second)

    def verdict_on(self, axis: ScoreAxis) -> AxisVerdict | None:
        return next((v for v in self.verdicts if v.axis_name is axis), None)


class Rating(SeekerModel):
    """One idea's Elo rating on one score axis."""

    model_config = ConfigDict(title="Rating", json_schema_extra={"class_uri": "seeker:Rating"})

    position: int = Field(
        title="position",
        ge=1,
        description="The draw's 1-based position within its batch.",
        examples=[1],
        json_schema_extra={"slot_uri": "seeker:position"},
    )
    axis_name: ScoreAxis = Field(
        title="axis_name",
        description='The score axis this verdict or rating is on.',
        examples=["promise"],
        json_schema_extra={"slot_uri": "seeker:axisName"},
    )
    rating: float = Field(
        title="rating",
        description='The Elo rating on this axis after every comparison so far.',
        examples=[1532.0],
        json_schema_extra={"slot_uri": "seeker:rating"},
    )
    wins: int = Field(
        title="wins",
        ge=0,
        description='Comparisons won on this axis.',
        examples=[4],
        json_schema_extra={"slot_uri": "seeker:wins"},
    )
    losses: int = Field(
        title="losses",
        ge=0,
        description='Comparisons lost on this axis.',
        examples=[2],
        json_schema_extra={"slot_uri": "seeker:losses"},
    )


class Tournament(SeekerModel):
    """The ranking of a run's debated ideas: the comparisons made, the per-axis Elo
    ratings they produce, and the survivors."""

    model_config = ConfigDict(title="Tournament", json_schema_extra={"class_uri": "seeker:Tournament"})

    k_factor: float = Field(
        title="k_factor",
        ge=0,
        description='How far one comparison moves a rating (the Elo K).',
        examples=[32.0],
        json_schema_extra={"slot_uri": "seeker:kFactor"},
    )
    initial_rating: float = Field(
        title="initial_rating",
        description='The rating every entrant starts at, on every axis.',
        examples=[1500.0],
        json_schema_extra={"slot_uri": "seeker:initialRating"},
    )
    max_comparisons: int = Field(
        title="max_comparisons",
        ge=1,
        description='The most comparisons the tournament may schedule.',
        examples=[66],
        json_schema_extra={"slot_uri": "seeker:maxComparisons"},
    )
    entrants: tuple[int, ...] = Field(
        default=(),
        title="entrants",
        description='The positions of the ideas that competed, in position order.',
        examples=[[1, 2, 3]],
        json_schema_extra={"slot_uri": "seeker:entrants"},
    )
    comparisons: tuple[Comparison, ...] = Field(
        default=(),
        title="comparisons",
        description='The comparisons made, in schedule order.',
        json_schema_extra={"slot_uri": "seeker:comparisons"},
    )
    ratings: tuple[Rating, ...] = Field(
        default=(),
        title="ratings",
        description='One rating per entrant per axis, recomputable from the comparisons.',
        json_schema_extra={"slot_uri": "seeker:ratings"},
    )
    survivors: tuple[int, ...] = Field(
        default=(),
        title="survivors",
        description='The positions of the top entrants by promise, best first.',
        examples=[[3, 7, 11]],
        json_schema_extra={"slot_uri": "seeker:survivors"},
    )
    skipped: bool = Field(
        default=False,
        title="skipped",
        description=(
            'True when fewer than two ideas could compete, so no comparison was made.'
        ),
        examples=[False],
        json_schema_extra={"slot_uri": "seeker:skipped"},
    )

    SURVIVOR_COUNT: ClassVar[int] = 3

    @model_validator(mode="after")
    def _positions_are_entrants(self) -> Tournament:
        entrants = set(self.entrants)
        if len(entrants) != len(self.entrants):
            raise _invalid("entrants", "each idea enters a tournament once")
        if not set(self.survivors) <= entrants or len(self.survivors) > self.SURVIVOR_COUNT:
            raise _invalid("survivors", "survivors are at most three of the entrants")
        if any(r.position not in entrants for r in self.ratings):
            raise _invalid("ratings", "ratings are only for entrants")
        if any(c.first not in entrants or c.second not in entrants for c in self.comparisons):
            raise _invalid("comparisons", "comparisons are only between entrants")
        if self.skipped and (self.comparisons or self.survivors):
            raise _invalid("skipped", "a skipped tournament has no comparisons and no survivors")
        return self

    def rating_of(self, position: int, axis: ScoreAxis) -> Rating | None:
        return next((r for r in self.ratings if r.position == position and r.axis_name is axis), None)
