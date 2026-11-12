"""The debate ontology models (debate-ideas task 3.3): bounds and cross-field rules."""

import pytest
from pydantic import ValidationError

from seeker.ontology import (
    Citation,
    Critique,
    CritiqueTarget,
    Debate,
    Defense,
    DefenseMove,
    DefenseOutcome,
    IdeaRevision,
    Reply,
    RoleName,
    Severity,
    Usage,
)

USAGE = Usage(input_tokens=10, output_tokens=5, cache_read_tokens=0, cache_write_tokens=0)
WEB = Citation(title="A paper", url="https://example.org/paper", relevance="Close but not liturgical.")


def critique(role: RoleName = RoleName.SKEPTIC, **overrides: object) -> Critique:
    fields: dict[str, object] = {
        "role_name": role,
        "model": "claude-haiku-5-5",
        "target": CritiqueTarget.BEHAVIOR,
        "severity": Severity.SERIOUS,
        "failure": "Crowd speech in a stone nave smears every grain into reverb.",
        "argument": "Untrained speakers overlap and the room adds two seconds of tail.",
        "usage": USAGE,
    }
    if role is RoleName.PROSECUTOR:
        fields["citations"] = (WEB,)
    fields.update(overrides)
    return Critique(**fields)


def defense(*roles: RoleName, outcome: DefenseOutcome = DefenseOutcome.DEFENDED, **overrides: object) -> Defense:
    replies = tuple(Reply(answers=role, move=DefenseMove.REBUT, argument="Not so.") for role in roles)
    return Defense(model="claude-opus-5-5", replies=replies, outcome=outcome, usage=USAGE, **overrides)


REVISION = IdeaRevision(
    statement="A sampler that plays one grain per spoken response because a congregation answers in turns.",
    subject="a sampler",
    behavior="plays one grain per spoken response",
    rationale="a congregation answers in turns",
)
CRITICS = (RoleName.PROSECUTOR, RoleName.SKEPTIC, RoleName.TASTE_CRITIC)


# --- Citation -------------------------------------------------------------------------


def test_citation_needs_exactly_one_source() -> None:
    assert Citation(title="t", cited_work="oramics-demo-tape-1962", relevance="r").url is None
    with pytest.raises(ValidationError, match="exactly one of url and cited_work"):
        Citation(title="t", relevance="r")
    with pytest.raises(ValidationError, match="exactly one of url and cited_work"):
        Citation(title="t", url="https://x.org", cited_work="oramics-demo-tape-1962", relevance="r")


def test_citation_defaults_and_bad_url() -> None:
    assert WEB.embodied_cards == ()
    with pytest.raises(ValidationError):
        Citation(title="t", url="not a url", relevance="r")


# --- Critique -------------------------------------------------------------------------


def test_card_reading_target_needs_a_card() -> None:
    assert critique(target=CritiqueTarget.CARD_READING, target_card="lumigraph").target_card == "lumigraph"
    with pytest.raises(ValidationError, match="target_card is required"):
        critique(target=CritiqueTarget.CARD_READING)
    with pytest.raises(ValidationError, match="target_card is required"):
        critique(target_card="lumigraph")


def test_none_found_is_minor_uncited_and_prosecutor_only() -> None:
    found_none = critique(RoleName.PROSECUTOR, citations=(), none_found=True, severity=Severity.MINOR)
    assert found_none.none_found and found_none.citations == ()
    with pytest.raises(ValidationError, match="no citations and is minor"):
        critique(RoleName.PROSECUTOR, citations=(), none_found=True, severity=Severity.FATAL)
    with pytest.raises(ValidationError, match="no citations and is minor"):
        critique(RoleName.PROSECUTOR, none_found=True, severity=Severity.MINOR)
    with pytest.raises(ValidationError, match="only the prosecutor reports"):
        critique(RoleName.SKEPTIC, none_found=True, severity=Severity.MINOR)


def test_prosecutor_cites_or_declares_none() -> None:
    with pytest.raises(ValidationError, match="cites its evidence"):
        critique(RoleName.PROSECUTOR, citations=())
    with pytest.raises(ValidationError, match="only the prosecutor cites"):
        critique(RoleName.TASTE_CRITIC, citations=(WEB,))


def test_critique_text_bounds() -> None:
    with pytest.raises(ValidationError):
        critique(failure="   ")
    with pytest.raises(ValidationError):
        critique(severity="mild")


# --- Defense --------------------------------------------------------------------------


def test_revision_exactly_when_revised() -> None:
    assert defense(RoleName.SKEPTIC, outcome=DefenseOutcome.REVISED, revision=REVISION).revision == REVISION
    with pytest.raises(ValidationError, match="exactly when the outcome is revised"):
        defense(RoleName.SKEPTIC, outcome=DefenseOutcome.REVISED)
    with pytest.raises(ValidationError, match="exactly when the outcome is revised"):
        defense(RoleName.SKEPTIC, revision=REVISION)


def test_one_reply_per_critique() -> None:
    with pytest.raises(ValidationError, match="exactly one reply"):
        defense(RoleName.SKEPTIC, RoleName.SKEPTIC)
    with pytest.raises(ValidationError):
        defense()


def test_reply_lookup() -> None:
    answered = defense(*CRITICS)
    assert answered.reply_to(RoleName.SKEPTIC).answers is RoleName.SKEPTIC
    assert defense(RoleName.SKEPTIC).reply_to(RoleName.PROSECUTOR) is None


# --- Debate ---------------------------------------------------------------------------


def debate(critiques: tuple[Critique, ...], answered: Defense, statement: str = "A sampler.") -> Debate:
    return Debate(position=1, critiques=critiques, defense=answered, final_statement=statement)


def test_full_debate() -> None:
    full = debate(tuple(critique(role) for role in CRITICS), defense(*CRITICS))
    assert full.competes and not full.short_a_critique
    assert full.critique_by(RoleName.PROSECUTOR).citations == (WEB,)


def test_short_debate_still_competes() -> None:
    short = debate((critique(RoleName.PROSECUTOR), critique(RoleName.TASTE_CRITIC)), defense(RoleName.PROSECUTOR, RoleName.TASTE_CRITIC))
    assert short.short_a_critique and short.competes


def test_withdrawn_does_not_compete() -> None:
    gone = debate((critique(),), defense(RoleName.SKEPTIC, outcome=DefenseOutcome.WITHDRAWN))
    assert not gone.competes


def test_defense_must_answer_the_critiques_faced() -> None:
    with pytest.raises(ValidationError, match="answers exactly the critiques"):
        debate((critique(),), defense(RoleName.PROSECUTOR))


def test_duplicate_or_non_critic_critiques() -> None:
    with pytest.raises(ValidationError):
        debate((critique(), critique()), defense(RoleName.SKEPTIC))
    with pytest.raises(ValidationError, match="one critique per critic role"):
        debate((critique(RoleName.JUDGE),), defense(RoleName.JUDGE))


def test_revised_idea_competes_as_revision() -> None:
    revised = defense(RoleName.SKEPTIC, outcome=DefenseOutcome.REVISED, revision=REVISION)
    assert debate((critique(),), revised, REVISION.statement).final_statement == REVISION.statement
    with pytest.raises(ValidationError, match="competes as its revision"):
        debate((critique(),), revised, "Something else.")
