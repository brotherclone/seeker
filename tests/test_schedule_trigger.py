"""Scheduler.trigger end to end: records, lock, gate, cadence and the vault note (scheduled-run 4.5, 4.6)."""

import hashlib
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import yaml

from seeker.config import SeekerConfig
from seeker.models import ScriptedModel
from seeker.ontology import ReviewSignOff, ScheduledRun, ScheduleOutcome
from seeker.schedule.log import RunLock, RunLog
from seeker.schedule.trigger import Scheduler
from test_debate_cli import judgment
from test_debate_runner import one_round
from tests.schedule_fixtures import workspace
from tests.test_schedule_round import JUDGMENTS, children

NOW = datetime(2026, 11, 25, 2, 0).astimezone()
ROUND_3 = "debates/2026-11-23-round-3-literal.yaml"


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SEEKER_VAULT", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


@pytest.fixture
def config(tmp_path: Path) -> SeekerConfig:
    return SeekerConfig.load(workspace(tmp_path))


def sign_off(config: SeekerConfig, label: str = ROUND_3) -> None:
    digest = hashlib.sha256((config.root / label).read_bytes()).hexdigest()
    signed = ReviewSignOff(reviewed_run_path=label, reviewed_run_digest=digest, signed_at=NOW)
    config.paths.reviews.mkdir(parents=True, exist_ok=True)
    (config.paths.reviews / "r3.yaml").write_text(yaml.safe_dump(signed.model_dump(mode="json")))


def advanced_at(config: SeekerConfig, ended: datetime) -> None:
    RunLog(config.paths.runs).write(
        ScheduledRun(
            started_at=ended - timedelta(hours=1), ended_at=ended, schedule_outcome="advanced",
            budget_usd=5.0, estimated_cost_usd=3.0,
        )
    )


def notes(config: SeekerConfig) -> list[Path]:
    folder = config.vault().runs
    return sorted(folder.glob("*.md")) if folder.is_dir() else []


# -- gate and cadence ---------------------------------------------------------------------


def test_round_three_waits_for_review(config: SeekerConfig) -> None:
    model = ScriptedModel(())
    record = Scheduler(config, model).trigger(NOW)
    assert record.schedule_outcome is ScheduleOutcome.AWAITING_REVIEW
    assert record.head_run_path == ROUND_3 and record.head_round == 3 and record.estimated_cost_usd == 0
    assert model.requests == []
    assert RunLog(config.paths.runs).last() == record
    (note,) = notes(config)
    text = note.read_text()
    assert note.name == "2026-11-25 0200 round-3 awaiting_review.md"
    assert "type: note" in text and "outcome: awaiting_review" in text and "[[Seeker]]" in text
    assert f"uv run seeker-schedule approve {ROUND_3}" in text
    assert "## Survivors" in text and "reports/2026-11-23-round-3-literal.md" in text


def test_too_soon_writes_a_record_but_no_note(config: SeekerConfig) -> None:
    sign_off(config)
    advanced_at(config, NOW - timedelta(hours=22, minutes=50))
    model = ScriptedModel(())
    record = Scheduler(config, model).trigger(NOW)
    assert record.schedule_outcome is ScheduleOutcome.TOO_SOON and model.requests == []
    assert notes(config) == []
    assert len(RunLog(config.paths.runs).all()) == 2


def test_locked_trigger_makes_no_call_and_no_note(config: SeekerConfig) -> None:
    held = RunLock(config.paths.runs)
    assert held.acquire()
    try:
        model = ScriptedModel(())
        record = Scheduler(config, model).trigger(NOW)
    finally:
        held.release()
    assert record.schedule_outcome is ScheduleOutcome.LOCKED and record.head_run_path is None
    assert model.requests == [] and notes(config) == []
    assert RunLog(config.paths.runs).last() == record


def test_a_dead_process_leaves_the_lock_free(config: SeekerConfig) -> None:
    script = (
        "import os, sys; from pathlib import Path; from seeker.schedule.log import RunLock; "
        "assert RunLock(Path(sys.argv[1])).acquire(); os._exit(0)"
    )
    subprocess.run([sys.executable, "-c", script, str(config.paths.runs)], check=True)
    lock = RunLock(config.paths.runs)
    assert lock.acquire()
    lock.release()


# -- failures -----------------------------------------------------------------------------


def test_missing_key_is_recorded_as_failed(config: SeekerConfig) -> None:
    sign_off(config)
    record = Scheduler(config).trigger(NOW)
    assert record.schedule_outcome is ScheduleOutcome.FAILED
    assert "no API key" in record.failure_message and record.head_round == 3
    assert RunLog(config.paths.runs).last() == record
    (note,) = notes(config)
    assert "failed" in note.name and "no API key" in note.read_text()


def test_two_heads_are_recorded_as_failed(config: SeekerConfig) -> None:
    (config.root / "debates" / "copy.yaml").write_bytes((config.root / ROUND_3).read_bytes())
    model = ScriptedModel(())
    record = Scheduler(config, model).trigger(NOW)
    assert record.schedule_outcome is ScheduleOutcome.FAILED and record.head_run_path is None
    assert ROUND_3 in record.failure_message and "debates/copy.yaml" in record.failure_message
    assert model.requests == []


