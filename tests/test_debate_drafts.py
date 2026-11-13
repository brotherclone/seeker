"""Critique drafts and the named-failure rules (debate-ideas task 6.1)."""

import json
from pathlib import Path

import pytest
import yaml

from seeker.debate.drafts import CitationDraft, CritiqueDraft, ProsecutorDraft, Wording
from seeker.ontology import CritiqueTarget, Generation, RoleName, Severity, Usage

ROOT = Path(__file__).resolve().parent.parent
GENERATION = Generation.model_validate(
    yaml.safe_load((ROOT / "generations" / "2026-11-04-round-1-literal.yaml").read_text())
)
IDEA = GENERATION.ideas[0]
DRAW = GENERATION.draw_batch.draws[0]
CARD_WORDS = frozenset(word for card in DRAW.drawn_cards for word in card.split("-"))
USAGE = Usage(input_tokens=10, output_tokens=5, cache_read_tokens=0, cache_write_tokens=0)
SPECIFIC = "Nobody owns working Oramics hardware, so drawn-film playback needs a film scanner and custom code."
URLS = frozenset({"https://nime.org/paper.pdf"})
WORKS = frozenset({"oramics-demo-tape-1962"})


def draft(**overrides: object) -> CritiqueDraft:
    fields: dict[str, object] = {
        "target": "behavior",
        "severity": "serious",
        "failure": SPECIFIC,
        "argument": "The original machine is in a museum and scanners at that resolution are not cheap.",
    }
    fields.update(overrides)
    return CritiqueDraft.model_validate(fields)


def prosecution(**overrides: object) -> ProsecutorDraft:
    fields: dict[str, object] = {
        "target": "subject",
        "severity": "fatal",
        "failure": SPECIFIC,
        "argument": "A NIME paper describes the same thing.",
        "citations": [{"title": "A paper", "url": "https://nime.org/paper.pdf", "relevance": "Very close.", "embodied_cards": []}],
    }
    fields.update(overrides)
    return ProsecutorDraft.model_validate(fields)


def messages(problems: tuple[object, ...]) -> str:
    return " | ".join(str(p) for p in problems)


def test_specific_critique_passes_and_becomes_a_critique() -> None:
    good = draft()
    assert good.problems_for(IDEA, DRAW, CARD_WORDS) == ()
    critique = good.to_critique(RoleName.SKEPTIC, "claude-haiku-5-5", USAGE)
    assert critique.target is CritiqueTarget.BEHAVIOR and critique.target_card is None


def test_vague_failure_is_rejected() -> None:
    found = messages(draft(failure="This might be hard to build.").problems_for(IDEA, DRAW, CARD_WORDS))
    assert "8-40 words naming a specific failure" in found


def test_two_sentence_failure_is_rejected() -> None:
    found = messages(draft(failure=SPECIFIC + " It also costs a lot of money to run.").problems_for(IDEA, DRAW, CARD_WORDS))
    assert "one sentence" in found


def test_restatement_is_rejected() -> None:
    echo = "A webcomic that reveals each dark panel where the reader's fingers press the touchscreen, sounding chords."
    assert "restates the idea" in messages(draft(failure=echo).problems_for(IDEA, DRAW, CARD_WORDS))


def test_restatement_by_overlap() -> None:
    statement = Wording("A tape loop that slows down because the room gets colder over the night.")
    assert Wording("The tape loop slows down because the room gets colder at night.").restates(statement, frozenset())
    assert not Wording("Tape stretches unevenly below ten degrees, so pitch drifts randomly, not with the room.").restates(
        statement, frozenset()
    )


def test_card_reading_target_names_a_draw_card() -> None:
    card = DRAW.drawn_cards[1]
    assert draft(target="card_reading", target_card=card).problems_for(IDEA, DRAW, CARD_WORDS) == ()
    assert "draw's cards" in messages(draft(target="card_reading", target_card="nope").problems_for(IDEA, DRAW, CARD_WORDS))
    assert "must be empty" in messages(draft(target_card=card).problems_for(IDEA, DRAW, CARD_WORDS))


