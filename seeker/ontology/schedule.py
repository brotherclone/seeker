"""The scheduling classes from schema/seeker.yaml: ``ScheduledRun`` and
``ReviewSignOff``, and the ``ScheduleOutcome`` enum."""

from __future__ import annotations

from datetime import datetime

from pydantic import ConfigDict, Field

from seeker.ontology.base import DescribedStrEnum, SeekerModel
from seeker.ontology.types import Sha256Digest


class ScheduleOutcome(DescribedStrEnum):
    """How one trigger of the scheduled run ended."""

    ADVANCED = "advanced", "A round finished and its report was written."
    BUDGET = "budget", "The trigger reached its spend cap; the round resumes at the next trigger."
    TOO_SOON = "too_soon", "The last advanced round is more recent than the cadence allows; nothing ran."
    AWAITING_REVIEW = "awaiting_review", "The lineage head is at a review point with no sign-off; nothing ran."
    LOCKED = "locked", "Another scheduled run held the lock; nothing ran."
    FAILED = "failed", "The trigger stopped on an error, which it records."

    @property
    def did_work(self) -> bool:
        """Whether the trigger got past its checks, so it deserves a vault note."""
        return self not in (ScheduleOutcome.TOO_SOON, ScheduleOutcome.LOCKED)


class ScheduledRun(SeekerModel):
    """One trigger of the scheduled job: the lineage head it found, how it
    ended, the files it wrote and what it cost."""

    model_config = ConfigDict(title="ScheduledRun", json_schema_extra={"class_uri": "seeker:ScheduledRun"})

    started_at: datetime = Field(
        title="started_at",
        description="When the run first started.",
        examples=["2026-11-25T02:00:00"],
        json_schema_extra={"slot_uri": "seeker:startedAt"},
    )
    ended_at: datetime = Field(
        title="ended_at",
        description="When the trigger finished, whatever its outcome.",
        examples=["2026-11-25T03:12:40"],
        json_schema_extra={"slot_uri": "seeker:endedAt"},
    )
    schedule_outcome: ScheduleOutcome = Field(
        title="schedule_outcome",
        description="How the trigger ended.",
        examples=["advanced"],
        json_schema_extra={"slot_uri": "seeker:scheduleOutcome"},
    )
    head_run_path: str | None = Field(
        default=None,
        title="head_run_path",
        description=(
            "The lineage head the trigger started from, relative to the repository root when inside it. "
            "Absent when the trigger failed before finding one."
        ),
        examples=["debates/2026-11-23-round-3-literal.yaml"],
        json_schema_extra={"slot_uri": "seeker:headRunPath"},
    )
    head_round: int | None = Field(
        default=None,
        title="head_round",
        ge=1,
        description="The round of the lineage head the trigger started from.",
        examples=[3],
        json_schema_extra={"slot_uri": "seeker:headRound"},
    )
    written_paths: tuple[str, ...] = Field(
        default=(),
        title="written_paths",
        description=(
            "The generation, debate run and report files the trigger wrote or resumed, relative to the "
            "repository root when inside it."
        ),
        examples=[("generations/2026-11-25-round-4-literal.yaml",)],
        json_schema_extra={"slot_uri": "seeker:writtenPaths"},
    )
    budget_usd: float = Field(
        title="budget_usd",
        ge=0,
        description="The estimated spend at which the run stops cleanly, in US dollars.",
        examples=[5.0],
        json_schema_extra={"slot_uri": "seeker:budgetUsd"},
    )
    estimated_cost_usd: float = Field(
        title="estimated_cost_usd",
        ge=0,
        description=(
            "The total usage priced with the configured price table. It is an estimate, "
            "because prices change and are kept as data."
        ),
        examples=[3.42],
        json_schema_extra={"slot_uri": "seeker:estimatedCostUsd"},
    )
    failure_message: str | None = Field(
        default=None,
        title="failure_message",
        description=(
            "What went wrong, for a failed trigger, or a problem that did not stop it, such as a vault "
            "note that could not be written."
        ),
        examples=["no API key: set ANTHROPIC_API_KEY in the environment"],
        json_schema_extra={"slot_uri": "seeker:failureMessage"},
    )


class ReviewSignOff(SeekerModel):
    """Gabe's sign-off on a lineage head at a review point, pinned by the
    run's digest, which lets the scheduled run advance past it."""

    model_config = ConfigDict(title="ReviewSignOff", json_schema_extra={"class_uri": "seeker:ReviewSignOff"})

    reviewed_run_path: str = Field(
        title="reviewed_run_path",
        min_length=1,
        description="The debate run signed off, relative to the repository root when inside it.",
        examples=["debates/2026-11-23-round-3-literal.yaml"],
        json_schema_extra={"slot_uri": "seeker:reviewedRunPath"},
    )
    reviewed_run_digest: Sha256Digest = Field(
        title="reviewed_run_digest",
        description=(
            "SHA-256 of the signed-off run's bytes, so a sign-off stops counting if the run changes afterwards."
        ),
        examples=["41909d46fec8a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a"],
        json_schema_extra={"slot_uri": "seeker:reviewedRunDigest"},
    )
    signed_at: datetime = Field(
        title="signed_at",
        description="When the sign-off was recorded.",
        examples=["2026-11-24T09:30:00"],
        json_schema_extra={"slot_uri": "seeker:signedAt"},
    )
    review_note: str | None = Field(
        default=None,
        title="review_note",
        description="What the reviewer wanted remembered about the review, if anything.",
        examples=["keep the obscura line"],
        json_schema_extra={"slot_uri": "seeker:reviewNote"},
    )

    def approves(self, path: str, digest: Sha256Digest) -> bool:
        """Whether this sign-off covers the run at ``path`` with these exact bytes."""
        return self.reviewed_run_path == path and self.reviewed_run_digest == digest
