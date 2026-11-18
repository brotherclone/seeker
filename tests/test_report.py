"""The survivors report's judge-health and lineage sections (mutate-ideas 6.1-6.2)."""

from pathlib import Path

import pytest
import yaml

from seeker.config import SeekerConfig
from seeker.debate.health import JudgeHealth
from seeker.debate.report import SurvivorReport
from seeker.decks import DeckDirectory
from seeker.ontology import (
    AxisVerdict,
    Comparison,
    DebateRun,
    Generation,
    MutationKind,
    RoleName,
    ScoreAxis,
    SearchError,
    SearchReport,
    Usage,
)

ROOT = Path(__file__).resolve().parent.parent
RUN = ROOT / "debates" / "2026-11-14-round-1-literal.yaml"
CONFIG = SeekerConfig.load(ROOT / "seeker.yaml")
DECKS = DeckDirectory(CONFIG.paths.decks).load()


@pytest.fixture(scope="module")
def round_one() -> tuple[DebateRun, Generation]:
    run = DebateRun.model_validate(yaml.safe_load(RUN.read_text()))
    generation = Generation.model_validate(yaml.safe_load((ROOT / run.generation_path).read_text()))
    return run, generation


def test_round_one_position_bias(round_one) -> None:
    run, _ = round_one
    health = JudgeHealth.of(run)
    shares = {a.axis: (a.a_wins, a.judged, a.splits) for a in health.axes}
    assert shares == {
        ScoreAxis.NOVELTY: (44, 66, None),
        ScoreAxis.FEASIBILITY: (29, 66, None),
        ScoreAxis.PROMISE: (34, 66, None),
    }


def test_round_one_report_shows_health(round_one) -> None:
    run, generation = round_one
    text = SurvivorReport(run, generation, DECKS, CONFIG.prices).render()
    assert "- novelty: A won 44 of 66 (67%)" in text
    assert "- feasibility: A won 29 of 66 (44%)" in text
    assert "- promise: A won 34 of 66 (52%)" in text
    assert "- skeptic: fatal 0, serious 12, minor 0" in text
    assert "Defense outcomes: defended 0, revised 12, withdrawn 0" in text
    assert "## Lineage" not in text and "Lineage |" not in text


def comparison(first: int, second: int, winner: int) -> Comparison:
    verdicts = tuple(AxisVerdict(axis_name=axis, winner=winner, ruling="Specific.") for axis in ScoreAxis)
    return Comparison(first=first, second=second, verdicts=verdicts, model="claude-sonnet-5-5", usage=Usage.zero())


def test_split_pairs_are_counted(round_one) -> None:
    run, _ = round_one
    # (3, 7) judged "A" both times: a different idea won each order, one split. (3, 4) agreed: no split.
    comparisons = (comparison(3, 7, 3), comparison(7, 3, 7), comparison(3, 4, 3), comparison(4, 3, 3))
    tournament = run.tournament.model_copy(update={"comparisons": comparisons, "both_orders": True})
    health = JudgeHealth.of(run.model_copy(update={"tournament": tournament}))
    novelty = health.bias_on(ScoreAxis.NOVELTY)
    assert (novelty.splits, novelty.pairs, novelty.a_wins, novelty.judged) == (1, 2, 3, 4)


