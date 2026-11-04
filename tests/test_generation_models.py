"""Unit tests for the generation ontology: Usage, Idea, Role, Generation, types."""

from datetime import datetime, timezone

import pytest
from pydantic import TypeAdapter, ValidationError

from seeker.ontology import (
    DrawBatch,
    Generation,
    GenerationFailure,
    GitCommit,
    Idea,
    ModelId,
    Reading,
    Role,
    Usage,
)

DIGEST = "b" * 64


def usage(i: int = 10, o: int = 5, r: int = 0, w: int = 0) -> Usage:
    return Usage(input_tokens=i, output_tokens=o, cache_read_tokens=r, cache_write_tokens=w)


def idea(position: int, cost: Usage | None = None) -> Idea:
    return Idea(
        position=position,
        statement="A zine that hums because paper is a speaker.",
        subject="a zine",
        behavior="hums",
        rationale="paper is a speaker",
        card_readings=[
            {"card": "one-page", "interpretation": "a single sheet"},
            {"card": "zine", "interpretation": "the format"},
            {"card": "piezo-contact-sensing", "interpretation": "paper as transducer"},
        ],
        usage=cost or usage(),
    )


def batch(size: int = 3) -> DrawBatch:
    return DrawBatch(
        seed=1,
        deck_set_digest=DIGEST,
        draws=[
            {
                "position": p,
                "axes": ["constraint", "medium", "technique"],
                "home_field": "writing",
                "drawn_cards": [f"c{p}", f"m{p}", f"t{p}"],
            }
            for p in range(1, size + 1)
        ],
    )


def generation(ideas: tuple, failures: tuple = (), total: Usage | None = None) -> Generation:
    return Generation(
        draw_batch=batch(),
        reading="literal",
        role_name="generator",
        model="claude-opus-5-5",
        role_digest=DIGEST,
        generated_at=datetime(2026, 11, 4, tzinfo=timezone.utc),
        ideas=ideas,
        failures=failures,
        usage=total if total is not None else Usage.total(tuple(r.usage for r in (*ideas, *failures))),
        estimated_cost_usd=0.01,
    )


def role(**overrides: object) -> dict:
    return {
        "role_name": "generator",
        "model": "claude-opus-5-5",
        "persona": "p",
        "system_prompt": "s",
        "reading_guidance": [{"reading": r.value, "guidance": f"{r.value} guidance"} for r in Reading],
        "max_output_tokens": 1200,
        "temperature": 1.0,
        **overrides,
    }


def test_usage_adds_and_totals() -> None:
    assert usage(1, 2, 3, 4) + usage(10, 20, 30, 40) == usage(11, 22, 33, 44)
    assert Usage.total(()) == Usage.zero()
    assert Usage.total((usage(1, 1), usage(2, 2), usage(3, 3))) == usage(6, 6)


def test_usage_rejects_negative() -> None:
    with pytest.raises(ValidationError):
        usage(-1)


def test_role_guidance_lookup() -> None:
    model = Role(**role())
    assert model.guidance_for(Reading.METAPHORICAL) == "metaphorical guidance"


@pytest.mark.parametrize(
    "guidance",
    [
        [{"reading": "literal", "guidance": "a"}, {"reading": "loose", "guidance": "b"}],
        [{"reading": "literal", "guidance": "a"}, {"reading": "literal", "guidance": "b"}, {"reading": "loose", "guidance": "c"}],
    ],
)
def test_role_needs_one_guidance_per_reading(guidance: list) -> None:
    with pytest.raises(ValidationError):
        Role(**role(reading_guidance=guidance))


@pytest.mark.parametrize(
    "overrides",
    [{"temperature": 1.5}, {"temperature": -0.1}, {"max_output_tokens": 0}, {"model": "gpt-4"}, {"role_name": "judge"}],
)
def test_role_bounds(overrides: dict) -> None:
    with pytest.raises(ValidationError):
        Role(**role(**overrides))


def test_type_patterns() -> None:
    assert TypeAdapter(ModelId).validate_python("claude-haiku-5-5") == "claude-haiku-5-5"
    commit = TypeAdapter(GitCommit).validate_python("a" * 40 + "-dirty")
    assert commit.is_dirty
    for bad, kind in (("Claude-Opus", ModelId), ("abc", GitCommit), ("a" * 40 + "-clean", GitCommit)):
        with pytest.raises(ValidationError):
            TypeAdapter(kind).validate_python(bad)


def test_idea_needs_three_card_readings() -> None:
    data = idea(1).model_dump()
    data["card_readings"] = data["card_readings"][:2]
    with pytest.raises(ValidationError):
        Idea(**data)


def test_generation_positions_and_totals() -> None:
    record = generation((idea(1), idea(3)), (GenerationFailure(position=2, reason="x", usage=usage()),))
    assert record.covered_positions == {1, 2, 3}
    assert record.remaining_positions == ()
    assert record.idea_at(3).position == 3
    assert record.usage == usage(30, 15)

    partial = generation((idea(1),))
    assert partial.remaining_positions == (2, 3)


@pytest.mark.parametrize(
    "build",
    [
        lambda: generation((idea(1), idea(1))),
        lambda: generation((idea(1),), (GenerationFailure(position=1, reason="x", usage=usage()),)),
        lambda: generation((idea(4),)),
        lambda: generation((idea(2), idea(1))),
        lambda: generation((idea(1),), total=usage(999)),
    ],
)
def test_generation_integrity(build: object) -> None:
    with pytest.raises(ValidationError):
        build()
