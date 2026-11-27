"""RunLog: records with their files, rewriting in place, and the lookups that skip discarded
records (pin-schedule-workspace 2.1, 2.2)."""

from datetime import datetime, timedelta
from pathlib import Path

from seeker.ontology import ScheduledRun, ScheduleOutcome
from seeker.schedule.cadence import Cadence
from seeker.schedule.log import RunLog

ROUND_4 = (
    "generations/2026-11-24-round-4-literal.yaml",
    "debates/2026-11-24-round-4-literal.yaml",
    "reports/2026-11-24-round-4-literal.md",
)
DUPLICATE = tuple(path.replace("11-24", "11-26") for path in ROUND_4)


def at(day: int, hour: int = 2) -> datetime:
    return datetime(2026, 11, day, hour, 0).astimezone()


def trigger(day: int, outcome: str = "advanced", paths: tuple[str, ...] = (), **extra: object) -> ScheduledRun:
    return ScheduledRun(
        started_at=at(day), ended_at=at(day) + timedelta(minutes=30), schedule_outcome=outcome,
        written_paths=paths, budget_usd=5.0, estimated_cost_usd=4.0 if paths else 0.0, **extra,
    )


def history(tmp_path: Path) -> RunLog:
    """The real sequence: 11-24 advanced round 4, 11-25 too soon, 11-26 advanced a duplicate."""
    log = RunLog(tmp_path / "runs")
    log.write(trigger(26, paths=DUPLICATE))
    log.write(trigger(24, paths=ROUND_4))
    log.write(trigger(25, "too_soon"))
    return log


def test_records_come_back_oldest_first_with_their_files(tmp_path: Path) -> None:
    records = history(tmp_path).all()
    assert [r.run.started_at.day for r in records] == [24, 25, 26]
    assert [r.path.name for r in records] == [f"{r.run.started_at:%Y-%m-%dT%H%M%S}.yaml" for r in records]


def test_a_corrupt_record_is_still_skipped(tmp_path: Path) -> None:
    log = history(tmp_path)
    (log.folder / "broken.yaml").write_text("schedule_outcome: [unclosed")
    assert len(log.all()) == 3


def test_rewrite_keeps_the_file_name(tmp_path: Path) -> None:
    log = history(tmp_path)
    duplicate = log.all()[-1]
    dropped = duplicate.run.model_copy(update={"discarded_at": at(27, 9), "discard_note": "duplicate round 4"})
    assert log.rewrite(duplicate.model_copy(update={"run": dropped})) == duplicate.path
    assert sorted(p.name for p in log.folder.glob("*.yaml")) == sorted(r.path.name for r in log.all())
    assert log.read(duplicate.path).run == dropped


def test_lookups_skip_a_discarded_record(tmp_path: Path) -> None:
    log = history(tmp_path)
    assert log.last_with_outputs().run.written_paths == DUPLICATE
    assert log.last_advanced().started_at.day == 26
    duplicate = log.all()[-1]
    dropped = duplicate.run.model_copy(update={"discarded_at": at(27, 9), "discard_note": "duplicate round 4"})
    log.rewrite(duplicate.model_copy(update={"run": dropped}))
    assert log.last_with_outputs().run.written_paths == ROUND_4
    assert log.last_advanced().started_at.day == 24
    assert log.last().schedule_outcome is ScheduleOutcome.ADVANCED and log.last().discarded


def test_a_budget_stop_counts_as_outputs(tmp_path: Path) -> None:
    log = history(tmp_path)
    log.write(trigger(28, "budget", paths=("generations/2026-11-28-round-5-literal.yaml",)))
    assert log.last_with_outputs().run.schedule_outcome is ScheduleOutcome.BUDGET
    assert log.last_advanced().started_at.day == 26


def test_no_records_means_no_outputs_to_check(tmp_path: Path) -> None:
    log = RunLog(tmp_path / "runs")
    assert log.all() == () and log.last_with_outputs() is None and log.last_advanced() is None


def test_a_discarded_round_does_not_hold_back_the_next(tmp_path: Path) -> None:
    """Spec scenario: 11-24 advanced, 11-26 advanced and was discarded; 11-27 at 02:00 is due."""
    log = history(tmp_path)
    cadence = Cadence(days=2)
    last = log.last_advanced()
    assert not cadence.due(last.ended_at, at(27))
    duplicate = log.all()[-1]
    dropped = duplicate.run.model_copy(update={"discarded_at": at(26, 12), "discard_note": "duplicate round 4"})
    log.rewrite(duplicate.model_copy(update={"run": dropped}))
    assert cadence.due(log.last_advanced().ended_at, at(27))
