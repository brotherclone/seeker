"""One idea's round of debate against a scripted model (debate-ideas task 6.5)."""

import json
from datetime import date
from pathlib import Path

import yaml

from seeker.config import SeekerConfig
from seeker.debate import DebateRoles
from seeker.debate.debater import Debater
from seeker.models import ModelCallFailed, ModelReply, ScriptedModel, SearchResult
from seeker.ontology import DefenseOutcome, Generation, Reading, RoleName, SearchError, SearchTool, Usage
from seeker.works.catalog import WorkNotes
from vault_fixtures import repo_decks

ROOT = Path(__file__).resolve().parent.parent
GENERATION = Generation.model_validate(
    yaml.safe_load((ROOT / "generations" / "2026-11-04-round-1-literal.yaml").read_text())
)
IDEA, DRAW = GENERATION.ideas[0], GENERATION.draw_batch.draws[0]
ROLES = DebateRoles.load(ROOT / "prompts", SeekerConfig.load(ROOT / "seeker.yaml").prices)
CALL = Usage(input_tokens=100, output_tokens=50, cache_read_tokens=0, cache_write_tokens=0)
PAPER = "https://nime.org/proceedings/2019/touch-comic.pdf"


def critique_json(failure: str, severity: str = "serious", **extra: object) -> str:
    return json.dumps({"target": "behavior", "target_card": "", "severity": severity, "failure": failure,
                       "argument": "Specific reasons.", **extra})


PROSECUTION = critique_json(
    "A 2019 NIME paper already maps fingertip contact area on glass to chord voicings in a scrolling comic.",
    citations=[{"title": "Touch Comic", "url": PAPER, "work_id": "", "relevance": "Very close.", "embodied_cards": ["webcomic"]}],
    none_found=False,
)
SKEPTIC = critique_json("Measuring contact area needs a pressure-sensing screen that phones stopped shipping in 2019.")
TASTE = critique_json("Touch-to-reveal comics were a 2012 app-store gimmick and readers tired of them within minutes.")
DEFENSE = json.dumps({
    "replies": [{"answers": r, "move": "rebut", "argument": "Not so."} for r in ("prosecutor", "skeptic", "taste_critic")],
    "outcome": "defended", "statement": "", "subject": "", "behavior": "", "rationale": "",
})


def reply(text: str, *urls: str) -> ModelReply:
    return ModelReply(output_json=text, usage=CALL, search_results=tuple(SearchResult(url=u, title="t") for u in urls))


def debater(model: ScriptedModel, vault: Path) -> Debater:
    works = WorkNotes(folder=vault, deck_set=repo_decks())
    return Debater(ROLES, model, repo_decks(), works, Reading.LITERAL, date(2026, 11, 12))


def test_full_round(tmp_path: Path) -> None:
    model = ScriptedModel((reply(PROSECUTION, PAPER), reply(SKEPTIC), reply(TASTE), reply(DEFENSE)))
    outcome = debater(model, tmp_path).debate(IDEA, DRAW)
    debate = outcome.debate
    assert [c.role_name for c in debate.critiques] == [RoleName.PROSECUTOR, RoleName.SKEPTIC, RoleName.TASTE_CRITIC]
    assert debate.defense.outcome is DefenseOutcome.DEFENDED and debate.final_statement == IDEA.statement
    assert [c.model for c in debate.critiques] == ["claude-sonnet-5-5", "claude-haiku-5-5", "claude-sonnet-5-5"]
    assert debate.defense.model == "claude-opus-5-5"
    assert outcome.failures == () and len(outcome.captured) == 1
    assert outcome.usage.input_tokens == 400
    # Only the prosecutor is offered searches; no critic sees another's text.
    assert [r.max_searches for r in model.requests] == [3, 0, 0, 0]
    assert "pressure-sensing" not in model.requests[2].prompt
    assert "pressure-sensing" in model.requests[3].prompt


