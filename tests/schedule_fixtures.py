"""A throwaway Seeker workspace holding copies of the committed round 1-3 literal records."""

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROUNDS = (
    ("2026-11-04-round-1-literal", "2026-11-14-round-1-literal"),
    ("2026-11-16-round-2-literal", "2026-11-16-round-2-literal"),
    ("2026-11-23-round-3-literal", "2026-11-23-round-3-literal"),
)


def workspace(tmp_path: Path, rounds: int = 3, extra_config: str = "") -> Path:
    """Copy the first ``rounds`` generations and debate runs (and their reports) into ``tmp_path``,
    with a seeker.yaml that reads the repo's decks and prompts. Returns the config path."""
    for folder in ("generations", "debates", "reports"):
        (tmp_path / folder).mkdir(parents=True, exist_ok=True)
    for generation, run in ROUNDS[:rounds]:
        shutil.copy(ROOT / "generations" / f"{generation}.yaml", tmp_path / "generations")
        shutil.copy(ROOT / "debates" / f"{run}.yaml", tmp_path / "debates")
        report = ROOT / "reports" / f"{run}.md"
        if report.is_file():
            shutil.copy(report, tmp_path / "reports")
    text = (ROOT / "seeker.yaml").read_text()
    for folder in ("decks", "prompts"):
        text = text.replace(f"{folder}: {folder}", f"{folder}: {ROOT / folder}")
    text = text.replace("  vault: null", f"  vault: {tmp_path / 'vault'}")
    path = tmp_path / "seeker.yaml"
    path.write_text(text + extra_config)
    return path
