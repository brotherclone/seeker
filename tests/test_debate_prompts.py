"""Critic and advocate prompts (debate-ideas task 6.3)."""

from pathlib import Path

import yaml

from seeker.debate import DebateRoles
from seeker.debate.drafts import CritiqueDraft
from seeker.debate.prompts import AdvocatePrompt, CriticPrompt, ProsecutorPrompt
from seeker.config import SeekerConfig
from seeker.generate import SystemPrompt
from seeker.ontology import Generation, Reading, RoleName, Usage
from seeker.works.catalog import WorkNotes
from seeker.works.check import DrawPriorArt
from vault_fixtures import repo_decks, work_note

ROOT = Path(__file__).resolve().parent.parent
GENERATION = Generation.model_validate(
    yaml.safe_load((ROOT / "generations" / "2026-11-04-round-1-literal.yaml").read_text())
)
IDEA, DRAW = GENERATION.ideas[0], GENERATION.draw_batch.draws[0]
DECKS = repo_decks()
USAGE = Usage(input_tokens=1, output_tokens=1, cache_read_tokens=0, cache_write_tokens=0)
ROLES = DebateRoles.load(ROOT / "prompts", SeekerConfig.load(ROOT / "seeker.yaml").prices)


def prior_art(folder: Path) -> DrawPriorArt:
    return DrawPriorArt.of(WorkNotes(folder=folder, deck_set=DECKS).catalog(), DRAW)


def test_critic_prompt_shows_the_idea_and_cards_in_full() -> None:
    text = CriticPrompt(IDEA, DRAW, DECKS).render()
    assert IDEA.statement in text and IDEA.rationale in text
    for card_id in DRAW.drawn_cards:
        assert f"(id: {card_id})" in text
    assert all(reading.interpretation in text for reading in IDEA.card_readings)


def test_catalog_hit_reaches_the_prosecutor(tmp_path: Path) -> None:
    work_note(tmp_path, "light comic", cards='["[[lumigraph]]", "[[webcomic]]"]')
    text = ProsecutorPrompt(IDEA, DRAW, DECKS, prior_art(tmp_path)).render()
    assert "work id light-comic" in text and "webcomic, lumigraph" in text


def test_empty_catalog_is_said_plainly(tmp_path: Path) -> None:
    text = ProsecutorPrompt(IDEA, DRAW, DECKS, prior_art(tmp_path)).render()
    assert "the catalog has no prior art for this draw" in text


def test_full_hit_is_marked(tmp_path: Path) -> None:
    work_note(tmp_path, "everything", cards='["[[lumigraph]]", "[[webcomic]]", "[[no-keyboard]]"]')
    assert "links all three cards" in ProsecutorPrompt(IDEA, DRAW, DECKS, prior_art(tmp_path)).render()


def test_critics_never_see_each_other() -> None:
    skeptic = CritiqueDraft(
        target="behavior",
        severity="serious",
        failure="A UNIQUE-SKEPTIC-FAILURE about pressure-sensitive glass costing more than the whole budget.",
        argument="UNIQUE-SKEPTIC-ARGUMENT",
    ).to_critique(RoleName.SKEPTIC, "claude-haiku-5-5", USAGE)
    taste = CriticPrompt(IDEA, DRAW, DECKS).render()
    assert "UNIQUE-SKEPTIC" not in taste
    advocate = AdvocatePrompt(IDEA, DRAW, DECKS, (skeptic,)).render()
    assert "UNIQUE-SKEPTIC-FAILURE" in advocate and "Critique from skeptic" in advocate


def test_reading_guidance_is_in_each_system_prompt() -> None:
    for name in DebateRoles.ALL:
        role = ROLES.role(name).role
        text = SystemPrompt(role, Reading.METAPHORICAL).render()
        assert role.guidance_for(Reading.METAPHORICAL).strip() in text
        assert role.guidance_for(Reading.LITERAL).strip() not in text
