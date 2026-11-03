"""The seeker-decks command line (spec: Command-line validation)."""

import subprocess
import sys
from pathlib import Path

import pytest

from deck_fixtures import REQUIRED_AXES, deck_body, valid_directory, write_deck
from seeker.decks.cli import main


def test_valid_decks_print_digests(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    directory = valid_directory(tmp_path)
    assert main(["validate", "--dir", str(directory)]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert [line.split()[0] for line in lines[:-1]] == sorted(REQUIRED_AXES)
    for line in lines[:-1]:
        _, count, unit, digest = line.split()
        assert (count, unit) == ("1", "cards") and len(digest) == 12
    assert lines[-1].startswith("deck set")
    assert lines[-1].split()[-3:-1] == ["5", "cards"]


def test_invalid_decks_print_every_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    directory = valid_directory(tmp_path)
    write_deck(directory, "technique", deck_body("technique", {"id": "Bad_Id", "name": "bad"}))
    (directory / "domain.yaml").unlink()
    assert main(["validate", "--dir", str(directory)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    errors = captured.err.splitlines()
    assert errors[-1] == f"2 errors in {directory}"
    assert any("card 'Bad_Id'" in line for line in errors)
    assert any("missing required axis 'domain'" in line for line in errors)


def test_python_dash_m_entry_point(tmp_path: Path) -> None:
    directory = valid_directory(tmp_path)
    result = subprocess.run(
        [sys.executable, "-m", "seeker.decks", "validate", "--dir", str(directory)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[-1].startswith("deck set")