def test_mutated_round_report_shows_lineage(tmp_path: Path) -> None:
    from seeker.debate.elo import Ratings, Survivors
    from tests.mutation_fixtures import mutated_generation

    generation = Generation.model_validate(yaml.safe_load(mutated_generation(tmp_path / "r2.yaml").read_text()))
    parent = DebateRun.model_validate(yaml.safe_load(RUN.read_text()))
    # Build a round-2 run: each child reuses its parent's debate, renumbered; carried ones are marked.
    debates = []
    for idea in generation.ideas:
        source = parent.debate_at(idea.lineage.parent_position)
        carried = idea.lineage.parent_position if idea.lineage.mutation_kind is MutationKind.CARRIED else None
        debates.append(source.model_copy(update={"position": idea.position, "carried_from": carried}))
    entrants = tuple(range(1, 16))
    # Child 1 beats its carried parent 13 every time; parent 13 beats child 2.
    comparisons = (comparison(1, 13, 1), comparison(13, 1, 1), comparison(13, 2, 13), comparison(2, 13, 13))
    ratings = Ratings.recompute(entrants, comparisons, 32.0, 1500.0)
    tournament = parent.tournament.model_copy(update={
        "entrants": entrants, "comparisons": comparisons, "ratings": ratings,
        "survivors": Survivors.pick(ratings), "both_orders": True,
    })
    run = parent.model_copy(update={"debates": tuple(debates), "tournament": tournament})
    changed = parent.model_copy(update={"role_digests": tuple(
        d.model_copy(update={"role_digest": "0" * 64}) if d.role_name.value == "skeptic" else d
        for d in parent.role_digests
    )})
    text = SurvivorReport(run, generation, DECKS, CONFIG.prices, parent=changed).render()
    assert "- **Lineage:** reworking of #10 ↑" in text  # child 1 is the top survivor
    assert "| reworking of #10 ↓ |" in text  # child 2 lost to its parent
    assert "card swap (domain) of #10" in text
    assert "**#13 (was #10):**" in text and "carried #10" in text
    assert "## Lineage" in text and "1 of 2 pairs split" not in text
    assert "role files changed since the parent run (skeptic)" in text


def test_a_tie_with_the_parent_is_neither_up_nor_down(tmp_path: Path) -> None:
    from seeker.debate.elo import Ratings
    from tests.mutation_fixtures import mutated_generation

    generation = Generation.model_validate(yaml.safe_load(mutated_generation(tmp_path / "r2.yaml").read_text()))
    run = DebateRun.model_validate(yaml.safe_load(RUN.read_text()))
    entrants = tuple(range(1, 16))
    ratings = Ratings.recompute(entrants, (), 32.0, 1500.0)  # nobody judged yet: every rating ties at 1500
    tournament = run.tournament.model_copy(update={"entrants": entrants, "comparisons": (), "ratings": ratings})
    report = SurvivorReport(run.model_copy(update={"tournament": tournament}), generation, DECKS, CONFIG.prices)
    assert report.lineage_tag(1) == "reworking of #10 ="
    assert report.lineage_tag(13) == "carried #10"


# --- fix-prior-art-search 4.1: search health -----------------------------------------


def with_search(run: DebateRun, failing: int) -> DebateRun:
    """Every prosecution searched: 9 results each, except ``failing``, which hit the limit."""
    limit = SearchError(error_code="max_uses_exceeded", error_message="max_uses_exceeded")
    debates = []
    for debate in run.debates:
        critiques = tuple(
            c.model_copy(
                update={
                    "search": SearchReport(results_returned=0, search_errors=(limit,))
                    if debate.position == failing
                    else SearchReport(results_returned=9)
                }
            )
            if c.role_name is RoleName.PROSECUTOR
            else c
            for c in debate.critiques
        )
        debates.append(debate.model_copy(update={"critiques": critiques}))
    return run.model_copy(update={"debates": tuple(debates)})


def test_search_health_is_counted_and_shown(round_one) -> None:
    run, generation = round_one
    searched = with_search(run, failing=10)  # survivor 1, so its critiques are shown
    urls = sum(1 for d in run.debates for c in d.critiques for x in c.citations if x.url is not None)
    health = JudgeHealth.of(searched).search
    assert (health.prosecutions, health.with_results, health.with_errors, health.citations) == (12, 11, 1, urls)
    text = SurvivorReport(searched, generation, DECKS, CONFIG.prices).render()
    assert f"Prior-art search: 11 of 12 prosecutions with results, 1 with errors, {urls} citations" in text
    assert "*Search: 9 results*" in text
    assert "*Search: 0 results; errors: max_uses_exceeded*" in text


def test_round_two_says_search_was_not_recorded() -> None:
    run = DebateRun.model_validate(
        yaml.safe_load((ROOT / "debates" / "2026-11-16-round-2-literal.yaml").read_text())
    )
    generation = Generation.model_validate(yaml.safe_load((ROOT / run.generation_path).read_text()))
    assert JudgeHealth.of(run).search is None
    text = SurvivorReport(run, generation, DECKS, CONFIG.prices).render()
    assert "Prior-art search: search outcomes were not recorded for this run." in text
    assert "*Search:" not in text
