"""The seeker-works command line against a fixture vault."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from seeker.works.cli import main
from vault_fixtures import ROOT, work_note

CONFIG = """\
paths: {{decks: {decks}, batches: batches, generations: generations, prompts: prompts, vault: null}}
prices:
  as_of: 2026-11-04
  models:
    - {{model: claude-opus-5-5, input: 4.0, output: 20.0, cache_read: 0.4, cache_write: 5.0}}
"""


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.delenv("SEEKER_VAULT", raising=False)
    monkeypatch.delenv("SEEKER_CONFIG", raising=False)
    project = tmp_path / "project"
    project.mkdir()
    (project / "seeker.yaml").write_text(CONFIG.format(decks=ROOT / "decks"))
    (project / ".env").write_text(f"SEEKER_VAULT={tmp_path / 'vault'}\n")
    monkeypatch.chdir(project)
    return tmp_path / "vault"


def works(vault: Path) -> Path:
    return vault / "Works"


def test_vault_not_configured(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (Path.cwd() / ".env").unlink()
    assert main(["validate"]) == 1
    assert "SEEKER_VAULT" in capsys.readouterr().err
    assert not project.exists()


def test_validate_ok(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    work_note(works(project), "demo", cards='["[[oramics]]"]')
    assert main(["validate"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("1 work in ") and "catalog " in out


def test_validate_problems(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    work_note(works(project), "a", extra="year: soon\n")
    work_note(works(project), "b", cards='["[[granular-synth]]"]')
    assert main(["validate"]) == 1
    err = capsys.readouterr().err.splitlines()
    assert err[-1].startswith("2 problems in ")
    assert any("b.md: cards: 'granular-synth': unknown card" in line for line in err)


def test_sync_cards_then_resync(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["sync-cards"]) == 0
    assert capsys.readouterr().out.startswith("153 created, 0 updated, 0 unchanged")
    assert (project / "Cards" / "granular-synthesis.md").is_file()
    assert main(["sync-cards"]) == 0
    assert capsys.readouterr().out.startswith("0 created, 0 updated, 153 unchanged")


def test_suggest_lists_then_applies(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = work_note(works(project), "demo", body="Drawn sound on cassette tape.\n")
    before = path.read_text()
    assert main(["suggest"]) == 0
    out = capsys.readouterr().out
    assert "demo.md" in out and "+ oramics" in out and "+ tape" in out and "--apply" in out
    assert path.read_text() == before
    assert main(["suggest", "--apply"]) == 0
    assert "added 2 card links to 1 note" in capsys.readouterr().out
    assert "'[[oramics]]'" in path.read_text()
    assert main(["suggest"]) == 0
    assert "no new card suggestions" in capsys.readouterr().out


def test_check_batch(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    work_note(works(project), "fischinger strip", cards='["[[webcomic]]", "[[lumigraph]]"]')
    batch = ROOT / "batches" / "2026-11-04-round-1.yaml"
    assert main(["check", "--batch", str(batch)]) == 0
    lines = capsys.readouterr().out.splitlines()
    entries = [line for line in lines if line.startswith("#")]
    assert len(entries) == 12
    assert lines[1] == "     [2 of 3] fischinger strip (fischinger-strip): webcomic, lumigraph"
    assert lines.count("     no prior art in the vault") == 11
    assert lines[-1].startswith("1 of 12 draws have prior art among 1 works")


def test_check_bad_batch(project: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("seed: nope\n")
    assert main(["check", "--batch", str(bad)]) == 1
    assert "not a readable draw batch" in capsys.readouterr().err


def test_console_script(project: Path) -> None:
    script = shutil.which("seeker-works")
    command = [script] if script else [sys.executable, "-m", "seeker.works"]
    result = subprocess.run([*command, "validate"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("0 works in ")
