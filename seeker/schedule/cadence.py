"""How often the scheduled run may advance a round."""

from __future__ import annotations

from datetime import datetime, timedelta

from pydantic import ConfigDict, Field

from seeker.ontology import SeekerModel

SLACK = timedelta(hours=12)


class Cadence(SeekerModel):
    """A round is due once the last advanced round ended ``days`` days ago, less 12 hours of slack.

    The slack keeps a round that ended at 03:10 from pushing the next one, two days later at
    02:00, back by a further day."""

    model_config = ConfigDict(title="Cadence")

    days: int = Field(ge=1, description="Days between rounds.")

    @property
    def gap(self) -> timedelta:
        return timedelta(days=self.days) - SLACK

    def due_at(self, last_advanced: datetime | None) -> datetime | None:
        """When the next round may start; None when no round has advanced yet (due now)."""
        return None if last_advanced is None else last_advanced + self.gap

    def due(self, last_advanced: datetime | None, now: datetime) -> bool:
        due_at = self.due_at(last_advanced)
        return due_at is None or now >= due_at
