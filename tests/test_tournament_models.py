"""The tournament and debate-run ontology models (debate-ideas task 3.4)."""

import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from seeker.ontology import (
    AxisVerdict,
    Comparison,
    Critique,
    CritiqueTarget,
    Debate,
    DebateFailure,
    DebateRun,
    Defense,
    DefenseMove,
    DefenseOutcome,
    Rating,
    Reply,
    RoleDigest,
    RoleName,
    ScoreAxis,
    Severity,
    StopReason,
    Tournament,
    Usage,
)

ROOT = Path(__file__).resolve().parent.parent
USAGE = Usage(input_tokens=10, output_tokens=5, cache_read_tokens=0, cache_write_tokens=0)
DIGEST = "a" * 64
DEBATE_ROLES = (RoleName.PROSECUTOR, RoleName.SKEPTIC, RoleName.TASTE_CRITIC, RoleName.ADVOCATE, RoleName.JUDGE)


def verdicts(winner: int) -> tuple[AxisVerdict, ...]:
    return tuple(AxisVerdict(axis_name=axis, winner=winner, ruling="It is better.") for axis in ScoreAxis)


def comparison(first: int = 1, second: int = 2, winner: int = 1, **overrides: object) -> Comparison:
    fields: dict[str, object] = {
        "first": first,
        "second": second,
        "verdicts": verdicts(winner),
        "model": "claude-sonnet-5-5",
        "usage": USAGE,
    }
    fields.update(overrides)
    return Comparison(**fields)


def tournament(**overrides: object) -> Tournament:
    fields: dict[str, object] = {
        "k_factor": 32.0,
        "initial_rating": 1500.0,
        "max_comparisons": 66,
        "entrants": (1, 2, 3),
        "comparisons": (comparison(),),
        "ratings": (Rating(position=1, axis_name=ScoreAxis.PROMISE, rating=1516.0, wins=1, losses=0),),
        "survivors": (1, 2, 3),
    }
    fields.update(overrides)
    return Tournament(**fields)


# --- Comparison -----------------------------------------------------------------------


def test_comparison_has_one_verdict_per_axis() -> None:
    assert comparison().verdict_on(ScoreAxis.NOVELTY).winner == 1
    with pytest.raises(ValidationError, match="one verdict per score axis"):
        comparison(verdicts=verdicts(1)[:2])
    doubled = (*verdicts(1)[:2], AxisVerdict(axis_name=ScoreAxis.NOVELTY, winner=2, ruling="r"))
    with pytest.raises(ValidationError, match="one verdict per score axis"):
        comparison(verdicts=doubled)


def test_winner_is_in_the_pair() -> None:
    with pytest.raises(ValidationError, match="one of the two ideas"):
        comparison(winner=5)


def test_pair_is_two_ideas() -> None:
    with pytest.raises(ValidationError, match="two different ideas"):
        comparison(first=2, second=2, winner=2)


def test_failed_comparison_has_no_verdicts() -> None:
    failed = comparison(failed=True, verdicts=())
    assert failed.failed and failed.verdict_on(ScoreAxis.PROMISE) is None
    with pytest.raises(ValidationError, match="no verdicts"):
        comparison(failed=True)


# --- Tournament -----------------------------------------------------------------------


