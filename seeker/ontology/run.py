"""The debate-run classes from schema/seeker.yaml: ``RoleDigest`` and
``DebateRun``, and the ``StopReason`` enum."""

from __future__ import annotations

from datetime import datetime

from pydantic import ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

from seeker.ontology.base import DescribedStrEnum, SeekerModel
from seeker.ontology.debate import Debate, DebateFailure
from seeker.ontology.generation import Usage
from seeker.ontology.reading import RoleName
from seeker.ontology.tournament import Tournament
from seeker.ontology.types import GitCommit, Sha256Digest


class StopReason(DescribedStrEnum):
    """Why a debate run stopped before or after finishing."""

    FINISHED = "finished", "Every debate and comparison is done."
    BUDGET = "budget", "The run's estimated spend reached its budget; it can be resumed with more."
    NO_TOURNAMENT = "no_tournament", "The run was asked to debate only and stopped before the tournament."


class RoleDigest(SeekerModel):
    """The digest of one role file a run used."""

    model_config = ConfigDict(title="RoleDigest", json_schema_extra={"class_uri": "seeker:RoleDigest"})

    role_name: RoleName = Field(
        title="role_name",
        description='Which role in the pipeline this is.',
        examples=["skeptic"],
        json_schema_extra={"slot_uri": "seeker:roleName"},
    )
    role_digest: Sha256Digest = Field(
        title="role_digest",
        description="SHA-256 of the role file's bytes, so any prompt edit is visible.",
        examples=["41909d46fec8a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a"],
        json_schema_extra={"slot_uri": "seeker:roleDigest"},
    )


class DebateRun(SeekerModel):
    """One debate over a recorded generation: its pinned inputs, every debate and
    failure, the tournament, and its usage and estimated cost."""

    model_config = ConfigDict(title="DebateRun", json_schema_extra={"class_uri": "seeker:DebateRun"})

    generation_path: str = Field(
        title="generation_path",
        min_length=1,
        description=(
            'The generation record debated, relative to the repository root when inside it.'
        ),
        examples=["generations/2026-11-04-round-1-literal.yaml"],
        json_schema_extra={"slot_uri": "seeker:generationPath"},
    )
    generation_digest: Sha256Digest = Field(
        title="generation_digest",
        description=(
            "SHA-256 of the generation record's bytes, so a changed input is caught on "
            'resume.'
        ),
        examples=["41909d46fec8a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a"],
        json_schema_extra={"slot_uri": "seeker:generationDigest"},
    )
    role_digests: tuple[RoleDigest, ...] = Field(
        title="role_digests",
        min_length=5, max_length=5,
        description='The digest of every debate role file the run used.',
        json_schema_extra={"slot_uri": "seeker:roleDigests"},
    )
    catalog_digest: Sha256Digest = Field(
        title="catalog_digest",
        description=(
            'Digest of the works catalog when the run started. It may change during the run, '
            "because the prosecutor's finds are added to the catalog."
        ),
        examples=["41909d46fec8a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a"],
        json_schema_extra={"slot_uri": "seeker:catalogDigest"},
    )
    git_commit: GitCommit | None = Field(
        default=None,
        title="git_commit",
        description='The repository commit the generation ran from, when known.',
        examples=["5085562a1b2c3d4e5f60718293a4b5c6d7e8f90a"],
        json_schema_extra={"slot_uri": "seeker:gitCommit"},
    )
    tournament_seed: int = Field(
        title="tournament_seed",
        ge=0,
        description=(
            'The integer that pairings, A/B order and objection order are derived from.'
        ),
        examples=[7],
        json_schema_extra={"slot_uri": "seeker:tournamentSeed"},
    )
    started_at: datetime = Field(
        title="started_at",
        description='When the run first started.',
        examples=["2026-11-12T22:00:00Z"],
        json_schema_extra={"slot_uri": "seeker:startedAt"},
    )
    budget_usd: float = Field(
        title="budget_usd",
        ge=0,
        description='The estimated spend at which the run stops cleanly, in US dollars.',
        examples=[5.0],
        json_schema_extra={"slot_uri": "seeker:budgetUsd"},
    )
    stop_reason: StopReason | None = Field(
        default=None,
        title="stop_reason",
        description='Why the run last stopped; absent while it is running.',
        examples=["budget"],
        json_schema_extra={"slot_uri": "seeker:stopReason"},
    )
    debates: tuple[Debate, ...] = Field(
        default=(),
        title="debates",
        description='The finished debates, in position order.',
        json_schema_extra={"slot_uri": "seeker:debates"},
    )
    debate_failures: tuple[DebateFailure, ...] = Field(
        default=(),
        title="debate_failures",
        description='Roles that produced no valid answer, in position then role order.',
        json_schema_extra={"slot_uri": "seeker:debateFailures"},
    )
    tournament: Tournament | None = Field(
        default=None,
        title="tournament",
        description='The ranking of the debated ideas, once it has started.',
        json_schema_extra={"slot_uri": "seeker:tournament"},
    )
    usage: Usage = Field(
        title="usage",
        description='Tokens consumed by the model calls this record accounts for.',
        json_schema_extra={"slot_uri": "seeker:usage"},
    )
    estimated_cost_usd: float = Field(
        title="estimated_cost_usd",
        ge=0,
        description=(
            'The total usage priced with the configured price table. It is an estimate, '
            'because prices change and are kept as data.'
        ),
        examples=[2.84],
        json_schema_extra={"slot_uri": "seeker:estimatedCostUsd"},
    )

    @model_validator(mode="after")
    def _one_digest_per_debate_role(self) -> DebateRun:
        roles = [d.role_name for d in self.role_digests]
        if len(set(roles)) != len(roles) or RoleName.GENERATOR in roles:
            raise PydanticCustomError("role_digests", "one digest per debate role, and none for the generator")
        positions = [d.position for d in self.debates]
        if positions != sorted(set(positions)):
            raise PydanticCustomError("debates", "debates are unique and in position order")
        return self

    def digest_of(self, role: RoleName) -> Sha256Digest | None:
        return next((d.role_digest for d in self.role_digests if d.role_name is role), None)

    def debate_at(self, position: int) -> Debate | None:
        return next((d for d in self.debates if d.position == position), None)
