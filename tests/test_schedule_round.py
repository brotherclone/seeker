"""RoundRunner: one round in process under one cap per trigger (scheduled-run 4.4)."""

from datetime import date
from pathlib import Path

import pytest

from seeker.config import SeekerConfig
from seeker.debate.meter import RunCost
from seeker.debate.record import DebateFile
from seeker.generate import GenerationFile
from seeker.models import ScriptedModel
from seeker.mutate.job import MutationJob
from seeker.ontology import ScheduleOutcome, StopReason
from seeker.schedule.lineage import LineageRecords
from seeker.schedule.round import RoundRunner
from test_debate_cli import judgment
from test_debate_runner import one_round
from tests.schedule_fixtures import workspace
from tests.test_generator import CALL, answer

TODAY = date(2026, 11, 25)
ROUND_4 = "2026-11-25-round-4-literal"
JUDGMENTS = 132


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SEEKER_VAULT", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def load(tmp_path: Path) -> SeekerConfig:
    return SeekerConfig.load(workspace(tmp_path))


def children(config: SeekerConfig, start: int = 0) -> tuple:
    head = LineageRecords(config).head()
    plan = MutationJob(config, head.path).plan
    return tuple(answer(e.draw) for e in plan.children[start:])


def whole_round(config: SeekerConfig) -> ScriptedModel:
    return ScriptedModel(children(config) + one_round() * 12 + tuple(judgment() for _ in range(JUDGMENTS)))


def test_a_full_round_writes_three_files(tmp_path: Path) -> None:
    config = load(tmp_path)
    state = LineageRecords(config).state()
    result = RoundRunner(config, whole_round(config), TODAY).advance(state, 5.0)
    assert result.outcome is ScheduleOutcome.ADVANCED and result.round == 4
    assert result.generation == tmp_path / "generations" / f"{ROUND_4}.yaml"
    assert result.debate_run == tmp_path / "debates" / f"{ROUND_4}.yaml"
    assert result.report == tmp_path / "reports" / f"{ROUND_4}.md"
    assert all(path.is_file() for path in result.written)
    run = DebateFile(result.debate_run).read()
    assert run.stop_reason is StopReason.FINISHED
    spent = GenerationFile(result.generation).read().estimated_cost_usd + RunCost.of(run).usd(config.prices)
    assert result.cost_usd == pytest.approx(spent)
    assert LineageRecords(config).head().round == 4


def test_mutation_spend_reduces_the_debate_budget(tmp_path: Path) -> None:
    config = load(tmp_path)
    result = RoundRunner(config, whole_round(config), TODAY).advance(LineageRecords(config).state(), 5.0)
    mutation = GenerationFile(result.generation).read().estimated_cost_usd
    assert mutation > 0
    assert DebateFile(result.debate_run).read().budget_usd == pytest.approx(5.0 - mutation)


def test_cap_reached_mid_tournament_then_resumed_next_trigger(tmp_path: Path) -> None:
    # Measure a full round's costs in one workspace, then cap a second one mid-tournament.
    measured = load(tmp_path / "measure")
    full = RoundRunner(measured, whole_round(measured), TODAY).advance(LineageRecords(measured).state(), 5.0)
    full_run = DebateFile(full.debate_run).read()
    comparisons = len(full_run.tournament.comparisons)
    sample = full_run.tournament.comparisons[0]
    judge = measured.prices.cost(sample.model, sample.usage)
    before_tournament = full.cost_usd - comparisons * judge

    config = load(tmp_path / "capped")
    first_model = whole_round(config)
    cap = before_tournament + 10.5 * judge
    first = RoundRunner(config, first_model, TODAY).advance(LineageRecords(config).state(), cap)
    assert first.outcome is ScheduleOutcome.BUDGET and first.report is None
    stopped = DebateFile(first.debate_run).read()
    assert stopped.stop_reason is StopReason.BUDGET
    done = len(stopped.tournament.comparisons)
    assert done == 11  # the comparison that crosses the cap is the last one made

    state = LineageRecords(config).state()
    assert state.head.round == 3 and state.in_progress == first.generation
    assert state.in_progress_run == first.debate_run
    second_model = ScriptedModel(tuple(judgment() for _ in range(JUDGMENTS)))
    second = RoundRunner(config, second_model, date(2026, 11, 26)).advance(state, 5.0)
    assert second.outcome is ScheduleOutcome.ADVANCED
    assert second.generation == first.generation  # resumed under its original name
    assert len(second_model.requests) == comparisons - done
    assert second.cost_usd == pytest.approx((comparisons - done) * judge)


def test_cap_reached_during_mutation(tmp_path: Path) -> None:
    config = load(tmp_path)
    per_child = config.prices.cost("claude-opus-5-5", CALL)
    model = ScriptedModel(children(config))
    result = RoundRunner(config, model, TODAY).advance(LineageRecords(config).state(), per_child * 3.5)
    assert result.outcome is ScheduleOutcome.BUDGET and result.debate_run is None
    assert len(model.requests) == 4
    assert GenerationFile(result.generation).read().stop_reason is StopReason.BUDGET

    resumed = ScriptedModel(children(config, start=4) + one_round() * 12 + tuple(judgment() for _ in range(JUDGMENTS)))
    again = RoundRunner(config, resumed, TODAY).advance(LineageRecords(config).state(), 5.0)
    assert again.outcome is ScheduleOutcome.ADVANCED
    assert GenerationFile(again.generation).read().stop_reason is None
