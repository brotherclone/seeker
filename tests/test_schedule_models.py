"""Unit tests for the scheduling ontology: ScheduledRun, ReviewSignOff,
ScheduleOutcome, and the optional Generation.stop_reason slot."""

from datetime import datetime
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from seeker.ontology import Generation, ReviewSignOff, ScheduledRun, ScheduleOutcome, StopReason

ROOT = Path(__file__).resolve().parent.parent
DIGEST = "d" * 64
WHEN = datetime(2026, 11, 25, 2, 0)


def test_scheduled_run_round_trips_through_yaml() -> None:
    run = ScheduledRun(
        started_at=WHEN,
        ended_at=WHEN.replace(hour=3),
        schedule_outcome="advanced",
        head_run_path="debates/2026-11-23-round-3-literal.yaml",
        head_round=3,
        written_paths=("generations/2026-11-25-round-4-literal.yaml",),
        budget_usd=5.0,
        estimated_cost_usd=3.4,
    )
    again = ScheduledRun.model_validate(yaml.safe_load(yaml.safe_dump(run.model_dump(mode="json"))))
    assert again == run
    assert again.schedule_outcome is ScheduleOutcome.ADVANCED


def test_a_skipped_trigger_needs_no_head() -> None:
    run = ScheduledRun(
        started_at=WHEN, ended_at=WHEN, schedule_outcome="locked", budget_usd=5.0, estimated_cost_usd=0.0
    )
    assert run.head_run_path is None and run.written_paths == ()


def test_head_round_starts_at_one() -> None:
    with pytest.raises(ValidationError):
        ScheduledRun(
            started_at=WHEN, ended_at=WHEN, schedule_outcome="failed", head_round=0,
            budget_usd=5.0, estimated_cost_usd=0.0,
        )


@pytest.mark.parametrize(
    ("outcome", "did_work"),
    [("advanced", True), ("budget", True), ("awaiting_review", True), ("failed", True),
     ("too_soon", False), ("locked", False)],
)
def test_which_outcomes_did_work(outcome: str, did_work: bool) -> None:
    assert ScheduleOutcome(outcome).did_work is did_work


def test_sign_off_approves_only_the_exact_run() -> None:
    signed = ReviewSignOff(reviewed_run_path="debates/r3.yaml", reviewed_run_digest=DIGEST, signed_at=WHEN)
    assert signed.approves("debates/r3.yaml", DIGEST)
    assert not signed.approves("debates/r3.yaml", "e" * 64)
    assert not signed.approves("debates/r4.yaml", DIGEST)


def test_sign_off_rejects_a_bad_digest() -> None:
    with pytest.raises(ValidationError):
        ReviewSignOff(reviewed_run_path="debates/r3.yaml", reviewed_run_digest="nope", signed_at=WHEN)


@pytest.mark.parametrize("path", sorted((ROOT / "generations").glob("*.yaml")), ids=lambda p: p.name)
def test_recorded_generations_load_without_stop_reason(path: Path) -> None:
    generation = Generation.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    assert generation.stop_reason is None


def test_generation_accepts_a_budget_stop() -> None:
    path = ROOT / "generations" / "2026-11-16-round-2-literal.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    stopped = Generation.model_validate({**raw, "stop_reason": "budget"})
    assert stopped.stop_reason is StopReason.BUDGET
