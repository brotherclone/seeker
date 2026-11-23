"""The ``StopReason`` enum from schema/seeker.yaml, shared by debate runs and generations."""

from __future__ import annotations

from seeker.ontology.base import DescribedStrEnum


class StopReason(DescribedStrEnum):
    """Why a debate run stopped before or after finishing."""

    FINISHED = "finished", "Every debate and comparison is done."
    BUDGET = "budget", "The run's estimated spend reached its budget; it can be resumed with more."
    NO_TOURNAMENT = "no_tournament", "The run was asked to debate only and stopped before the tournament."
