"""``seeker-schedule workspace create`` and ``update`` against a real temporary git repository
with a bare ``origin`` (pin-schedule-workspace 6.1, 6.2)."""

import plistlib
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from seeker.config import SeekerConfig
from seeker.ontology import ScheduledRun
from seeker.schedule.cli import ScheduleCommand
from seeker.schedule.lineage import LineageRecords
from seeker.schedule.launchd import LABEL
from seeker.schedule.log import RunLock, RunLog
from seeker.schedule.workspace import UvSync
from tests.schedule_fixtures import ROOT, ROUNDS, workspace
from tests.test_schedule_cli import UV, FakeLaunchctl

ROUND_3 = ROUNDS[2]
ROUND_3_FILES = (
    f"generations/{ROUND_3[0]}.yaml",
    f"debates/{ROUND_3[1]}.yaml",
    f"reports/{ROUND_3[1]}.md",
)
IGNORE = ".env\nruns/\nlogs/\n.venv/\n__pycache__/\n"


class FakeUvSync(UvSync):
    def __init__(self) -> None:
        self.projects: list[Path] = []

    def run(self, project: Path) -> None:
        self.projects.append(project)


def git(cwd: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", *args],
        cwd=cwd, capture_output=True, text=True, check=True,
    )
    return done.stdout.strip()


class Repo:
    """origin.git, a main checkout with rounds 1-2 committed on develop and round 3 untracked,
    and a .env naming the workspace."""

    def __init__(self, tmp_path: Path) -> None:
        self.origin = tmp_path / "origin.git"
        self.main = tmp_path / "main"
        self.ws = tmp_path / "seeker-schedule"
        self.origin.mkdir()
        git(self.origin, "init", "--bare", "-b", "develop")
        self.config_path = workspace(self.main, rounds=2)
        (self.main / ".gitignore").write_text(IGNORE)
        git(self.main, "init", "-b", "develop")
        git(self.main, "add", ".")
        git(self.main, "commit", "-m", "rounds 1-2")
        git(self.main, "remote", "add", "origin", str(self.origin))
        git(self.main, "push", "origin", "develop")
        for relative in ROUND_3_FILES:
            shutil.copy(ROOT / relative, self.main / relative)
        (self.main / "debates" / "scratch").mkdir()
        (self.main / "debates" / "scratch" / "probe.yaml").write_text("scratch: true\n")
        (self.main / ".env").write_text(f"SEEKER_SCHEDULE_WORKSPACE={self.ws}\n")
        started = datetime(2026, 11, 23, 14, 0).astimezone()
        RunLog(self.main / "runs").write(
            ScheduledRun(
                started_at=started, ended_at=started + timedelta(minutes=40), schedule_outcome="advanced",
                written_paths=ROUND_3_FILES, budget_usd=5.0, estimated_cost_usd=4.7,
            )
        )
        self.uv = FakeUvSync()

    def command(self, *argv: str, launchctl: FakeLaunchctl | None = None) -> int:
        return ScheduleCommand(
            uv_sync=self.uv, launchctl=launchctl or FakeLaunchctl(), agents_dir=self.main.parent / "agents", uv=UV,
        ).run(["--config", str(self.config_path), *argv])

    def merge_round_3(self) -> None:
        """Commit round 3 on a feature branch in the main checkout and land it on develop."""
        git(self.main, "switch", "-c", "feature/round-3")
        git(self.main, "add", *ROUND_3_FILES)
        git(self.main, "commit", "-m", "Record round 3")
        git(self.main, "push", "origin", "HEAD:develop")

    def head_round(self) -> int:
        return LineageRecords(SeekerConfig.load(self.ws / "seeker.yaml")).head().round


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    return Repo(tmp_path)


# -- create ---------------------------------------------------------------------------------


def test_create_carries_the_live_round_into_a_detached_worktree(repo: Repo, capsys) -> None:
    assert repo.command("workspace", "create") == 0
    out = capsys.readouterr().out
    assert f"created {repo.ws.resolve()}" in out
    assert git(repo.ws, "branch", "--show-current") == ""
    assert git(repo.ws, "rev-parse", "HEAD") == git(repo.main, "rev-parse", "origin/develop")
    for relative in ROUND_3_FILES:
        assert (repo.ws / relative).read_bytes() == (repo.main / relative).read_bytes()
        assert f"copied {relative}" in out
        assert (repo.main / relative).is_file()  # nothing is taken from the source
    assert not (repo.ws / "debates" / "scratch").exists()
    assert (repo.ws / ".env").read_text() == (repo.main / ".env").read_text()
    assert len(RunLog(repo.ws / "runs").all()) == 1
    assert repo.uv.projects == [repo.ws.resolve()]
    assert repo.head_round() == 3


