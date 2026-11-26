"""``seeker-mutate`` end to end with a scripted model (mutate-ideas 7.1)."""

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from seeker.generate import GenerationFile
from seeker.models import ScriptedModel
from seeker.mutate.cli import MutateCommand
from seeker.mutate.plan import MutationPlan
from seeker.ontology import Generation, MutationKind
from tests.test_generator import answer

ROOT = Path(__file__).resolve().parent.parent
RUN = ROOT / "debates" / "2026-11-14-round-1-literal.yaml"


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("SEEKER_CONFIG", raising=False)


@pytest.fixture
def config(tmp_path: Path) -> Path:
    """A config rooted in tmp_path that reads the repo's decks, prompts and generations."""
    text = (ROOT / "seeker.yaml").read_text()
    for folder in ("decks", "prompts"):
        text = text.replace(f"{folder}: {folder}", f"{folder}: {ROOT / folder}")
    (tmp_path / "debates").mkdir()
    shutil.copy(RUN, tmp_path / "debates" / RUN.name)
    shutil.copytree(ROOT / "generations", tmp_path / "generations", ignore=shutil.ignore_patterns("scratch"))
    path = tmp_path / "seeker.yaml"
    path.write_text(text)
    return path


def children_script(plan_size: int = 12, start: int = 0) -> ScriptedModel:
    from seeker.config import SeekerConfig
    from seeker.debate.runner import GenerationInput
    from seeker.decks import DeckDirectory
    from seeker.mutate.plan import RunInput

    decks = DeckDirectory(SeekerConfig.load(ROOT / "seeker.yaml").paths.decks).load()
    parent = RunInput.read(RUN, ROOT)
    plan = MutationPlan.build(parent, GenerationInput.read(ROOT / parent.run.generation_path, ROOT), decks, 7, 2)
    return ScriptedModel(tuple(answer(e.draw) for e in plan.children[start:plan_size]))


def test_dry_run_needs_no_key(config: Path, tmp_path: Path, capsys) -> None:
    model = ScriptedModel(())
    assert MutateCommand(model).run([str(tmp_path / "debates" / RUN.name), "--dry-run", "--config", str(config)]) == 0
    out = capsys.readouterr().out
    assert out.count("=== child ") == 12 and out.count(", no call: ") == 3
    assert "round 2, 12 children from 3 survivors" in out and model.requests == []


def test_out_writes_a_mutated_generation(config: Path, tmp_path: Path, capsys) -> None:
    out = tmp_path / "generations" / "round-2.yaml"
    model = children_script()
    assert MutateCommand(model).run([str(tmp_path / "debates" / RUN.name), "--out", str(out), "--config", str(config)]) == 0
    record = GenerationFile(out).read()
    assert record.mutation.parent_run_path == f"debates/{RUN.name}" and record.round == 2
    assert [i.lineage.mutation_kind for i in record.ideas[12:]] == [MutationKind.CARRIED] * 3
    printed = capsys.readouterr().out
    assert "card swap of #10" in printed and "round 2 · 15 ideas" in printed and model.remaining == 0


def test_scratch_lands_in_ignored_folder(config: Path, tmp_path: Path) -> None:
    assert MutateCommand(children_script()).run([str(tmp_path / "debates" / RUN.name), "--scratch", "--config", str(config)]) == 0
    (written,) = (tmp_path / "generations" / "scratch").glob("*-round-2-from-*.yaml")
    assert Generation.model_validate(yaml.safe_load(written.read_text())).round == 2
    relative = Path("generations/scratch") / written.name
    result = subprocess.run(["git", "check-ignore", str(relative)], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0


def test_unfinished_run_exits_one(config: Path, tmp_path: Path, capsys) -> None:
    path = tmp_path / "debates" / RUN.name
    raw = yaml.safe_load(path.read_text())
    raw["stop_reason"] = "budget"
    path.write_text(yaml.safe_dump(raw, sort_keys=False))
    model = ScriptedModel(())
    assert MutateCommand(model).run([str(path), "--out", str(tmp_path / "r2.yaml"), "--config", str(config)]) == 1
    assert "'budget'" in capsys.readouterr().err and model.requests == []


def test_a_target_is_required(config: Path, tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        MutateCommand(ScriptedModel(())).run([str(tmp_path / "debates" / RUN.name), "--config", str(config)])


def test_missing_key_fails_before_any_call(config: Path, tmp_path: Path, capsys) -> None:
    status = MutateCommand().run([str(tmp_path / "debates" / RUN.name), "--out", str(tmp_path / "r2.yaml"), "--config", str(config)])
    assert status == 1 and "ANTHROPIC_API_KEY" in capsys.readouterr().err


def test_budget_stop_exits_three_and_resumes(config: Path, tmp_path: Path, capsys) -> None:
    out = tmp_path / "generations" / "round-2.yaml"
    run = str(tmp_path / "debates" / RUN.name)
    first = children_script(3)
    status = MutateCommand(first).run([run, "--out", str(out), "--budget", "0.004", "--config", str(config)])
    assert status == 3
    printed = capsys.readouterr().out
    assert "not yet made" in printed and "stopped at the $0.00 budget" in printed
    assert GenerationFile(out).read().stop_reason.value == "budget"
    second = children_script(start=3)
    status = MutateCommand(second).run([run, "--out", str(out), "--budget", "1", "--config", str(config)])
    assert status == 0 and second.remaining == 0 and len(second.requests) == 9
    assert GenerationFile(out).read().stop_reason is None
