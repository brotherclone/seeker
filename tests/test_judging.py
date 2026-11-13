"""The blinded judge prompt and verdict checks (debate-ideas task 7.2)."""

import json
from pathlib import Path

import yaml

from seeker.config import SeekerConfig
from seeker.debate import DebateRoles
from seeker.debate.judging import Entrant, JudgePrompt, JudgmentDraft
from seeker.debate.schedule import Pairing
from seeker.ontology import (
    Citation,
    Critique,
    CritiqueTarget,
    Debate,
    Defense,
    DefenseMove,
    DefenseOutcome,
    Generation,
    Reply,
    RoleName,
    ScoreAxis,
    Severity,
    Usage,
)

ROOT = Path(__file__).resolve().parent.parent
GENERATION = Generation.model_validate(
    yaml.safe_load((ROOT / "generations" / "2026-11-04-round-1-literal.yaml").read_text())
)
ROLES = DebateRoles.load(ROOT / "prompts", SeekerConfig.load(ROOT / "seeker.yaml").prices)
USAGE = Usage(input_tokens=1, output_tokens=1, cache_read_tokens=0, cache_write_tokens=0)
MODELS = {"prosecutor": "claude-sonnet-5-5", "skeptic": "claude-haiku-5-5", "taste_critic": "claude-sonnet-5-5"}


def entrant(position: int) -> Entrant:
    idea = GENERATION.ideas[position - 1]
    critiques = []
    for role in (RoleName.PROSECUTOR, RoleName.SKEPTIC, RoleName.TASTE_CRITIC):
        extra = {"citations": (Citation(title="Paper", url="https://nime.org/p", relevance="Close."),)} if role is RoleName.PROSECUTOR else {}
        critiques.append(Critique(role_name=role, model=MODELS[role.value], target=CritiqueTarget.BEHAVIOR,
                                  severity=Severity.FATAL, failure=f"Failure from {position}-{role.value[:3]}x.",
                                  argument="Because.", usage=USAGE, **extra))
    defense = Defense(model="claude-opus-5-5", outcome=DefenseOutcome.DEFENDED, usage=USAGE,
                      replies=tuple(Reply(answers=c.role_name, move=DefenseMove.REBUT, argument="No.") for c in critiques))
    return Entrant(idea=idea, debate=Debate(position=position, critiques=tuple(critiques), defense=defense,
                                            final_statement=idea.statement))


PAIR = Pairing(first=3, second=7)


def render(seed: int = 7) -> str:
    return JudgePrompt(PAIR, entrant(3), entrant(7), seed).render()


def test_nothing_names_who_argued_what() -> None:
    text = render()
    banned = [name.value for name in RoleName] + ["taste critic", "fatal", "serious", "minor", "severity"]
    banned += list(MODELS.values()) + ["claude-opus-5-5"]
    banned += [ROLES.role(name).role.persona[:60] for name in DebateRoles.ALL]
    assert not [word for word in banned if word.lower() in text.lower()]
    assert "Idea A:" in text and "Idea B:" in text and "Objection 3:" in text and "Reply (rebuts)" in text


def test_seeded_order_is_stable() -> None:
    assert render(7) == render(7)
    orders = {tuple(line for line in render(seed).splitlines() if line.startswith("Objection")) for seed in range(12)}
    assert len(orders) > 1


def verdicts(**overrides: object) -> str:
    body = {axis.value: {"winner": "A", "reason": "Clear reason."} for axis in ScoreAxis}
    body.update(overrides)
    return json.dumps(body)


def test_judgment_maps_sides_to_positions() -> None:
    draft, problems = JudgmentDraft.parse(verdicts(feasibility={"winner": "B", "reason": "Cheaper."}))
    assert problems == ()
    comparison = draft.to_comparison(PAIR, "claude-sonnet-5-5", USAGE)
    assert comparison.verdict_on(ScoreAxis.NOVELTY).winner == 3
    assert comparison.verdict_on(ScoreAxis.FEASIBILITY).winner == 7


def test_missing_axis_names_it() -> None:
    body = json.loads(verdicts())
    del body["feasibility"]
    draft, problems = JudgmentDraft.parse(json.dumps(body))
    assert draft is None and any(p.field == "feasibility" for p in problems)


def test_tie_or_outside_choice_is_rejected() -> None:
    for bad in ("tie", "C"):
        draft, problems = JudgmentDraft.parse(verdicts(promise={"winner": bad, "reason": "Equal."}))
        assert draft is None and any(p.field.startswith("promise") for p in problems)


def test_failed_comparison_record() -> None:
    failed = JudgmentDraft.failed(PAIR, "claude-sonnet-5-5", USAGE)
    assert failed.failed and failed.verdicts == ()