def test_critique_is_retried_with_feedback(tmp_path: Path) -> None:
    vague = critique_json("This might be hard to build.")
    model = ScriptedModel((reply(PROSECUTION, PAPER), reply(vague), reply(SKEPTIC), reply(TASTE), reply(DEFENSE)))
    outcome = debater(model, tmp_path).debate(IDEA, DRAW)
    assert "8-40 words" in model.requests[2].retry.feedback
    assert outcome.debate.critique_by(RoleName.SKEPTIC).usage.input_tokens == 200


def test_invented_url_is_retried(tmp_path: Path) -> None:
    model = ScriptedModel((reply(PROSECUTION), reply(PROSECUTION, PAPER), reply(SKEPTIC), reply(TASTE), reply(DEFENSE)))
    debater(model, tmp_path).debate(IDEA, DRAW)
    assert PAPER in model.requests[1].retry.feedback


def test_failing_critic_still_gets_the_advocate(tmp_path: Path) -> None:
    vague = critique_json("This might be hard to build.")
    two = json.dumps({**json.loads(DEFENSE), "replies": [
        {"answers": r, "move": "rebut", "argument": "No."} for r in ("prosecutor", "taste_critic")]})
    model = ScriptedModel((reply(PROSECUTION, PAPER), reply(vague), reply(vague), reply(TASTE), reply(two)))
    outcome = debater(model, tmp_path).debate(IDEA, DRAW)
    assert outcome.debate.short_a_critique and outcome.debate.competes
    (failure,) = outcome.failures
    assert failure.role_name is RoleName.SKEPTIC and "invalid after retry" in failure.failure_reason
    assert failure.usage.input_tokens == 200 and failure.model == "claude-haiku-5-5"


def test_failing_advocate_leaves_no_debate(tmp_path: Path) -> None:
    model = ScriptedModel((reply(PROSECUTION, PAPER), reply(SKEPTIC), reply(TASTE), ModelCallFailed("overloaded")))
    outcome = debater(model, tmp_path).debate(IDEA, DRAW)
    assert outcome.debate is None
    assert outcome.failures[-1].role_name is RoleName.ADVOCATE and "overloaded" in outcome.failures[-1].failure_reason
    assert outcome.usage.input_tokens == 300


def test_revision_competes(tmp_path: Path) -> None:
    revised = json.dumps({**json.loads(DEFENSE), "outcome": "revised",
        "statement": "A webcomic whose panels stay dark until fingers press them, because touch played the Lumigraph.",
        "subject": "a webcomic", "behavior": "stays dark until pressed", "rationale": "touch played the Lumigraph"})
    model = ScriptedModel((reply(PROSECUTION, PAPER), reply(SKEPTIC), reply(TASTE), reply(revised)))
    debate = debater(model, tmp_path).debate(IDEA, DRAW).debate
    assert debate.final_statement.startswith("A webcomic whose panels stay dark")


# --- fix-prior-art-search 3.1: search reports on critiques --------------------------

LIMIT = SearchError(error_code="max_uses_exceeded", error_message="max_uses_exceeded")


def searched(text: str, results: int, *errors: SearchError) -> ModelReply:
    urls = (PAPER, *(f"https://example.org/{i}" for i in range(results - 1))) if results else ()
    return reply(text, *urls).model_copy(update={"search_errors": errors})


def test_prosecutor_critique_records_its_search(tmp_path: Path) -> None:
    model = ScriptedModel((searched(PROSECUTION, 18), reply(SKEPTIC), reply(TASTE), reply(DEFENSE)))
    critiques = debater(model, tmp_path).debate(IDEA, DRAW).debate.critiques
    prosecution, skeptic, taste = critiques
    assert prosecution.search.results_returned == 18 and prosecution.search.search_errors == ()
    assert skeptic.search is None and taste.search is None
    assert model.requests[0].search_tool is SearchTool.BASIC
    assert all(r.search_tool is None for r in model.requests[1:])


def test_search_errors_are_recorded(tmp_path: Path) -> None:
    model = ScriptedModel((searched(PROSECUTION, 9, LIMIT), reply(SKEPTIC), reply(TASTE), reply(DEFENSE)))
    prosecution = debater(model, tmp_path).debate(IDEA, DRAW).debate.critiques[0]
    assert prosecution.search.results_returned == 9 and prosecution.search.search_errors == (LIMIT,)
    assert not prosecution.search.verified