def test_a_missing_vault_does_not_fail_the_trigger(config: SeekerConfig) -> None:
    config.vault().root.parent.mkdir(parents=True, exist_ok=True)
    config.vault().root.write_text("not a folder")
    record = Scheduler(config, ScriptedModel(())).trigger(NOW)
    assert record.schedule_outcome is ScheduleOutcome.AWAITING_REVIEW
    assert record.failure_message.startswith("vault note not written")


def test_a_missing_head_report_is_rendered_first(config: SeekerConfig) -> None:
    report = config.paths.reports / "2026-11-23-round-3-literal.md"
    report.unlink()
    model = ScriptedModel(())
    record = Scheduler(config, model).trigger(NOW)
    assert report.is_file() and model.requests == []
    assert record.written_paths == ("reports/2026-11-23-round-3-literal.md",)


# -- the missing-output guard -------------------------------------------------------------

ROUND_3_OUTPUTS = (
    "generations/2026-11-23-round-3-literal.yaml",
    ROUND_3,
    "reports/2026-11-23-round-3-literal.md",
)


def wrote(config: SeekerConfig, ended: datetime, paths: tuple[str, ...], outcome: str = "advanced") -> Path:
    return RunLog(config.paths.runs).write(
        ScheduledRun(
            started_at=ended - timedelta(hours=1), ended_at=ended, schedule_outcome=outcome,
            written_paths=paths, budget_usd=5.0, estimated_cost_usd=4.0,
        )
    )


def generations(config: SeekerConfig) -> list[str]:
    return sorted(p.name for p in config.paths.generations.glob("*.yaml"))


def test_outputs_removed_by_a_branch_switch_stop_the_trigger(config: SeekerConfig) -> None:
    """The round-3 run left the disk, so the head would fall back to round 2 and redo round 3."""
    record_path = wrote(config, NOW - timedelta(days=3), ROUND_3_OUTPUTS)
    (config.root / ROUND_3).unlink()
    before = generations(config)
    model = ScriptedModel(())
    record = Scheduler(config, model).trigger(NOW)
    assert record.schedule_outcome is ScheduleOutcome.FAILED
    assert ROUND_3 in record.failure_message and "reports/" not in record.failure_message
    assert f"uv run seeker-schedule discard runs/{record_path.name}" in record.failure_message
    assert model.requests == [] and record.estimated_cost_usd == 0
    assert generations(config) == before and record.written_paths == ()
    (note,) = notes(config)
    assert "failed" in note.name and ROUND_3 in note.read_text()


def test_outputs_present_let_the_trigger_go_on(config: SeekerConfig) -> None:
    wrote(config, NOW - timedelta(hours=22), ROUND_3_OUTPUTS)
    record = Scheduler(config, ScriptedModel(())).trigger(NOW)
    assert record.schedule_outcome is ScheduleOutcome.AWAITING_REVIEW


def test_a_budget_stop_is_guarded_too(config: SeekerConfig) -> None:
    wrote(config, NOW - timedelta(days=1), ("generations/2026-11-24-round-4-literal.yaml",), outcome="budget")
    model = ScriptedModel(())
    record = Scheduler(config, model).trigger(NOW)
    assert record.schedule_outcome is ScheduleOutcome.FAILED and model.requests == []
    assert "generations/2026-11-24-round-4-literal.yaml" in record.failure_message


def test_a_discarded_record_is_not_guarded(config: SeekerConfig) -> None:
    path = wrote(config, NOW - timedelta(days=1), ("debates/2026-11-24-round-4-literal.yaml",))
    log = RunLog(config.paths.runs)
    kept = log.read(path)
    dropped = kept.run.model_copy(update={"discarded_at": NOW - timedelta(hours=2), "discard_note": "duplicate"})
    log.rewrite(kept.model_copy(update={"run": dropped}))
    record = Scheduler(config, ScriptedModel(())).trigger(NOW)
    assert record.schedule_outcome is ScheduleOutcome.AWAITING_REVIEW


# -- a real round -------------------------------------------------------------------------


def test_a_due_signed_off_round_advances_and_leaves_a_note(config: SeekerConfig) -> None:
    sign_off(config)
    advanced_at(config, NOW - timedelta(hours=46, minutes=50))
    model = ScriptedModel(children(config) + one_round() * 12 + tuple(judgment() for _ in range(JUDGMENTS)))
    record = Scheduler(config, model).trigger(NOW)
    assert record.schedule_outcome is ScheduleOutcome.ADVANCED, record.failure_message
    assert record.written_paths == (
        "generations/2026-11-25-round-4-literal.yaml",
        "debates/2026-11-25-round-4-literal.yaml",
        "reports/2026-11-25-round-4-literal.md",
    )
    assert 0 < record.estimated_cost_usd < 5
    (note,) = notes(config)
    text = note.read_text()
    assert note.name == "2026-11-25 0200 round-4 advanced.md"
    assert "Round 4 finished." in text and f"${record.estimated_cost_usd:.2f} of $5.00" in text
    assert text.count("**#") == 3 and "(promise " in text
    assert "prior-art search: 12 of 12 with results" in text
    assert "Report: `reports/2026-11-25-round-4-literal.md`" in text and "[[Seeker]]" in text

    # The next night is too soon, and the lineage now sits at round 4.
    again = Scheduler(config, ScriptedModel(())).trigger(NOW + timedelta(days=1))
    assert again.schedule_outcome is ScheduleOutcome.TOO_SOON and again.head_round == 4
