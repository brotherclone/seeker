"""Debate runs: incremental records, resume checks and the budget stop (debate-ideas task 6.6)."""

import json
import shutil
from datetime import date
from pathlib import Path

import pytest

from seeker.config import SeekerConfig
from seeker.debate import DebateRoles
from seeker.debate.debater import Debater
from seeker.debate.meter import CostMeter, RunCost
from seeker.debate.record import DebateFile, DebateResumeMismatch
from seeker.debate.runner import DebateRunner, GenerationInput
from seeker.models import ModelReply, ScriptedModel, SearchResult
from seeker.ontology import Reading, RoleName, StopReason, Usage
from seeker.works.catalog import WorkNotes
from vault_fixtures import repo_decks

ROOT = Path(__file__).resolve().parent.parent
GENERATION = ROOT / "generations" / "2026-11-04-round-1-literal.yaml"
PRICES = SeekerConfig.load(ROOT / "seeker.yaml").prices
ROLES_PROMPTS = ROOT / "prompts"
CALL = Usage(input_tokens=10_000, output_tokens=1_000, cache_read_tokens=0, cache_write_tokens=0)
SEARCHED = CALL.model_copy(update={"web_search_requests": 1})


def critique(failure: str, **extra: object) -> str:
    return json.dumps({"target": "behavior", "target_card": "", "severity": "serious", "failure": failure,
                       "argument": "Specific reasons.", **extra})


NOTHING = critique("Searches across NIME, itch.io and Bandcamp turned up only distant cousins of this exact pairing.",
                   severity="minor", citations=[], none_found=True)
SKEPTIC = critique("Fabricating the custom enclosure needs a laser cutter and four weekends of fitting work.")
TASTE = critique("It lands as a museum interactive that people press once, smile at, and walk past.")
DEFENSE = json.dumps({
    "replies": [{"answers": r, "move": "rebut", "argument": "No."} for r in ("prosecutor", "skeptic", "taste_critic")],
    "outcome": "defended", "statement": "", "subject": "", "behavior": "", "rationale": "",
})


def one_round() -> tuple[ModelReply, ...]:
    return (
        ModelReply(output_json=NOTHING, usage=SEARCHED, search_results=(SearchResult(url="https://x.org"),)),
        ModelReply(output_json=SKEPTIC, usage=CALL),
        ModelReply(output_json=TASTE, usage=CALL),
        ModelReply(output_json=DEFENSE, usage=CALL),
    )


def runner(model: ScriptedModel, vault: Path, budget: float = 5.0, prompts: Path = ROOT / "prompts") -> DebateRunner:
    roles = DebateRoles.load(prompts, PRICES)
    works = WorkNotes(folder=vault, deck_set=repo_decks())
    debater = Debater(roles, model, repo_decks(), works, Reading.LITERAL, date(2026, 11, 12))
    return DebateRunner(roles, debater, CostMeter(PRICES, budget))


def source(ideas: int = 12) -> GenerationInput:
    full = GenerationInput.read(GENERATION, ROOT)
    trimmed = full.generation.model_copy(update={"ideas": full.generation.ideas[:ideas]})
    return full.model_copy(update={"generation": trimmed})


def test_full_debate_stage(tmp_path: Path) -> None:
    model = ScriptedModel(one_round() * 12)
    sink = DebateFile(tmp_path / "run.yaml")
    run = runner(model, tmp_path / "vault").debate_all(source(), seed=7, sink=sink).run
    assert [d.position for d in run.debates] == list(range(1, 13))
    assert run.generation_path == "generations/2026-11-04-round-1-literal.yaml"
    assert len(run.role_digests) == 5 and run.digest_of(RoleName.GENERATOR) is None
    assert sink.read() == run
    assert run.usage.web_search_requests == 12 and run.usage.input_tokens == 12 * 4 * 10_000


def test_mixed_model_cost_adds_up(tmp_path: Path) -> None:
    run = runner(ScriptedModel(one_round()), tmp_path).debate_all(source(1), seed=7).run
    run_one = run
    sonnet, haiku, opus = (PRICES.price_for(m) for m in ("claude-sonnet-5-5", "claude-haiku-5-5", "claude-opus-5-5"))
    expected = sonnet.cost(CALL) + 0.01 + haiku.cost(CALL) + sonnet.cost(CALL) + opus.cost(CALL)
    assert RunCost.of(run_one).usd(PRICES) == pytest.approx(expected)
    assert run.estimated_cost_usd == pytest.approx(expected)


def test_resume_after_interruption(tmp_path: Path) -> None:
    sink = DebateFile(tmp_path / "run.yaml")
    first = runner(ScriptedModel(one_round() * 5), tmp_path / "vault", budget=5.0)
    with pytest.raises(Exception):
        first.debate_all(source(), seed=7, sink=sink)
    partial = sink.read()
    assert [d.position for d in partial.debates] == [1, 2, 3, 4, 5]
    model = ScriptedModel(one_round() * 7)
    done = runner(model, tmp_path / "vault").debate_all(source(), seed=7, sink=sink, record=partial).run
    assert [d.position for d in done.debates] == list(range(1, 13)) and model.remaining == 0


def test_changed_role_file_is_refused_by_name(tmp_path: Path) -> None:
    sink = DebateFile(tmp_path / "run.yaml")
    runner(ScriptedModel(one_round()), tmp_path / "vault").debate_all(source(1), seed=7, sink=sink)
    prompts = tmp_path / "prompts"
    shutil.copytree(ROOT / "prompts", prompts)
    (prompts / "skeptic.yaml").write_text((prompts / "skeptic.yaml").read_text() + "# tweak\n")
    with pytest.raises(DebateResumeMismatch, match="skeptic role digest"):
        runner(ScriptedModel(()), tmp_path / "vault", prompts=prompts).debate_all(source(), seed=7, record=sink.read())


def test_changed_seed_is_refused(tmp_path: Path) -> None:
    record = runner(ScriptedModel(one_round()), tmp_path).debate_all(source(1), seed=7).run
    with pytest.raises(DebateResumeMismatch, match="tournament seed"):
        runner(ScriptedModel(()), tmp_path).debate_all(source(1), seed=8, record=record)


def test_budget_stop_then_resume_with_more(tmp_path: Path) -> None:
    one = runner(ScriptedModel(one_round()), tmp_path / "probe").debate_all(source(1), seed=7).run.estimated_cost_usd
    sink = DebateFile(tmp_path / "run.yaml")
    budget = one * 6.5
    model = ScriptedModel(one_round() * 12)
    stopped = runner(model, tmp_path / "vault", budget=budget).debate_all(source(), seed=7, sink=sink).run
    assert stopped.stop_reason is StopReason.BUDGET and len(stopped.debates) == 7
    assert stopped.estimated_cost_usd >= budget and sink.read().stop_reason is StopReason.BUDGET
    resumed = runner(model, tmp_path / "vault", budget=100).debate_all(source(), seed=7, sink=sink, record=sink.read()).run
    assert len(resumed.debates) == 12 and resumed.stop_reason is None and resumed.budget_usd == 100


def test_catalog_change_does_not_block_resume(tmp_path: Path) -> None:
    sink = DebateFile(tmp_path / "run.yaml")
    runner(ScriptedModel(one_round()), tmp_path / "vault").debate_all(source(1), seed=7, sink=sink)
    from vault_fixtures import work_note

    work_note(tmp_path / "vault", "new work")
    record = sink.read()
    resumed = runner(ScriptedModel(one_round()), tmp_path / "vault").debate_all(source(2), seed=7, record=record).run
    assert resumed.catalog_digest == record.catalog_digest