def test_status_after_create_reports_the_workspace_head(repo: Repo, capsys) -> None:
    assert repo.command("workspace", "create") == 0
    (repo.main / ROUND_3_FILES[1]).unlink()  # the main checkout no longer matters
    capsys.readouterr()
    assert repo.command("status") == 0
    out = capsys.readouterr().out
    assert out.startswith(f"workspace: {repo.ws.resolve()}")
    assert f"head: {ROUND_3_FILES[1]} (round 3, literal)" in out


def test_create_refuses_an_existing_path(repo: Repo, capsys) -> None:
    repo.ws.mkdir()
    (repo.ws / "keep.txt").write_text("mine")
    assert repo.command("workspace", "create") == 1
    assert "already exists" in capsys.readouterr().err
    assert sorted(p.name for p in repo.ws.iterdir()) == ["keep.txt"]
    assert "seeker-schedule" not in git(repo.main, "worktree", "list")


# -- update ---------------------------------------------------------------------------------


def test_update_moves_to_develop_once_the_round_is_merged(repo: Repo, capsys) -> None:
    assert repo.command("workspace", "create") == 0
    before = git(repo.ws, "rev-parse", "HEAD")
    repo.merge_round_3()
    capsys.readouterr()
    assert repo.command("workspace", "update") == 0
    out = capsys.readouterr().out
    after = git(repo.ws, "rev-parse", "HEAD")
    assert after != before and after == git(repo.origin, "rev-parse", "develop")
    assert git(repo.ws, "branch", "--show-current") == ""
    assert git(repo.ws, "status", "--porcelain", "--", "generations", "debates", "reports") == ""
    for relative in ROUND_3_FILES:
        assert f"now committed: {relative}" in out
    assert repo.head_round() == 3


def test_update_refuses_when_a_committed_copy_differs(repo: Repo, capsys) -> None:
    assert repo.command("workspace", "create") == 0
    repo.merge_round_3()
    changed = repo.ws / ROUND_3_FILES[1]
    changed.write_bytes(changed.read_bytes() + b"# resumed after the copy\n")
    body = changed.read_bytes()
    before = git(repo.ws, "rev-parse", "HEAD")
    assert repo.command("workspace", "update") == 1
    err = capsys.readouterr().err
    assert ROUND_3_FILES[1] in err and ROUND_3_FILES[0] not in err
    assert git(repo.ws, "rev-parse", "HEAD") == before
    assert changed.read_bytes() == body
    assert all((repo.ws / relative).is_file() for relative in ROUND_3_FILES)


def test_update_refuses_while_a_trigger_holds_the_lock(repo: Repo, capsys) -> None:
    assert repo.command("workspace", "create") == 0
    repo.merge_round_3()
    before = git(repo.ws, "rev-parse", "HEAD")
    lock = RunLock(repo.ws / "runs")
    assert lock.acquire()
    try:
        assert repo.command("workspace", "update") == 1
    finally:
        lock.release()
    assert "holds the lock" in capsys.readouterr().err
    assert git(repo.ws, "rev-parse", "HEAD") == before


def test_update_with_nothing_new_stays_put(repo: Repo, capsys) -> None:
    assert repo.command("workspace", "create") == 0
    capsys.readouterr()
    assert repo.command("workspace", "update") == 0
    assert "already at origin/develop" in capsys.readouterr().out
    assert repo.head_round() == 3


def test_workspace_commands_need_a_configured_path(repo: Repo, capsys) -> None:
    (repo.main / ".env").write_text("")
    assert repo.command("workspace", "create") == 1
    assert "SEEKER_SCHEDULE_WORKSPACE" in capsys.readouterr().err


# -- install ----------------------------------------------------------------------------------


def test_install_points_the_agent_at_the_workspace(repo: Repo) -> None:
    assert repo.command("workspace", "create") == 0
    launchctl = FakeLaunchctl()
    assert repo.command("install", launchctl=launchctl) == 0
    plist = plistlib.loads((repo.main.parent / "agents" / f"{LABEL}.plist").read_bytes())
    ws = str(repo.ws.resolve())
    assert plist["WorkingDirectory"] == ws
    assert plist["ProgramArguments"] == [str(UV), "run", "--project", ws, "seeker-schedule", "run"]
    assert plist["EnvironmentVariables"]["SEEKER_CONFIG"] == f"{ws}/seeker.yaml"
    assert plist["StandardOutPath"] == f"{ws}/logs/seeker-schedule.out.log"
    assert launchctl.is_loaded


def test_install_refuses_a_folder_that_is_not_a_worktree(repo: Repo, capsys) -> None:
    workspace(repo.ws)  # has a seeker.yaml, but is not a worktree of this repository
    launchctl = FakeLaunchctl()
    launchctl.is_loaded = True
    assert repo.command("install", launchctl=launchctl) == 1
    err = capsys.readouterr().err
    assert "not a git worktree" in err and str(repo.ws.resolve()) in err and "workspace create" in err
    assert all(call[0] != "bootout" for call in launchctl.calls) and launchctl.is_loaded
    assert not (repo.main.parent / "agents").exists()