def test_retried_prosecution_sums_both_attempts(tmp_path: Path) -> None:
    """The first answer cites a page its searches never returned, so it is retried."""
    model = ScriptedModel(
        (searched(PROSECUTION, 0, LIMIT), searched(PROSECUTION, 9), reply(SKEPTIC), reply(TASTE), reply(DEFENSE))
    )
    prosecution = debater(model, tmp_path).debate(IDEA, DRAW).debate.critiques[0]
    assert len(model.requests) == 5 and model.requests[1].retry is not None
    assert prosecution.search.results_returned == 9 and prosecution.search.search_errors == (LIMIT,)


def test_failed_retry_keeps_the_searches_already_gathered(tmp_path: Path) -> None:
    """The first answer is rejected; the retry's model call fails. The failure still
    records what the first call's searches returned and the error they hit."""
    vague = critique_json("This might have been done.", citations=[], none_found=True, severity="minor")
    model = ScriptedModel((searched(vague, 9, LIMIT), ModelCallFailed("overloaded")))
    failure = debater(model, tmp_path)._prosecute(IDEA, DRAW)
    assert len(model.requests) == 2 and model.requests[1].retry is not None
    assert failure.role_name is RoleName.PROSECUTOR and "overloaded" in failure.failure_reason
    assert failure.search.results_returned == 9 and failure.search.search_errors == (LIMIT,)
    assert failure.usage.input_tokens == 100


def test_invalid_after_retry_keeps_both_calls_searches(tmp_path: Path) -> None:
    """Both answers cite a page no search returned."""
    elsewhere = tuple(f"https://other.org/{i}" for i in range(4))
    first = reply(PROSECUTION, *elsewhere)
    second = reply(PROSECUTION, "https://other.org/x").model_copy(update={"search_errors": (LIMIT,)})
    model = ScriptedModel((first, second))
    failure = debater(model, tmp_path)._prosecute(IDEA, DRAW)
    assert "invalid after retry" in failure.failure_reason
    assert failure.search.results_returned == 5 and failure.search.search_errors == (LIMIT,)


def test_failing_non_searching_critic_records_no_search(tmp_path: Path) -> None:
    vague = critique_json("This might be hard to build.")
    model = ScriptedModel((reply(vague), ModelCallFailed("overloaded")))
    failure = debater(model, tmp_path)._critique(RoleName.SKEPTIC, IDEA, DRAW)
    assert "overloaded" in failure.failure_reason and failure.search is None


# --- fix-prior-art-search 3.3: a retry may cite the first call's results -------------


def test_retry_may_cite_what_the_first_call_returned(tmp_path: Path) -> None:
    """The first answer has a vague failure; the retry runs no search and re-cites the paper."""
    vague = critique_json(
        "This might have been done.",
        citations=[{"title": "Touch Comic", "url": PAPER, "work_id": "", "relevance": "Very close.", "embodied_cards": ["webcomic"]}],
        none_found=False,
    )
    model = ScriptedModel((reply(vague, PAPER), reply(PROSECUTION), reply(SKEPTIC), reply(TASTE), reply(DEFENSE)))
    outcome = debater(model, tmp_path).debate(IDEA, DRAW)
    assert model.requests[1].retry is not None and outcome.failures == ()
    prosecution = outcome.debate.critiques[0]
    assert str(prosecution.citations[0].url) == PAPER
    assert prosecution.search.results_returned == 1


def test_a_url_no_call_returned_is_still_rejected(tmp_path: Path) -> None:
    model = ScriptedModel((reply(PROSECUTION, "https://other.org"), reply(PROSECUTION)))
    failure = debater(model, tmp_path)._prosecute(IDEA, DRAW)
    assert failure.role_name is RoleName.PROSECUTOR and len(model.requests) == 2
    assert PAPER in failure.failure_reason and "not among" in failure.failure_reason