def test_shape_problems_from_parse() -> None:
    parsed, problems = CritiqueDraft.parse(json.dumps({"target": "vibes", "severity": "serious", "failure": "x", "argument": "y"}))
    assert parsed is None and any(p.field == "target" for p in problems)


def test_output_specs_are_strict() -> None:
    for kind in (CritiqueDraft, ProsecutorDraft):
        schema = json.loads(kind.output_spec().json_schema_text)
        assert schema["additionalProperties"] is False
        assert sorted(schema["required"]) == sorted(schema["properties"])
        assert set(schema["properties"]["target"]["enum"]) == {t.value for t in CritiqueTarget}
    assert ProsecutorDraft.output_spec().name == "prosecutor_draft"


# --- prosecutor evidence --------------------------------------------------------------


def test_cited_prosecution_passes() -> None:
    assert prosecution().evidence_problems(URLS, WORKS) == ()


def test_uncited_fatal_is_rejected() -> None:
    assert "need evidence" in messages(prosecution(citations=[]).evidence_problems(URLS, WORKS))


def test_invented_url_is_rejected_by_name() -> None:
    fake = [{"title": "t", "url": "https://made.up/x", "relevance": "r", "embodied_cards": []}]
    assert "https://made.up/x was not among" in messages(prosecution(citations=fake).evidence_problems(URLS, WORKS))


def test_unknown_work_id_is_rejected() -> None:
    work = [{"title": "t", "work_id": "ghost-work", "relevance": "r", "embodied_cards": []}]
    assert "ghost-work is not a catalog work id" in messages(prosecution(citations=work).evidence_problems(URLS, WORKS))


def test_citation_needs_one_source() -> None:
    both = [{"title": "t", "url": "https://nime.org/paper.pdf", "work_id": "oramics-demo-tape-1962", "relevance": "r"}]
    assert "exactly one of url and work_id" in messages(prosecution(citations=both).evidence_problems(URLS, WORKS))


def test_none_found_rules() -> None:
    nothing = prosecution(citations=[], none_found=True, severity="minor")
    assert nothing.evidence_problems(URLS, WORKS) == ()
    critique = nothing.to_prosecution("claude-sonnet-5-5", USAGE, DRAW)
    assert critique.none_found and critique.severity is Severity.MINOR and critique.citations == ()
    assert "severity minor" in messages(prosecution(citations=[], none_found=True).evidence_problems(URLS, WORKS))


def test_out_of_draw_citation_cards_are_dropped() -> None:
    inside, outside = DRAW.drawn_cards[0], "not-in-draw"
    cited = CitationDraft(title="t", url="https://nime.org/paper.pdf", relevance="r", embodied_cards=(inside, outside, inside))
    assert cited.to_citation(DRAW).embodied_cards == (inside,)


def test_work_citation_becomes_cited_work() -> None:
    work = [{"title": "Oramics", "work_id": "oramics-demo-tape-1962", "relevance": "r", "embodied_cards": []}]
    critique = prosecution(citations=work).to_prosecution("claude-sonnet-5-5", USAGE, DRAW)
    assert critique.citations[0].cited_work == "oramics-demo-tape-1962" and critique.citations[0].url is None


# --- 6.2 defense drafts ---------------------------------------------------------------

from seeker.debate.drafts import CardMention, DefenseDraft  # noqa: E402
from seeker.decks import DeckDirectory  # noqa: E402
from seeker.ontology import Critique, DefenseOutcome  # noqa: E402

DECKS = DeckDirectory(ROOT / "decks").load()
FOREIGN = tuple(card for deck in DECKS.decks for card in deck.cards if card.id not in DRAW.drawn_cards)
REVISED = "A webcomic whose panels stay dark until fingers press them, because touch is how the Lumigraph was played."


