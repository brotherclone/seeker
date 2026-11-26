"""The lineage head, the round in progress and the review gate, from records only (scheduled-run 4.2)."""

import hashlib
import shutil
from datetime import datetime
from pathlib import Path

import pytest
import yaml

from seeker.config import SeekerConfig
from seeker.ontology import Reading, ReviewSignOff
from seeker.schedule.lineage import LineageRecords, NoHead, TwoHeads
from tests.schedule_fixtures import workspace

ROUND_3 = "debates/2026-11-23-round-3-literal.yaml"


@pytest.fixture(autouse=True)
def no_vault_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SEEKER_VAULT", raising=False)


def records(config: Path) -> LineageRecords:
    return LineageRecords(SeekerConfig.load(config))


def sign_off(tmp_path: Path, label: str = ROUND_3) -> None:
    digest = hashlib.sha256((tmp_path / label).read_bytes()).hexdigest()
    signed = ReviewSignOff(reviewed_run_path=label, reviewed_run_digest=digest, signed_at=datetime(2026, 11, 24, 9))
    (tmp_path / "reviews").mkdir(exist_ok=True)
    (tmp_path / "reviews" / "round-3.yaml").write_text(yaml.safe_dump(signed.model_dump(mode="json")))


def test_head_after_round_three(tmp_path: Path) -> None:
    state = records(workspace(tmp_path)).state()
    assert state.head.label == ROUND_3
    assert state.head.round == 3 and state.head.reading is Reading.LITERAL
    assert state.in_progress is None and not state.report_missing


def test_two_heads_are_named(tmp_path: Path) -> None:
    config = workspace(tmp_path)
    shutil.copy(tmp_path / ROUND_3, tmp_path / "debates" / "copy-of-round-3.yaml")
    with pytest.raises(TwoHeads) as raised:
        records(config).head()
    assert set(raised.value.labels) == {ROUND_3, "debates/copy-of-round-3.yaml"}


def test_scratch_records_are_ignored(tmp_path: Path) -> None:
    config = workspace(tmp_path)
    (tmp_path / "debates" / "scratch").mkdir()
    shutil.copy(tmp_path / ROUND_3, tmp_path / "debates" / "scratch" / "copy.yaml")
    assert records(config).head().label == ROUND_3


def test_no_finished_run(tmp_path: Path) -> None:
    config = workspace(tmp_path, rounds=0)
    with pytest.raises(NoHead):
        records(config).head()


def test_unfinished_runs_are_not_heads(tmp_path: Path) -> None:
    config = workspace(tmp_path)
    raw = yaml.safe_load((tmp_path / ROUND_3).read_text())
    raw["stop_reason"] = "budget"
    (tmp_path / ROUND_3).write_text(yaml.safe_dump(raw, sort_keys=False))
    state = records(config).state()
    assert state.head.round == 2
    assert state.in_progress == tmp_path / "generations" / "2026-11-23-round-3-literal.yaml"
    assert state.in_progress_run == tmp_path / ROUND_3


def test_a_mutated_generation_without_a_run_is_in_progress(tmp_path: Path) -> None:
    config = workspace(tmp_path)
    (tmp_path / ROUND_3).unlink()
    state = records(config).state()
    assert state.head.label == "debates/2026-11-16-round-2-literal.yaml"
    assert state.in_progress == tmp_path / "generations" / "2026-11-23-round-3-literal.yaml"
    assert state.in_progress_run is None


def test_missing_report(tmp_path: Path) -> None:
    config = workspace(tmp_path)
    (tmp_path / "reports" / "2026-11-23-round-3-literal.md").unlink()
    assert records(config).state().report_missing


def test_gate_closed_without_a_sign_off(tmp_path: Path) -> None:
    state = records(workspace(tmp_path)).state()
    assert state.at_review_point and not state.signed_off and state.awaiting_review


def test_gate_open_with_a_matching_sign_off(tmp_path: Path) -> None:
    config = workspace(tmp_path)
    sign_off(tmp_path)
    state = records(config).state()
    assert state.signed_off and not state.awaiting_review


def test_gate_closes_again_when_the_run_changes(tmp_path: Path) -> None:
    config = workspace(tmp_path)
    sign_off(tmp_path)
    with (tmp_path / ROUND_3).open("a") as handle:
        handle.write("\n# edited after sign-off\n")
    assert records(config).state().awaiting_review


def test_no_gate_between_review_points(tmp_path: Path) -> None:
    config = workspace(tmp_path, rounds=2)
    state = records(config).state()
    assert state.head.round == 2 and not state.at_review_point and not state.awaiting_review


def test_review_every_comes_from_config(tmp_path: Path) -> None:
    config = workspace(tmp_path, rounds=2, extra_config="\n")
    text = config.read_text().replace("review_every: 3", "review_every: 2")
    config.write_text(text)
    assert records(config).state().awaiting_review
