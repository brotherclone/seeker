"""The generator role end to end, against ScriptedModel (spec: idea-generation)."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from seeker.config import SeekerConfig
from seeker.decks import DeckDirectory
from seeker.draw import BatchDrawer
from seeker.generate import (
    DrawPrompt,
    GenerationFile,
    IdeaDraft,
    IdeaGenerator,
    LoadedRole,
    ResumeMismatch,
    RoleFileError,
    Sentence,
    SystemPrompt,
    UnpricedModel,
)
from seeker.models import ModelCallFailed, ModelReply, ScriptedModel
from seeker.ontology import DeckSet, Draw, DrawBatch, Reading, Usage

ROOT = Path(__file__).resolve().parent.parent
ROLE_PATH = ROOT / "prompts" / "generator.yaml"
CALL = Usage(input_tokens=100, output_tokens=50, cache_read_tokens=900, cache_write_tokens=0)


@pytest.fixture(scope="module")
def deck_set() -> DeckSet:
    return DeckDirectory(ROOT / "decks").load()


@pytest.fixture(scope="module")
def batch(deck_set: DeckSet) -> DrawBatch:
    return BatchDrawer(deck_set).draw(7, 12)


@pytest.fixture(scope="module")
def config() -> SeekerConfig:
    return SeekerConfig.load(ROOT / "seeker.yaml")


@pytest.fixture(scope="module")
def role() -> LoadedRole:
    return LoadedRole.load(ROLE_PATH)


def answer(draw: Draw, statement: str | None = None, cards: tuple[str, ...] | None = None) -> ModelReply:
    body = {
        "statement": statement or f"A thing for draw {draw.position} that hums because paper is a speaker.",
        "subject": "a thing",
        "behavior": "hums",
        "rationale": "paper is a speaker",
        "card_readings": [{"card": c, "interpretation": f"read {c}"} for c in (cards or draw.drawn_cards)],
    }
    return ModelReply(output_json=json.dumps(body), usage=CALL)


def generator(role: LoadedRole, model: ScriptedModel, deck_set: DeckSet, config: SeekerConfig) -> IdeaGenerator:
    return IdeaGenerator(role, model, deck_set, config.prices)


# --- 4.1 role file ---------------------------------------------------------------


def test_generator_role_loads(role: LoadedRole) -> None:
    assert role.role.role_name == "generator"
    assert {g.reading for g in role.role.reading_guidance} == set(Reading)
    assert len(role.digest) == 64


def test_role_missing_guidance(tmp_path: Path) -> None:
    text = ROLE_PATH.read_text()
    broken = tmp_path / "generator.yaml"
    broken.write_text(text[: text.index("  - reading: metaphorical")])
    with pytest.raises(RoleFileError) as exc:
        LoadedRole.load(broken)
    assert str(broken) in str(exc.value) and "metaphorical" in str(exc.value)


# --- 4.2 prompts -------------------------------------------------------------------


def test_card_note_and_details_reach_the_prompt(deck_set: DeckSet, batch: DrawBatch) -> None:
    noted = next(d for d in batch.draws if any(deck_set.card(c).note for c in d.drawn_cards))
    rendered = DrawPrompt(noted, deck_set).render()
    for card_id in noted.drawn_cards:
        card = deck_set.card(card_id)
        assert card.name in rendered and f"(id: {card.id})" in rendered
        if card.note:
            assert card.note in rendered
        for synonym in card.synonyms:
            assert synonym in rendered
    assert f"Home field: {noted.home_field.value}" in rendered


@pytest.mark.parametrize("reading", list(Reading))
def test_only_the_selected_guidance_is_in_the_system_prompt(role: LoadedRole, reading: Reading) -> None:
    system = SystemPrompt(role.role, reading).render()
    for other in Reading:
        guidance = role.role.guidance_for(other).strip()
        assert (guidance in system) == (other is reading)


def test_unknown_reading_names_the_three() -> None:
    with pytest.raises(ValueError) as exc:
        Reading("surreal")
    assert "surreal" in str(exc.value)
    assert [r.value for r in Reading] == ["literal", "loose", "metaphorical"]


# --- 4.3 draft validation --------------------------------------------------------


@pytest.mark.parametrize(
    ("statement", "breaks"),
    [
        ("A zine that hums because paper is a speaker.", 0),
        ("A zine. It hums because paper is a speaker.", 1),
        ("A score, e.g. a scroll, that sings because Dr. Oram drew it.", 0),
        ("A J. S. Bach automaton that plays because it can!", 0),
        ("It hums! It sings? It stops.", 2),
    ],
)
def test_sentence_boundaries(statement: str, breaks: int) -> None:
    assert Sentence(statement).boundaries() == breaks


def test_draft_problems(batch: DrawBatch) -> None:
    draw = batch.draws[0]
    good = IdeaDraft.model_validate_json(answer(draw).output_json)
    assert good.problems_for(draw) == ()

    def problems(**kw: object) -> list[str]:
        draft = IdeaDraft.model_validate_json(answer(draw, **kw).output_json)
        return [p.field for p in draft.problems_for(draw)]

    assert problems(statement="A zine. It hums.") == ["statement"]
    assert problems(statement="word " * 61 + "end.") == ["statement"]
    cards = draw.drawn_cards
    assert problems(cards=(cards[0], cards[1], "not-a-card")) == ["card_readings"]
    assert problems(cards=(cards[1], cards[0], cards[2])) == ["card_readings"]


def test_draft_shape_problems() -> None:
    draft, problems = IdeaDraft.parse('{"statement": "x"}')
    assert draft is None and {p.field for p in problems} >= {"subject", "card_readings"}


# --- 4.4 the loop -----------------------------------------------------------------


def test_twelve_ideas(role, config, deck_set, batch) -> None:
    model = ScriptedModel(tuple(answer(d) for d in batch.draws))
    result = generator(role, model, deck_set, config).generate(batch)
    assert [i.position for i in result.ideas] == list(range(1, 13))
    assert result.failures == () and result.reading is Reading.LITERAL
    assert result.usage == Usage.total(tuple(i.usage for i in result.ideas))
    price = config.prices.price_for("claude-opus-5-5")
    assert result.estimated_cost_usd == pytest.approx(price.cost(result.usage))
    assert all(r.output.name == "idea_draft" for r in model.requests)


def test_recovers_on_retry_and_counts_both_calls(role, config, deck_set, batch) -> None:
    first = batch.draws[0]
    replies = (answer(first, statement="Two. Sentences."), *(answer(d) for d in batch.draws))
    model = ScriptedModel(replies)
    result = generator(role, model, deck_set, config).generate(batch)
    assert result.idea_at(1).usage == CALL + CALL
    retry = model.requests[1].retry
    assert retry is not None and "one sentence" in retry.feedback
    assert retry.previous_output == replies[0].output_json


def test_double_failure_is_recorded_and_the_batch_continues(role, config, deck_set, batch) -> None:
    replies = []
    for draw in batch.draws:
        if draw.position == 4:
            replies += [answer(draw, statement="Bad. Bad."), answer(draw, statement="Worse. Worse.")]
        else:
            replies.append(answer(draw))
    result = generator(role, ScriptedModel(tuple(replies)), deck_set, config).generate(batch)
    (failure,) = result.failures
    assert failure.position == 4 and "one sentence" in failure.reason
    assert failure.usage == CALL + CALL
    assert [i.position for i in result.ideas] == [p for p in range(1, 13) if p != 4]
    assert result.usage == Usage.total(tuple(r.usage for r in (*result.ideas, *result.failures)))


def test_call_failure_is_recorded(role, config, deck_set, batch) -> None:
    replies = (ModelCallFailed("overloaded"), *(answer(d) for d in batch.draws[1:]))
    result = generator(role, ScriptedModel(replies), deck_set, config).generate(batch)
    assert result.failures[0].position == 1 and "overloaded" in result.failures[0].reason


def test_unpriced_model_makes_no_calls(role, config, deck_set, tmp_path) -> None:
    text = ROLE_PATH.read_text().replace("model: claude-opus-5-5", "model: claude-unpriced-9")
    path = tmp_path / "generator.yaml"
    path.write_text(text)
    model = ScriptedModel(())
    with pytest.raises(UnpricedModel, match="claude-unpriced-9"):
        IdeaGenerator(LoadedRole.load(path), model, deck_set, config.prices)
    assert model.requests == []


# --- 4.5 records, resume, provenance -------------------------------------------------


def test_incremental_write_and_resume(role, config, deck_set, batch, tmp_path) -> None:
    out = GenerationFile(tmp_path / "gen.yaml")
    first_five = ScriptedModel(tuple(answer(d) for d in batch.draws[:5]))
    from seeker.models import ScriptExhausted

    with pytest.raises(ScriptExhausted):
        generator(role, first_five, deck_set, config).generate(batch, sink=out)
    partial = out.read()
    assert [i.position for i in partial.ideas] == [1, 2, 3, 4, 5]

    rest = ScriptedModel(tuple(answer(d) for d in batch.draws[5:]))
    finished = generator(role, rest, deck_set, config).generate(batch, record=partial, sink=out)
    assert len(rest.requests) == 7
    assert all(r.prompt.count("(id: ") == 3 for r in rest.requests)
    assert [i.position for i in finished.ideas] == list(range(1, 13))
    assert out.read() == finished
    assert finished.generated_at == partial.generated_at


def test_resume_mismatch_names_both_readings(role, config, deck_set, batch) -> None:
    record = generator(role, ScriptedModel((answer(batch.draws[0]),)), deck_set, config).generate(
        DrawBatch(seed=batch.seed, deck_set_digest=batch.deck_set_digest, draws=batch.draws[:1])
    ).model_copy(update={"draw_batch": batch})
    with pytest.raises(ResumeMismatch) as exc:
        generator(role, ScriptedModel(()), deck_set, config).generate(batch, Reading.METAPHORICAL, record=record)
    assert "'literal'" in str(exc.value) and "'metaphorical'" in str(exc.value)


def test_role_edit_changes_digest(tmp_path) -> None:
    path = tmp_path / "generator.yaml"
    path.write_text(ROLE_PATH.read_text())
    before = LoadedRole.load(path).digest
    path.write_text(ROLE_PATH.read_text() + "# tweak\n")
    assert LoadedRole.load(path).digest != before


def test_record_is_a_schema_instance(role, config, deck_set, batch, tmp_path) -> None:
    out = GenerationFile(tmp_path / "gen.yaml")
    result = generator(role, ScriptedModel(tuple(answer(d) for d in batch.draws)), deck_set, config).generate(
        batch, sink=out
    )
    assert out.read() == result
    tool = shutil.which("linkml-validate")
    if tool is None:
        pytest.skip("linkml-validate not installed")
    check = subprocess.run(
        [tool, "-s", str(ROOT / "schema" / "seeker.yaml"), "-C", "Generation", str(out.path)],
        capture_output=True,
        text=True,
    )
    assert check.returncode == 0, check.stdout + check.stderr


def test_git_commit_provenance() -> None:
    from seeker.generate import GitRepo

    commit = GitRepo(ROOT).commit()
    if commit is None:
        pytest.skip("not a git checkout")
    assert len(commit.removesuffix("-dirty")) == 40
