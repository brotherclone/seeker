"""The schedule workspace: a git worktree of the repository, detached at ``origin/develop``, that
the scheduled job runs in and nobody switches branches in.

Round outputs stay untracked between reviews, so the tree the job writes to holds the only copy.
``create`` makes the worktree and carries the live records into it. ``update`` moves it to the
latest ``develop`` and only drops an untracked file when develop now holds an identical copy,
so the lineage can never lose a round to a checkout."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from pydantic import ConfigDict, Field

from seeker.config import ConfigError, SeekerConfig
from seeker.ontology import SeekerModel
from seeker.schedule.log import RunLock

REMOTE = "origin"
BRANCH = "develop"
TARGET = f"{REMOTE}/{BRANCH}"
OUTPUT_FOLDERS = ("generations", "debates", "reports", "reviews")
SCRATCH = "scratch"


class WorkspaceError(ConfigError):
    """The workspace cannot be created or moved without risking a record."""


class GitFailed(WorkspaceError):
    def __init__(self, argv: tuple[str, ...], detail: str) -> None:
        super().__init__(f"git {' '.join(argv)} failed: {detail.strip() or 'no output'}")


class GitResult(SeekerModel):
    """What one git invocation returned."""

    model_config = ConfigDict(title="GitResult")

    returncode: int = Field(description="The exit status.")
    stdout: bytes = Field(default=b"", description="Standard output, as bytes so file contents survive.")
    stderr: str = Field(default="", description="Standard error.")

    @property
    def text(self) -> str:
        return self.stdout.decode("utf-8", errors="replace")

    @property
    def lines(self) -> tuple[str, ...]:
        return tuple(line for line in self.text.splitlines() if line.strip())


class Git:
    """Runs the git CLI in a folder. Tests may substitute a subclass."""

    def run(self, cwd: Path, *args: str) -> GitResult:
        done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=False)
        return GitResult(
            returncode=done.returncode, stdout=done.stdout, stderr=done.stderr.decode("utf-8", errors="replace")
        )

    def check(self, cwd: Path, *args: str) -> GitResult:
        result = self.run(cwd, *args)
        if result.returncode != 0:
            raise GitFailed(args, result.stderr)
        return result


class UvSync:
    """Installs a checkout's locked dependencies. Tests substitute a fake."""

    def run(self, project: Path) -> None:
        done = subprocess.run(["uv", "sync", "--project", str(project)], capture_output=True, text=True, check=False)
        if done.returncode != 0:
            raise WorkspaceError(f"uv sync --project {project} failed: {done.stderr.strip() or 'no output'}")


class HeldFile(SeekerModel):
    """An untracked workspace file set aside while the checkout moves, so a refused move can put it back."""

    model_config = ConfigDict(title="HeldFile")

    name: str = Field(description="The file's path relative to the worktree.")
    body: bytes = Field(description="Its bytes, identical to develop's committed copy.")


class WorkspaceCreated(SeekerModel):
    """What ``workspace create`` made and carried over."""

    model_config = ConfigDict(title="WorkspaceCreated")

    path: Path = Field(description="The new worktree.")
    commit: str = Field(description="The develop commit it is detached at.")
    copied: tuple[str, ...] = Field(default=(), description="Files copied in, relative to the worktree.")


class WorkspaceUpdated(SeekerModel):
    """Where ``workspace update`` moved the worktree from and to."""

    model_config = ConfigDict(title="WorkspaceUpdated")

    path: Path = Field(description="The worktree.")
    from_commit: str = Field(description="The commit it was detached at.")
    to_commit: str = Field(description="The develop commit it is detached at now.")
    replaced: tuple[str, ...] = Field(
        default=(), description="Untracked files dropped because develop now holds identical copies."
    )