def critiques(*severities: str) -> tuple[Critique, ...]:
    roles = (RoleName.PROSECUTOR, RoleName.SKEPTIC, RoleName.TASTE_CRITIC)
    made = []
    for role, severity in zip(roles, severities):
        base = draft(severity=severity)
        if role is RoleName.PROSECUTOR:
            made.append(prosecution(severity=severity).to_prosecution("claude-sonnet-5-5", USAGE, DRAW))
        else:
            made.append(base.to_critique(role, "claude-haiku-5-5", USAGE))
    return tuple(made)


def defense(moves: dict[str, str], outcome: str = "defended", **revision: str) -> DefenseDraft:
    replies = [{"answers": role, "move": move, "argument": "Because."} for role, move in moves.items()]
    return DefenseDraft.model_validate({"replies": replies, "outcome": outcome, **revision})


ALL_REBUT = {"prosecutor": "rebut", "skeptic": "rebut", "taste_critic": "rebut"}
REVISION = {"statement": REVISED, "subject": "a webcomic", "behavior": "stays dark until pressed", "rationale": "touch played the Lumigraph"}


def test_full_defense_passes() -> None:
    answer = defense(ALL_REBUT)
    assert answer.problems_for(critiques("serious", "serious", "minor"), FOREIGN) == ()
    made = answer.to_defense("claude-opus-5-5", USAGE)
    assert made.outcome is DefenseOutcome.DEFENDED and made.revision is None and len(made.replies) == 3


def test_unanswered_critique_is_named() -> None:
    found = messages(defense({"prosecutor": "rebut", "skeptic": "rebut"}).problems_for(critiques("serious", "serious", "minor"), FOREIGN))
    assert "taste_critic critique exactly once" in found


def test_reply_to_a_missing_critique() -> None:
    found = messages(defense(ALL_REBUT).problems_for(critiques("serious", "serious"), FOREIGN))
    assert "no taste_critic critique" in found


def test_conceded_fatal_cannot_be_defended() -> None:
    moves = {**ALL_REBUT, "skeptic": "concede"}
    found = messages(defense(moves).problems_for(critiques("serious", "fatal", "minor"), FOREIGN))
    assert "revised or withdrawn" in found
    assert defense(moves, "withdrawn").problems_for(critiques("serious", "fatal", "minor"), FOREIGN) == ()
    assert defense(moves, "revised", **REVISION).problems_for(critiques("serious", "fatal", "minor"), FOREIGN) == ()


def test_conceding_a_serious_critique_may_still_defend() -> None:
    moves = {**ALL_REBUT, "skeptic": "concede"}
    assert defense(moves).problems_for(critiques("serious", "serious", "minor"), FOREIGN) == ()


def test_revision_is_the_competing_form() -> None:
    made = defense(ALL_REBUT, "revised", **REVISION).to_defense("claude-opus-5-5", USAGE)
    assert made.revision.statement == REVISED


def test_revision_must_be_one_sentence() -> None:
    two = {**REVISION, "statement": REVISED + " It is also cheap."}
    found = messages(defense(ALL_REBUT, "revised", **two).problems_for(critiques("serious", "serious", "minor"), FOREIGN))
    assert "one sentence" in found


def test_revision_parts_required_and_empty_otherwise() -> None:
    found = messages(defense(ALL_REBUT, "revised").problems_for(critiques("serious", "serious", "minor"), FOREIGN))
    assert "must not be blank when the outcome is revised" in found
    stray = messages(defense(ALL_REBUT, "defended", **REVISION).problems_for(critiques("serious", "serious", "minor"), FOREIGN))
    assert "empty unless revised" in stray


def test_revision_that_leaves_the_draw() -> None:
    outsider = next(card for card in FOREIGN if CardMention(card.name).distinctive)
    leaving = {**REVISION, "statement": f"A webcomic played through {outsider.name} because touch matters."}
    found = messages(defense(ALL_REBUT, "revised", **leaving).problems_for(critiques("serious", "serious", "minor"), FOREIGN))
    assert f"names {outsider.name}" in found


def test_card_mention_ignores_short_common_names() -> None:
    assert not CardMention("tape").found_in("a tape loop")
    assert CardMention("granular synthesis").found_in("uses Granular  Synthesis live")
    assert not CardMention("granular synthesis").found_in("granular textures")
