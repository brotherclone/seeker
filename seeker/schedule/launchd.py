"""The per-user LaunchAgent that fires ``seeker-schedule run`` daily.

Every path in the plist (repository root, ``uv``, logs) is worked out at install time from
the config's location and the ``uv`` on PATH, so moving a run is a config change and a
reinstall, never a code change. The API key is never written into the plist."""

from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
from pathlib import Path

from pydantic import ConfigDict, Field

from seeker.config import ConfigError, SeekerConfig
from seeker.ontology import SeekerModel

LABEL = "com.seeker.scheduled-run"
DEFAULT_AGENTS = Path("~/Library/LaunchAgents")
BASE_PATH = ("/usr/local/bin", "/opt/homebrew/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin")


class UvNotFound(ConfigError):
    def __init__(self) -> None:
        super().__init__("uv is not on PATH; install it (https://docs.astral.sh/uv/) before installing the schedule")


class LaunchctlFailed(ConfigError):
    def __init__(self, argv: tuple[str, ...], detail: str) -> None:
        super().__init__(f"{' '.join(argv)} failed: {detail.strip() or 'no output'}")


class LaunchctlResult(SeekerModel):
    """What one launchctl invocation returned."""

    model_config = ConfigDict(title="LaunchctlResult")

    returncode: int = Field(description="The exit status.")
    output: str = Field(default="", description="stdout and stderr together.")


class Launchctl:
    """Runs launchctl in the user's GUI domain. Tests substitute a fake."""

    def __init__(self) -> None:
        self.domain = f"gui/{os.getuid()}"

    def run(self, *args: str) -> LaunchctlResult:
        done = subprocess.run(["launchctl", *args], capture_output=True, text=True, check=False)
        return LaunchctlResult(returncode=done.returncode, output=done.stdout + done.stderr)

    def loaded(self, label: str) -> bool:
        return self.run("print", f"{self.domain}/{label}").returncode == 0

    def bootstrap(self, plist: Path) -> None:
        result = self.run("bootstrap", self.domain, str(plist))
        if result.returncode != 0:
            raise LaunchctlFailed(("launchctl", "bootstrap", self.domain, str(plist)), result.output)

    def bootout(self, label: str) -> None:
        self.run("bootout", f"{self.domain}/{label}")  # not loaded is fine


class LaunchAgent:
    """Renders, installs and removes the scheduled run's LaunchAgent."""

    def __init__(
        self,
        config: SeekerConfig,
        launchctl: Launchctl | None = None,
        agents_dir: Path | None = None,
        uv: Path | None = None,
    ) -> None:
        self.config = config
        self.launchctl = launchctl or Launchctl()
        self.agents_dir = (agents_dir or DEFAULT_AGENTS).expanduser()
        self._uv = uv

    @property
    def plist_path(self) -> Path:
        return self.agents_dir / f"{LABEL}.plist"

    def uv(self) -> Path:
        if self._uv is not None:
            return self._uv
        found = shutil.which("uv")
        if found is None:
            raise UvNotFound()
        return Path(found)  # the PATH entry, not its target: a Homebrew Cellar path breaks on upgrade

    def plist(self) -> bytes:
        uv = self.uv()
        root = self.config.root.resolve()
        logs = self.config.paths.logs
        search_path = ":".join(dict.fromkeys((str(uv.parent), *BASE_PATH)))
        body = {
            "Label": LABEL,
            "ProgramArguments": [str(uv), "run", "--project", str(root), "seeker-schedule", "run"],
            "WorkingDirectory": str(root),
            "StartCalendarInterval": {"Hour": self.config.schedule.hour, "Minute": 0},
            "StandardOutPath": str(logs / "seeker-schedule.out.log"),
            "StandardErrorPath": str(logs / "seeker-schedule.err.log"),
            "EnvironmentVariables": {"PATH": search_path, "SEEKER_CONFIG": str(self.config.root / "seeker.yaml")},
            "RunAtLoad": False,
        }
        return plistlib.dumps(body)

    def install(self) -> Path:
        """Write the plist and (re)load it. Reinstalling replaces a loaded agent."""
        self.config.paths.logs.mkdir(parents=True, exist_ok=True)
        self.agents_dir.mkdir(parents=True, exist_ok=True)
        if self.launchctl.loaded(LABEL):
            self.launchctl.bootout(LABEL)
        self.plist_path.write_bytes(self.plist())
        self.launchctl.bootstrap(self.plist_path)
        return self.plist_path

    def uninstall(self) -> bool:
        """Unload and remove the agent; False when there was nothing installed."""
        present = self.plist_path.is_file() or self.launchctl.loaded(LABEL)
        self.launchctl.bootout(LABEL)
        self.plist_path.unlink(missing_ok=True)
        return present

    def loaded(self) -> bool:
        return self.launchctl.loaded(LABEL)