def test_tournament_lookups() -> None:
    assert tournament().rating_of(1, ScoreAxis.PROMISE).rating == 1516.0
    assert tournament().rating_of(2, ScoreAxis.PROMISE) is None


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"entrants": (1, 1, 2)}, "enters a tournament once"),
        ({"survivors": (1, 9)}, "at most three of the entrants"),
        ({"entrants": (1, 2, 3, 4), "survivors": (1, 2, 3, 4)}, "at most three"),
        ({"ratings": (Rating(position=9, axis_name=ScoreAxis.NOVELTY, rating=1500.0, wins=0, losses=0),)}, "only for entrants"),
        ({"comparisons": (comparison(first=1, second=9, winner=9),)}, "only between entrants"),
        ({"skipped": True}, "skipped tournament"),
    ],
)
def test_tournament_rules(overrides: dict[str, object], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        tournament(**overrides)


def test_skipped_tournament() -> None:
    assert tournament(entrants=(1,), comparisons=(), ratings=(), survivors=(), skipped=True).skipped


# --- DebateRun ------------------------------------------------------------------------


def a_debate(position: int) -> Debate:
    found = Critique(
        role_name=RoleName.SKEPTIC,
        model="claude-haiku-5-5",
        target=CritiqueTarget.BEHAVIOR,
        severity=Severity.MINOR,
        failure="The roll needs a take-up spindle nobody sells in zine sizes.",
        argument="Paper rolls wider than receipts need custom hardware.",
        usage=USAGE,
    )
    answer = Defense(
        model="claude-opus-5-5",
        replies=(Reply(answers=RoleName.SKEPTIC, move=DefenseMove.REBUT, argument="Tape and a dowel."),),
        outcome=DefenseOutcome.DEFENDED,
        usage=USAGE,
    )
    return Debate(position=position, critiques=(found,), defense=answer, final_statement="A paper roll comic.")


def run(**overrides: object) -> DebateRun:
    fields: dict[str, object] = {
        "generation_path": "generations/2026-11-04-round-1-literal.yaml",
        "generation_digest": DIGEST,
        "role_digests": tuple(RoleDigest(role_name=role, role_digest=DIGEST) for role in DEBATE_ROLES),
        "catalog_digest": DIGEST,
        "tournament_seed": 7,
        "started_at": datetime(2026, 11, 12, 22, 0, tzinfo=timezone.utc),
        "budget_usd": 5.0,
        "stop_reason": StopReason.FINISHED,
        "debates": (a_debate(1), a_debate(2)),
        "debate_failures": (
            DebateFailure(position=3, role_name=RoleName.ADVOCATE, model="claude-opus-5-5", failure_reason="no JSON", usage=USAGE),
        ),
        "tournament": tournament(entrants=(1, 2), survivors=(1, 2), ratings=()),
        "usage": USAGE,
        "estimated_cost_usd": 0.01,
    }
    fields.update(overrides)
    return DebateRun(**fields)


def test_run_lookups() -> None:
    record = run()
    assert record.digest_of(RoleName.JUDGE) == DIGEST
    assert record.digest_of(RoleName.GENERATOR) is None
    assert record.debate_at(2).position == 2 and record.debate_at(3) is None


def test_run_needs_five_distinct_debate_role_digests() -> None:
    with pytest.raises(ValidationError):
        run(role_digests=tuple(RoleDigest(role_name=r, role_digest=DIGEST) for r in DEBATE_ROLES[:4]))
    twice = tuple(RoleDigest(role_name=RoleName.SKEPTIC, role_digest=DIGEST) for _ in DEBATE_ROLES)
    with pytest.raises(ValidationError, match="one digest per debate role"):
        run(role_digests=twice)
    generator = (*DEBATE_ROLES[:4], RoleName.GENERATOR)
    with pytest.raises(ValidationError, match="none for the generator"):
        run(role_digests=tuple(RoleDigest(role_name=r, role_digest=DIGEST) for r in generator))


def test_debates_in_position_order() -> None:
    with pytest.raises(ValidationError, match="position order"):
        run(debates=(a_debate(2), a_debate(1)))


def test_run_record_is_a_schema_instance(tmp_path: Path) -> None:
    path = tmp_path / "run.yaml"
    path.write_text(yaml.safe_dump(run().model_dump(mode="json"), sort_keys=False))
    tool = shutil.which("linkml-validate")
    if tool is None:
        pytest.skip("linkml-validate not installed")
    check = subprocess.run(
        [tool, "-s", str(ROOT / "schema" / "seeker.yaml"), "-C", "DebateRun", str(path)],
        capture_output=True,
        text=True,
    )
    assert check.returncode == 0, check.stdout + check.stderr