class ScheduleWorkspace:
    """Creates and moves the configured schedule workspace for the checkout ``config`` belongs to."""

    def __init__(self, config: SeekerConfig, git: Git | None = None, uv: UvSync | None = None) -> None:
        self.config = config
        self.git = git or Git()
        self.uv = uv or UvSync()
        path = config.schedule_workspace()
        if path is None:
            raise WorkspaceError(
                "no schedule workspace is configured; set SEEKER_SCHEDULE_WORKSPACE in .env "
                "(or schedule.workspace in seeker.yaml)"
            )
        self.path = path

    # -- create ----------------------------------------------------------------------

    def create(self) -> WorkspaceCreated:
        source = self.config.root.resolve()
        if self.path.exists():
            raise WorkspaceError(f"{self.path} already exists; the workspace is created only once")
        if self.path == source:
            raise WorkspaceError(f"the workspace must be a separate folder, not this checkout ({source})")
        self.git.check(source, "fetch", REMOTE, BRANCH)
        self.git.check(source, "worktree", "add", "--detach", str(self.path), TARGET)
        target = SeekerConfig.load(self.path / "seeker.yaml")
        copied: list[str] = []
        if self.config.env_file.is_file():
            copied.append(self._copy(self.config.env_file, target.env_file, target))
        if self.config.paths.runs.is_dir():
            for record in sorted(self.config.paths.runs.glob("*.yaml")):
                copied.append(self._copy(record, target.paths.runs / record.name, target))
        for name in OUTPUT_FOLDERS:
            copied += self._copy_uncommitted(getattr(self.config.paths, name), getattr(target.paths, name), target)
        self.uv.run(self.path)
        return WorkspaceCreated(path=self.path, commit=self._head(self.path), copied=tuple(copied))

    def _copy_uncommitted(self, folder: Path, into: Path, target: SeekerConfig) -> list[str]:
        """Copy the untracked or modified files under ``folder`` (scratch excluded) into ``into``."""
        root = self.config.root.resolve()
        folder = folder.resolve()
        if not folder.is_dir() or not folder.is_relative_to(root):
            return []
        listed = self.git.check(
            root, "ls-files", "--others", "--modified", "--exclude-standard", "--", str(folder.relative_to(root))
        )
        copied: list[str] = []
        for line in dict.fromkeys(listed.lines):
            path = root / line
            inside = path.relative_to(folder)
            if SCRATCH in inside.parts or not path.is_file():
                continue
            copied.append(self._copy(path, into / inside, target))
        return copied

    @staticmethod
    def _copy(source: Path, destination: Path, target: SeekerConfig) -> str:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        resolved = destination.resolve()
        root = target.root.resolve()
        return str(resolved.relative_to(root)) if resolved.is_relative_to(root) else str(resolved)

    # -- update ----------------------------------------------------------------------

    def update(self) -> WorkspaceUpdated:
        if not (self.path / "seeker.yaml").is_file():
            raise WorkspaceError(
                f"the schedule workspace {self.path} does not exist; create it with: uv run seeker-schedule workspace create"
            )
        target = SeekerConfig.load(self.path / "seeker.yaml")
        lock = RunLock(target.paths.runs)
        if not lock.acquire():
            raise WorkspaceError("a scheduled run holds the lock; update the workspace after it finishes")
        try:
            return self._update()
        finally:
            lock.release()

    def _update(self) -> WorkspaceUpdated:
        before = self._head(self.path)
        self.git.check(self.path, "fetch", REMOTE, BRANCH)
        added = self.git.check(self.path, "diff", "--name-only", "--diff-filter=A", "HEAD", TARGET).lines
        untracked = set(self.git.check(self.path, "ls-files", "--others", "--", *added).lines) if added else set()
        held: list[HeldFile] = []
        differ: list[str] = []
        for name in added:
            if name not in untracked:
                continue
            local = (self.path / name).read_bytes()
            committed = self.git.check(self.path, "show", f"{TARGET}:{name}").stdout
            if local == committed:
                held.append(HeldFile(name=name, body=local))
            else:
                differ.append(name)
        if differ:
            raise WorkspaceError(
                f"develop holds different copies of these uncommitted workspace files: {', '.join(differ)}; "
                "the workspace stays where it is until they match"
            )
        for file in held:
            (self.path / file.name).unlink()
        result = self.git.run(self.path, "checkout", "--detach", TARGET)
        if result.returncode != 0:
            for file in held:  # put back what was removed, so a refused checkout loses nothing
                (self.path / file.name).write_bytes(file.body)
            raise GitFailed(("checkout", "--detach", TARGET), result.stderr)
        return WorkspaceUpdated(
            path=self.path, from_commit=before, to_commit=self._head(self.path),
            replaced=tuple(file.name for file in held),
        )

    def _head(self, folder: Path) -> str:
        return self.git.check(folder, "rev-parse", "HEAD").text.strip()
