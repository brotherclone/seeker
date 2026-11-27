"""``seeker-schedule`` commands and the LaunchAgent plist (scheduled-run 5.1, 5.2)."""

import hashlib
import plistlib
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import yaml

from seeker.models import ScriptedModel
from seeker.ontology import ReviewSignOff, ScheduledRun
from seeker.schedule.cli import ScheduleCommand
from seeker.schedule.launchd import LABEL, Launchctl, LaunchctlResult
from seeker.schedule.log import RunLog
from tests.schedule_fixtures import workspace

ROUND_3 = "debates/2026-11-23-round-3-literal.yaml"
UV = Path("/opt/tools/bin/uv")


class FakeLaunchctl(Launchctl):
    """Records launchctl calls; an agent counts as loaded once bootstrapped."""

    def __init__(self) -> None:
        self.domain = "gui/501"
        self.calls: list[tuple[str, ...]] = []
        self.is_loaded = False

    def run(self, *args: str) -> LaunchctlResult:
        self.calls.append(args)
        if args[0] == "bootstrap":
            self.is_loaded = True
        elif args[0] == "bootout":
            self.is_loaded = False
        elif args[0] == "print":
            return LaunchctlResult(returncode=0 if self.is_loaded else 113)
        return LaunchctlResult(returncode=0)


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("SEEKER_VAULT", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("SEEKER_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def config(tmp_path: Path) -> Path:
    return workspace(tmp_path)


def command(tmp_path: Path, launchctl: FakeLaunchctl | None = None, model: ScriptedModel | None = None) -> ScheduleCommand:
    return ScheduleCommand(model=model, launchctl=launchctl or FakeLaunchctl(), agents_dir=tmp_path / "agents", uv=UV)


# -- status, run and approve ---------------------------------------------------------------


def test_status_needs_no_key_and_reports_the_gate(config: Path, tmp_path: Path, capsys) -> None:
    assert command(tmp_path).run(["--config", str(config), "status"]) == 0
    out = capsys.readouterr().out
    assert f"head: {ROUND_3} (round 3, literal)" in out
    assert "awaiting review at round 3" in out and f"uv run seeker-schedule approve {ROUND_3}" in out
    assert "next round: due after sign-off" in out and "launch agent: not loaded" in out


def test_run_exits_zero_when_waiting_or_too_soon(config: Path, tmp_path: Path, capsys) -> None:
    model = ScriptedModel(())
    assert command(tmp_path, model=model).run(["--config", str(config), "run"]) == 0
    assert "awaiting_review from debates/2026-11-23-round-3-literal.yaml (round 3)" in capsys.readouterr().out
    assert model.requests == []


def test_run_exits_one_when_failed(config: Path, tmp_path: Path, capsys) -> None:
    assert command(tmp_path).run(["--config", str(config), "approve", ROUND_3]) == 0
    assert command(tmp_path).run(["--config", str(config), "run"]) == 1
    assert "no API key" in capsys.readouterr().err


def advanced_record(tmp_path: Path, paths: tuple[str, ...], day: int = 24) -> Path:
    started = datetime(2026, 11, day, 2, 0).astimezone()
    return RunLog(tmp_path / "runs").write(
        ScheduledRun(
            started_at=started, ended_at=started + timedelta(minutes=30), schedule_outcome="advanced",
            written_paths=paths, budget_usd=5.0, estimated_cost_usd=4.6,
        )
    )


def test_status_shows_a_missing_output_failure(config: Path, tmp_path: Path, capsys) -> None:
    """Spec: the morning after, status shows the missing paths and the discard command."""
    record = advanced_record(tmp_path, ("debates/2026-11-24-round-4-literal.yaml",))
    model = ScriptedModel(())
    assert command(tmp_path, model=model).run(["--config", str(config), "run"]) == 1
    assert model.requests == []
    capsys.readouterr()
    assert command(tmp_path).run(["--config", str(config), "status"]) == 0
    out = capsys.readouterr().out
    assert "failed" in out and "debates/2026-11-24-round-4-literal.yaml" in out
    assert f"uv run seeker-schedule discard runs/{record.name}" in out


DUPLICATE = (
    "generations/2026-11-26-round-4-literal.yaml",
    "debates/2026-11-26-round-4-literal.yaml",
    "reports/2026-11-26-round-4-literal.md",
)


def test_discard_marks_the_duplicate_and_clears_the_guard(config: Path, tmp_path: Path, capsys) -> None:
    record = advanced_record(tmp_path, DUPLICATE, day=26)
    before = RunLog(tmp_path / "runs").read(record).run
    note = "duplicate round 4; kept 2026-11-24"
    assert command(tmp_path).run(["--config", str(config), "discard", f"runs/{record.name}", "--note", note]) == 0
    after = RunLog(tmp_path / "runs").read(record).run
    assert after.discarded and after.discard_note == note
    assert after.model_copy(update={"discarded_at": None, "discard_note": None}) == before
    assert f"discarded runs/{record.name}" in capsys.readouterr().out
    model = ScriptedModel(())
    assert command(tmp_path, model=model).run(["--config", str(config), "run"]) == 0
    assert "awaiting_review" in capsys.readouterr().out and model.requests == []


def refused(tmp_path: Path, config: Path, record: Path, capsys) -> str:
    before = record.read_bytes()
    assert command(tmp_path).run(["--config", str(config), "discard", str(record), "--note", "x"]) == 1
    assert record.read_bytes() == before
    return capsys.readouterr().err


def test_discard_refuses_while_files_are_on_disk(config: Path, tmp_path: Path, capsys) -> None:
    record = advanced_record(tmp_path, (ROUND_3, "debates/gone.yaml"))
    err = refused(tmp_path, config, record, capsys)
    assert "still on disk" in err and ROUND_3 in err and "gone.yaml" not in err


def test_discard_refuses_a_record_with_no_outputs(config: Path, tmp_path: Path, capsys) -> None:
    record = advanced_record(tmp_path, ())
    assert "wrote no files" in refused(tmp_path, config, record, capsys)


def test_discard_refuses_twice(config: Path, tmp_path: Path, capsys) -> None:
    record = advanced_record(tmp_path, DUPLICATE, day=26)
    assert command(tmp_path).run(["--config", str(config), "discard", str(record), "--note", "dup"]) == 0
    capsys.readouterr()
    assert "already discarded" in refused(tmp_path, config, record, capsys)


def test_discard_needs_a_note(config: Path, tmp_path: Path) -> None:
    record = advanced_record(tmp_path, DUPLICATE, day=26)
    with pytest.raises(SystemExit):
        command(tmp_path).run(["--config", str(config), "discard", str(record)])


def test_approve_writes_a_sign_off_for_the_head(config: Path, tmp_path: Path, capsys) -> None:
    assert command(tmp_path).run(["--config", str(config), "approve", ROUND_3, "--note", "keep the obscura line"]) == 0
    signed = ReviewSignOff.model_validate(yaml.safe_load((tmp_path / "reviews" / "2026-11-23-round-3-literal.yaml").read_text()))
    assert signed.reviewed_run_path == ROUND_3 and signed.review_note == "keep the obscura line"
    assert signed.reviewed_run_digest == hashlib.sha256((tmp_path / ROUND_3).read_bytes()).hexdigest()
    capsys.readouterr()
    command(tmp_path).run(["--config", str(config), "status"])
    assert "gate: round 3 signed off" in capsys.readouterr().out


def test_approve_refuses_a_run_that_is_not_the_head(config: Path, tmp_path: Path, capsys) -> None:
    status = command(tmp_path).run(["--config", str(config), "approve", "debates/2026-11-16-round-2-literal.yaml"])
    assert status == 1 and "is not the lineage head" in capsys.readouterr().err
    assert not (tmp_path / "reviews").exists()


def test_approve_refuses_an_unfinished_run(config: Path, tmp_path: Path, capsys) -> None:
    raw = yaml.safe_load((tmp_path / ROUND_3).read_text())
    raw["stop_reason"] = "budget"
    (tmp_path / "debates" / "stopped.yaml").write_text(yaml.safe_dump(raw, sort_keys=False))
    assert command(tmp_path).run(["--config", str(config), "approve", "debates/stopped.yaml"]) == 1
    assert "not finished" in capsys.readouterr().err


# -- the launch agent ------------------------------------------------------------------------


def test_install_writes_and_loads_the_plist(config: Path, tmp_path: Path) -> None:
    launchctl = FakeLaunchctl()
    assert command(tmp_path, launchctl).run(["--config", str(config), "install"]) == 0
    path = tmp_path / "agents" / f"{LABEL}.plist"
    plist = plistlib.loads(path.read_bytes())
    assert plist["Label"] == LABEL
    assert plist["ProgramArguments"] == [str(UV), "run", "--project", str(tmp_path.resolve()), "seeker-schedule", "run"]
    assert plist["WorkingDirectory"] == str(tmp_path.resolve())
    assert plist["StartCalendarInterval"] == {"Hour": 2, "Minute": 0}
    assert plist["StandardOutPath"] == str(tmp_path / "logs" / "seeker-schedule.out.log")
    assert plist["EnvironmentVariables"]["PATH"].startswith("/opt/tools/bin:")
    assert "ANTHROPIC" not in path.read_text() and "sk-" not in path.read_text()
    assert ("bootstrap", "gui/501", str(path)) in launchctl.calls and launchctl.is_loaded
    assert (tmp_path / "logs").is_dir()


def test_a_changed_config_changes_the_plist(config: Path, tmp_path: Path) -> None:
    text = config.read_text().replace("  logs: logs", f"  logs: {tmp_path / 'elsewhere'}").replace("  hour: 2", "  hour: 4")
    config.write_text(text)
    launchctl = FakeLaunchctl()
    command(tmp_path, launchctl).run(["--config", str(config), "install"])
    assert command(tmp_path, launchctl).run(["--config", str(config), "install"]) == 0  # reinstall replaces
    plist = plistlib.loads((tmp_path / "agents" / f"{LABEL}.plist").read_bytes())
    assert plist["StandardErrorPath"] == str(tmp_path / "elsewhere" / "seeker-schedule.err.log")
    assert plist["StartCalendarInterval"] == {"Hour": 4, "Minute": 0}
    assert ("bootout", f"gui/501/{LABEL}") in launchctl.calls


def test_uninstall_unloads_and_removes(config: Path, tmp_path: Path, capsys) -> None:
    launchctl = FakeLaunchctl()
    command(tmp_path, launchctl).run(["--config", str(config), "install"])
    assert command(tmp_path, launchctl).run(["--config", str(config), "uninstall"]) == 0
    assert not (tmp_path / "agents" / f"{LABEL}.plist").exists() and not launchctl.is_loaded
    assert "removed the launch agent" in capsys.readouterr().out
    assert command(tmp_path, launchctl).run(["--config", str(config), "uninstall"]) == 0
    assert "no launch agent was installed" in capsys.readouterr().out


# -- the schedule workspace ------------------------------------------------------------------


def checkouts(tmp_path: Path, create_workspace: bool = True) -> tuple[Path, Path]:
    """A main checkout whose .env names a schedule workspace; returns both seeker.yaml paths."""
    main = workspace(tmp_path / "main")
    target = tmp_path / "schedule-ws"
    (tmp_path / "main" / ".env").write_text(f"SEEKER_SCHEDULE_WORKSPACE={target}\n")
    ws = workspace(target) if create_workspace else target / "seeker.yaml"
    return main, ws


def test_a_manual_run_from_the_main_checkout_writes_in_the_workspace(tmp_path: Path, capsys) -> None:
    main, ws = checkouts(tmp_path)
    model = ScriptedModel(())
    assert command(tmp_path, model=model).run(["--config", str(main), "run"]) == 0
    assert "awaiting_review" in capsys.readouterr().out and model.requests == []
    assert len(RunLog(ws.parent / "runs").all()) == 1
    assert not (main.parent / "runs").exists()


def test_status_from_the_main_checkout_reports_the_workspace(tmp_path: Path, capsys) -> None:
    main, ws = checkouts(tmp_path)
    (main.parent / ROUND_3).unlink()  # the main checkout lost round 3; the workspace still has it
    assert command(tmp_path).run(["--config", str(main), "status"]) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0].startswith(f"workspace: {ws.parent.resolve()}")
    assert f"head: {ROUND_3} (round 3, literal)" in out


def test_approve_from_the_main_checkout_signs_the_workspace_head(tmp_path: Path, capsys) -> None:
    main, ws = checkouts(tmp_path)
    assert command(tmp_path).run(["--config", str(main), "approve", ROUND_3]) == 0
    assert (ws.parent / "reviews" / "2026-11-23-round-3-literal.yaml").is_file()
    assert not (main.parent / "reviews").exists()


def test_a_missing_workspace_stops_every_command_but_uninstall(tmp_path: Path, capsys) -> None:
    main, ws = checkouts(tmp_path, create_workspace=False)
    model = ScriptedModel(())
    for argv in (["run"], ["status"], ["approve", ROUND_3], ["install"]):
        assert command(tmp_path, model=model).run(["--config", str(main), *argv]) == 1
        err = capsys.readouterr().err
        assert str(ws.parent.resolve()) in err and "seeker-schedule workspace create" in err
    assert model.requests == [] and not (main.parent / "runs").exists()
    assert command(tmp_path).run(["--config", str(main), "uninstall"]) == 0
