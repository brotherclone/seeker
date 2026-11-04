"""The seeker-generate command line (spec: Command-line generation), with ScriptedModel injected."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from seeker.decks import DeckDirectory
from seeker.draw import BatchDrawer
from seeker.generate.cli import GenerateCommand
from seeker.models import ModelReply, ScriptedModel
from seeker.ontology import DrawBatch, Generation, Usage

ROOT = Path(__file__).resolve().parent.parent
CONFIG = str(ROOT / "seeker.yaml")
CALL = Usage(input_tokens=100, output_tokens=50, cache_read_tokens=0, cache_write_tokens=0)


@pytest.fixture(autouse=True)
def no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("SEEKER_CONFIG", raising=False)


@pytest.fixture(scope="module")
def batch() -> DrawBatch:
    return BatchDrawer(DeckDirectory(ROOT / "decks").load()).draw(7, 12)


def replies(batch: DrawBatch) -> ScriptedModel:
    return ScriptedModel(
        tuple(
            ModelReply(
                output_json=json.dumps(
                    {
                        "statement": f"A piece for draw {d.position} that listens because rooms remember.",
                        "subject": "a piece",
                        "behavior": "listens",
                        "rationale": "rooms remember",
                        "card_readings": [{"card": c, "interpretation": "as named"} for c in d.drawn_cards],
                    }
                ),
                usage=CALL,
            )
            for d in batch.draws
        )
    )


def run(model: ScriptedModel | None, *args: str) -> int:
    return GenerateCommand(model=model).run(["run", "--config", CONFIG, *args])


def test_seeded_run_prints_ideas_and_summary(batch, capsys) -> None:
    model = replies(batch)
    assert run(model, "--seed", "7") == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 13
    assert lines[0].startswith(" 1  [music]  A piece for draw 1")
    assert lines[-1].startswith("12 ideas · 0 failures · 1,200 in / 600 out")
    assert "(claude-opus-5-5, literal)" in lines[-1]
    assert len(model.requests) == 12


def test_batch_file_input(batch, tmp_path, capsys) -> None:
    path = tmp_path / "batch.yaml"
    path.write_text(yaml.safe_dump(batch.model_dump(mode="json")))
    assert run(replies(batch), "--batch", str(path), "--reading", "metaphorical") == 0
    assert "metaphorical)" in capsys.readouterr().out.splitlines()[-1]


def test_dry_run_needs_no_key_and_makes_no_calls(capsys) -> None:
    model = ScriptedModel(())
    assert run(model, "--seed", "7", "--dry-run") == 0
    out = capsys.readouterr().out
    assert out.count("=== draw ") == 12 and "=== system" in out
    assert out.rstrip().endswith("dry run: 12 prompts, no API calls")
    assert model.requests == []


def test_missing_key_fails_before_any_call(capsys) -> None:
    assert GenerateCommand().run(["run", "--config", CONFIG, "--seed", "7"]) == 1
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err


def test_bad_reading_names_the_choices(capsys) -> None:
    with pytest.raises(SystemExit):
        run(ScriptedModel(()), "--seed", "7", "--reading", "surreal")
    assert "literal, loose, metaphorical" in capsys.readouterr().err


def test_out_writes_and_resumes(batch, tmp_path, capsys) -> None:
    out = tmp_path / "gen.yaml"
    assert run(replies(batch), "--seed", "7", "--out", str(out)) == 0
    record = Generation.model_validate(yaml.safe_load(out.read_text()))
    assert len(record.ideas) == 12
    capsys.readouterr()
    again = ScriptedModel(())
    assert run(again, "--seed", "7", "--out", str(out)) == 0
    assert "resuming" in capsys.readouterr().out
    assert again.requests == []


def test_scratch_lands_in_ignored_folder(batch, tmp_path, capsys) -> None:
    config = tmp_path / "seeker.yaml"
    text = (ROOT / "seeker.yaml").read_text()
    text = text.replace("decks: decks", f"decks: {ROOT / 'decks'}").replace("prompts: prompts", f"prompts: {ROOT / 'prompts'}")
    config.write_text(text)
    assert GenerateCommand(model=replies(batch)).run(["run", "--config", str(config), "--seed", "7", "--scratch"]) == 0
    written = list((tmp_path / "generations" / "scratch").glob("*-7-literal.yaml"))
    assert len(written) == 1
    if shutil.which("git") and (ROOT / ".git").exists():
        ignored = subprocess.run(["git", "check-ignore", "-q", "generations/scratch/x.yaml"], cwd=ROOT)
        assert ignored.returncode == 0


@pytest.mark.parametrize("label", ["../oops", "a/b", "..", ".hidden", "-x", "x..y", "with space", "a" * 81])
def test_label_must_be_one_safe_filename_component(label: str, capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        run(ScriptedModel(()), "--seed", "7", f"--label={label}")
    assert exc.value.code == 2
    assert "not a valid label" in capsys.readouterr().err


def test_good_label_writes_inside_generations(batch, tmp_path, capsys) -> None:
    config = tmp_path / "seeker.yaml"
    text = (ROOT / "seeker.yaml").read_text()
    text = text.replace("decks: decks", f"decks: {ROOT / 'decks'}").replace("prompts: prompts", f"prompts: {ROOT / 'prompts'}")
    config.write_text(text)
    assert GenerateCommand(model=replies(batch)).run(["run", "--config", str(config), "--seed", "7", "--label", "round-1_literal.v2"]) == 0
    (written,) = (tmp_path / "generations").glob("*-round-1_literal.v2.yaml")
    assert written.parent == tmp_path / "generations"


def test_missing_config_flag_exits_cleanly(capsys) -> None:
    assert GenerateCommand(model=ScriptedModel(())).run(["run", "--config", "/nope/seeker.yaml", "--seed", "7"]) == 1
    assert "no such config file" in capsys.readouterr().err
