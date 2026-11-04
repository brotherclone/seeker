"""Pinning where a generation came from: the git commit, when there is one."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from seeker.ontology import GitCommit


class GitRepo:
    """Reads the current commit of a working tree, marking uncommitted changes."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def _git(self, *args: str) -> str | None:
        if shutil.which("git") is None:
            return None
        result = subprocess.run(["git", *args], cwd=self.root, capture_output=True, text=True, check=False)
        return result.stdout.strip() if result.returncode == 0 else None

    def commit(self) -> GitCommit | None:
        head = self._git("rev-parse", "HEAD")
        if head is None:
            return None
        dirty = bool(self._git("status", "--porcelain", "--untracked-files=no"))
        return GitCommit(f"{head}-dirty" if dirty else head)
