"""The cadence check with 12 hours of slack (scheduled-run 4.3)."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from seeker.schedule.cadence import Cadence

MONDAY_RUN_ENDED = datetime(2026, 11, 23, 3, 10)
TUESDAY_2AM = datetime(2026, 11, 24, 2, 0)
WEDNESDAY_2AM = datetime(2026, 11, 25, 2, 0)


def test_every_other_day() -> None:
    cadence = Cadence(days=2)
    assert not cadence.due(MONDAY_RUN_ENDED, TUESDAY_2AM)  # 22h 50m
    assert cadence.due(MONDAY_RUN_ENDED, WEDNESDAY_2AM)  # 46h 50m
    assert cadence.due_at(MONDAY_RUN_ENDED) == datetime(2026, 11, 24, 15, 10)


def test_first_run_is_due() -> None:
    assert Cadence(days=2).due(None, TUESDAY_2AM)
    assert Cadence(days=2).due_at(None) is None


def test_daily_cadence_runs_the_next_night() -> None:
    assert Cadence(days=1).due(MONDAY_RUN_ENDED, TUESDAY_2AM)


def test_a_long_run_still_keeps_the_rhythm() -> None:
    ended_late = datetime(2026, 11, 23, 13, 59)  # a run that woke late and ran long
    assert Cadence(days=2).due(ended_late, WEDNESDAY_2AM)


def test_cadence_is_at_least_a_day() -> None:
    with pytest.raises(ValidationError):
        Cadence(days=0)
