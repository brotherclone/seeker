"""Integration (mutate-ideas 7.2): seeker-mutate feeds seeker-debate run, which feeds the report.

Fake models throughout; the records must be schema instances and the report must
show 15 entrants with lineage and judge health."""

import shutil
import subprocess
from pathlib import Path

import pytest

from seeker.debate.cli import DebateCommand
from seeker.debate.record import DebateFile
from seeker.generate import GenerationFile
from seeker.models import ScriptedModel
from seeker.mutate.cli import MutateCommand
from seeker.ontology import StopReason
from test_debate_cli import judgment
from test_debate_runner import one_round
from test_mutate_cli import RUN, children_script

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("SEEKER_CONFIG", raising=False)
    monkeypatch.setenv("SEEKER_VAULT", str(tmp_path / "vault"))


@pytest.fixture
def config(tmp_path: Path) -> Path:
    text = (ROOT / "seeker.yaml").read_text()
    for folder in ("decks", "prompts"):
        text = text.replace(f"{folder}: {folder}", f"{folder}: {ROOT / folder}")
    (tmp_path / "debates").mkdir()
    shutil.copy(RUN, tmp_path / "debates" / RUN.name)
    shutil.copytree(ROOT / "generations", tmp_path / "generations", ignore=shutil.ignore_patterns("scratch"))
    path = tmp_path / "seeker.yaml"
    path.write_text(text)
    return path


def schema_check(path: Path, target: str) -> None:
    tool = shutil.which("linkml-validate")
    if tool is None:
        pytest.skip("linkml-validate not installed")
    check = subprocess.run(
        [tool, "-s", str(ROOT / "schema" / "seeker.yaml"), "-C", target, str(path)], capture_output=True, text=True
    )
    assert check.returncode == 0, check.stdout + check.stderr


def test_mutate_debate_report(config: Path, tmp_path: Path) -> None:
    generation = tmp_path / "generations" / "round-2.yaml"
    assert MutateCommand(children_script()).run(
        [str(tmp_path / "debates" / RUN.name), "--out", str(generation), "--config", str(config)]
    ) == 0
    assert GenerationFile(generation).read().round == 2

    out = tmp_path / "debates" / "round-2.yaml"
    model = ScriptedModel(one_round() * 12 + tuple(judgment() for _ in range(120)))
    assert DebateCommand(model).run(["run", str(generation), "--out", str(out), "--config", str(config)]) == 0
    assert model.remaining == 0
    run = DebateFile(out).read()
    assert run.stop_reason is StopReason.FINISHED
    assert run.tournament.both_orders and len(run.tournament.entrants) == 15
    assert [d.carried_from for d in run.debates[12:]] == [10, 6, 3]

    assert DebateCommand(ScriptedModel(())).run(["report", str(out), "--config", str(config)]) == 0
    report = (tmp_path / "reports" / "round-2.md").read_text()
    survivors = report.count("\n### ")
    rows = report.split("## The rest, by promise", 1)[1].split("\n## ", 1)[0].count("\n| ") - 1
    assert survivors + rows == 15
    assert "## Lineage" in report and "**#13 (was #10):**" in report
    assert "## Judge health" in report and "pairs split between the two orders" in report

    schema_check(generation, "Generation")
    schema_check(out, "DebateRun")
