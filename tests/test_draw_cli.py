"""The seeker-draw command line (spec: Command-line drawing)."""

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from seeker.decks import DeckDirectory
from seeker.draw.cli import main
from seeker.draw.drawer import BatchDrawer
from seeker.ontology import DrawBatch

ROOT = Path(__file__).resolve().parent.parent
DECKS = str(ROOT / "decks")
SUMMARY = re.compile(r"^seed (\d+)  decks ([0-9a-f]{12})  (\d+) draws$")


def run(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, list[str]]:
    code = main(["batch", "--dir", DECKS, *args])
    return code, capsys.readouterr().out.splitlines()


def test_seeded_draw(capsys: pytest.CaptureFixture[str]) -> None:
    code, lines = run(capsys, "--seed", "7", "--size", "12")
    assert code == 0
    assert len(lines) == 13
    assert [int(line.split()[0]) for line in lines[:12]] == list(range(1, 13))
    assert all("constraint: " in line for line in lines[:12])
    match = SUMMARY.match(lines[-1])
    assert match and match.group(1) == "7" and match.group(3) == "12"


def test_unseeded_draw_prints_a_reproducible_seed(capsys: pytest.CaptureFixture[str]) -> None:
    _, first = run(capsys)
    seed = SUMMARY.match(first[-1]).group(1)
    _, again = run(capsys, "--seed", seed)
    assert again == first


def test_out_writes_a_valid_replayable_record(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "batches" / "2026-11-03-test.yaml"
    code, lines = run(capsys, "--seed", "7", "--out", str(out))
    assert code == 0 and lines[-1] == f"wrote {out}"
    record = DrawBatch.model_validate(yaml.safe_load(out.read_text()))
    drawer = BatchDrawer(DeckDirectory(ROOT / "decks").load())
    assert drawer.replay(record) == record

    tool = shutil.which("linkml-validate")
    if tool is None:
        pytest.skip("linkml-validate not installed")
    result = subprocess.run(
        [tool, "-s", str(ROOT / "schema" / "seeker.yaml"), "-C", "DrawBatch", str(out)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_scratch_writes_under_batches_scratch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    code, lines = run(capsys, "--seed", "42", "--scratch")
    assert code == 0
    assert (tmp_path / "batches" / "scratch" / "42.yaml").is_file()
    assert lines[-1] == "wrote batches/scratch/42.yaml"


def test_out_and_scratch_are_exclusive(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["batch", "--dir", DECKS, "--out", "x.yaml", "--scratch"])
    assert exc.value.code == 2
    assert "not allowed with argument" in capsys.readouterr().err


def test_size_out_of_range_exits_nonzero(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["batch", "--dir", DECKS, "--seed", "1", "--size", "31"]) == 1
    assert "1 to 30" in capsys.readouterr().err


def test_scratch_folder_is_gitignored() -> None:
    if shutil.which("git") is None or not (ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    result = subprocess.run(
        ["git", "check-ignore", "-q", "batches/scratch/x.yaml"], cwd=ROOT, capture_output=True
    )
    assert result.returncode == 0
    kept = subprocess.run(["git", "check-ignore", "-q", "batches/2026-11-03-round-1.yaml"], cwd=ROOT)
    assert kept.returncode == 1
