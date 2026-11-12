"""The seeker-debate command line (debate-ideas tasks 8.1-8.2), with a scripted model injected."""

import json
from pathlib import Path

import pytest
import yaml

from seeker.debate.cli import DebateCommand
from seeker.debate.record import DebateFile
from seeker.models import ModelReply, ScriptedModel
from seeker.ontology import Generation, ScoreAxis, StopReason, Usage
from test_debate_runner import one_round

ROOT = Path(__file__).resolve().parent.parent
CALL = Usage(input_tokens=1_000, output_tokens=100, cache_read_tokens=0, cache_write_tokens=0)


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
    path = tmp_path / "seeker.yaml"
    path.write_text(text)
    return path


@pytest.fixture
def generation(tmp_path: Path) -> Path:
    """The round-1 literal generation cut to its first three ideas."""
    full = yaml.safe_load((ROOT / "generations" / "2026-11-04-round-1-literal.yaml").read_text())
    full["ideas"], full["failures"] = full["ideas"][:3], []
    keys = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")
    full["usage"] = {k: sum(i["usage"].get(k, 0) for i in full["ideas"]) for k in keys}
    Generation.model_validate(full)
    path = tmp_path / "generations" / "three.yaml"
    path.parent.mkdir()
    path.write_text(yaml.safe_dump(full, sort_keys=False))
    return path


def judgment() -> ModelReply:
    return ModelReply(
        output_json=json.dumps({a.value: {"winner": "A", "reason": "Specific."} for a in ScoreAxis}), usage=CALL
    )


def full_script(ideas: int = 3, comparisons: int = 3) -> ScriptedModel:
    return ScriptedModel(one_round() * ideas + tuple(judgment() for _ in range(comparisons)))


def test_dry_run_needs_no_key_and_makes_no_calls(config, capsys) -> None:
    model = ScriptedModel(())
    generation = ROOT / "generations" / "2026-11-04-round-1-literal.yaml"
    assert DebateCommand(model).run([str(generation), "--dry-run", "--config", str(config)]) == 0
    out = capsys.readouterr().out
    assert "12 debates, 48 debate calls (up to 36 searches), up to 66 comparisons" in out
    assert out.count("=== idea") == 24 and model.requests == []


def test_run_out_writes_debates_tournament_and_survivors(config, generation, tmp_path, capsys) -> None:
    out = tmp_path / "run.yaml"
    model = full_script()
    assert DebateCommand(model).run(["run", str(generation), "--out", str(out), "--config", str(config)]) == 0
    record = DebateFile(out).read()
    assert len(record.debates) == 3 and len(record.tournament.comparisons) == 3
    assert record.stop_reason is StopReason.FINISHED and record.tournament_seed == 7
    assert record.generation_path == "generations/three.yaml"
    printed = capsys.readouterr().out
    assert "defended" in printed and "survivor 1:" in printed and "searches" in printed and model.remaining == 0


def test_no_tournament_stops_before_ranking(config, generation, tmp_path) -> None:
    out = tmp_path / "run.yaml"
    assert DebateCommand(full_script(comparisons=0)).run(
        [str(generation), "--out", str(out), "--no-tournament", "--config", str(config)]
    ) == 0
    record = DebateFile(out).read()
    assert record.stop_reason is StopReason.NO_TOURNAMENT and record.tournament is None
    model = ScriptedModel(tuple(judgment() for _ in range(3)))
    assert DebateCommand(model).run([str(generation), "--out", str(out), "--config", str(config)]) == 0
    assert len(DebateFile(out).read().tournament.comparisons) == 3 and model.remaining == 0


def test_budget_stop_exits_three_and_resumes(config, generation, tmp_path, capsys) -> None:
    out = tmp_path / "run.yaml"
    status = DebateCommand(full_script()).run([str(generation), "--out", str(out), "--budget", "0.0001", "--config", str(config)])
    assert status == 3 and DebateFile(out).read().stop_reason is StopReason.BUDGET
    assert "higher --budget" in capsys.readouterr().out
    rest = ScriptedModel(one_round() * 2 + tuple(judgment() for _ in range(3)))
    assert DebateCommand(rest).run([str(generation), "--out", str(out), "--budget", "50", "--config", str(config)]) == 0
    assert DebateFile(out).read().stop_reason is StopReason.FINISHED


def test_scratch_lands_in_ignored_folder(config, generation, tmp_path) -> None:
    assert DebateCommand(full_script()).run([str(generation), "--scratch", "--config", str(config)]) == 0
    (written,) = (tmp_path / "debates" / "scratch").glob("*-three.yaml")
    assert DebateFile(written).read().stop_reason is StopReason.FINISHED


def test_a_target_is_required(config, generation) -> None:
    with pytest.raises(SystemExit):
        DebateCommand(ScriptedModel(())).run([str(generation), "--config", str(config)])


def test_missing_key_fails_before_any_call(config, generation, tmp_path, capsys) -> None:
    assert DebateCommand().run([str(generation), "--out", str(tmp_path / "r.yaml"), "--config", str(config)]) == 1
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err


def test_report_from_a_finished_run(config, generation, tmp_path, capsys) -> None:
    out = tmp_path / "run.yaml"
    DebateCommand(full_script()).run([str(generation), "--out", str(out), "--config", str(config)])
    model = ScriptedModel(())
    assert DebateCommand(model).run(["report", str(out), "--config", str(config)]) == 0
    report = (tmp_path / "reports" / "run.md").read_text()
    assert report.count("### ") == 3 and "**prosecutor**" in report and "*Advocate rebuts:*" in report
    assert "novelty" in report and "## Provenance" in report and model.requests == []
