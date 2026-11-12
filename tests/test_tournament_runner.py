"""Running the tournament over a debated run (debate-ideas tasks 7.3-7.4)."""

import json
from pathlib import Path

import pytest

from seeker.debate.elo import Ratings
from seeker.debate.meter import CostMeter
from seeker.debate.record import DebateFile
from seeker.debate.tournament import TournamentRunner
from seeker.models import ModelCallFailed, ModelReply, ScriptedModel
from seeker.ontology import DefenseOutcome, ScoreAxis, StopReason, Usage
from test_debate_runner import PRICES, ROLES_PROMPTS, one_round, runner, source

CALL = Usage(input_tokens=2_000, output_tokens=300, cache_read_tokens=0, cache_write_tokens=0)


def judgment(winner: str = "A") -> ModelReply:
    body = {axis.value: {"winner": winner, "reason": "Specific."} for axis in ScoreAxis}
    return ModelReply(output_json=json.dumps(body), usage=CALL)


def debated(tmp_path: Path, ideas: int) -> tuple:
    src = source(ideas)
    run = runner(ScriptedModel(one_round() * ideas), tmp_path / "vault").debate_all(src, seed=7).run
    return run, src.generation


def tournament(model: ScriptedModel, budget: float = 100.0, max_comparisons: int = 66) -> TournamentRunner:
    from seeker.config import SeekerConfig
    from seeker.debate import DebateRoles
    from seeker.ontology import Reading, RoleName

    roles = DebateRoles.load(ROLES_PROMPTS, SeekerConfig.load(ROLES_PROMPTS.parent / "seeker.yaml").prices)
    return TournamentRunner(roles.role(RoleName.JUDGE), model, Reading.LITERAL, CostMeter(PRICES, budget), max_comparisons)


def test_round_robin_and_survivors(tmp_path: Path) -> None:
    run, generation = debated(tmp_path, 4)
    model = ScriptedModel(tuple(judgment() for _ in range(6)))
    done = tournament(model).play(run, generation)
    played = done.tournament
    assert len(played.comparisons) == 6 and played.entrants == (1, 2, 3, 4)
    assert played.ratings == Ratings.recompute((1, 2, 3, 4), played.comparisons, 32.0, 1500.0)
    assert len(played.survivors) == 3 and done.stop_reason is StopReason.FINISHED
    promise = {r.position: r.rating for r in played.ratings if r.axis_name is ScoreAxis.PROMISE}
    assert [promise[p] for p in played.survivors] == sorted(promise.values(), reverse=True)[:3]
    assert done.estimated_cost_usd > run.estimated_cost_usd


def test_withdrawn_ideas_do_not_compete(tmp_path: Path) -> None:
    run, generation = debated(tmp_path, 4)
    withdrawn = run.debates[1].defense.model_copy(update={"outcome": DefenseOutcome.WITHDRAWN})
    debates = (run.debates[0], run.debates[1].model_copy(update={"defense": withdrawn}), *run.debates[2:])
    run = run.model_copy(update={"debates": debates})
    done = tournament(ScriptedModel(tuple(judgment() for _ in range(3)))).play(run, generation)
    assert done.tournament.entrants == (1, 3, 4) and len(done.tournament.comparisons) == 3


def test_fewer_than_two_entrants_is_skipped(tmp_path: Path) -> None:
    run, generation = debated(tmp_path, 1)
    model = ScriptedModel(())
    done = tournament(model).play(run, generation)
    assert done.tournament.skipped and done.tournament.comparisons == () and model.requests == []


def test_two_entrants_both_survive(tmp_path: Path) -> None:
    run, generation = debated(tmp_path, 2)
    done = tournament(ScriptedModel((judgment(),))).play(run, generation)
    assert sorted(done.tournament.survivors) == [1, 2]


def test_judge_retry_then_failure_leaves_ratings(tmp_path: Path) -> None:
    run, generation = debated(tmp_path, 2)
    bad = ModelReply(output_json=json.dumps({"novelty": {"winner": "A", "reason": "x"}}), usage=CALL)
    model = ScriptedModel((bad, bad))
    done = tournament(model).play(run, generation)
    (comparison,) = done.tournament.comparisons
    assert comparison.failed and comparison.usage.input_tokens == 4_000
    assert "feasibility" in model.requests[1].retry.feedback
    assert {r.rating for r in done.tournament.ratings} == {1500.0}


def test_judge_call_failure_is_a_failed_comparison(tmp_path: Path) -> None:
    run, generation = debated(tmp_path, 2)
    done = tournament(ScriptedModel((ModelCallFailed("overloaded"),))).play(run, generation)
    assert done.tournament.comparisons[0].failed


def test_interrupted_tournament_resumes_without_repeats(tmp_path: Path) -> None:
    run, generation = debated(tmp_path, 4)
    sink = DebateFile(tmp_path / "run.yaml")
    with pytest.raises(Exception):
        tournament(ScriptedModel(tuple(judgment() for _ in range(2)))).play(run, generation, sink)
    partial = sink.read()
    assert len(partial.tournament.comparisons) == 2
    model = ScriptedModel(tuple(judgment() for _ in range(4)))
    done = tournament(model).play(partial, generation, sink)
    pairs = [frozenset((c.first, c.second)) for c in done.tournament.comparisons]
    assert len(pairs) == 6 == len(set(pairs)) and model.remaining == 0


def test_budget_stops_the_tournament(tmp_path: Path) -> None:
    run, generation = debated(tmp_path, 4)
    model = ScriptedModel(tuple(judgment() for _ in range(6)))
    stopped = tournament(model, budget=run.estimated_cost_usd + 0.000001).play(run, generation)
    assert stopped.stop_reason is StopReason.BUDGET and len(stopped.tournament.comparisons) == 1
