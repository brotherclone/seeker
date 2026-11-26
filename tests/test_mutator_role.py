"""The mutator role file: valid, on the generator's model and persona, and the
generator's own file untouched."""

from pathlib import Path

from seeker.generate.role_file import LoadedRole
from seeker.ontology import Effort, RoleName

PROMPTS = Path(__file__).resolve().parent.parent / "prompts"


def test_mutator_loads_with_the_generators_voice() -> None:
    mutator = LoadedRole.load(PROMPTS / "mutator.yaml").role
    generator = LoadedRole.load(PROMPTS / "generator.yaml").role
    assert mutator.role_name is RoleName.MUTATOR
    assert mutator.model == generator.model == "claude-opus-5-5"
    assert mutator.effort is Effort.HIGH
    assert mutator.persona == generator.persona
    assert mutator.reading_guidance == generator.reading_guidance
    assert "Reworking" in mutator.system_prompt and "Card swap" in mutator.system_prompt


def test_generator_file_still_matches_round_one() -> None:
    """Round-1 generations pin the generator's digest; adding the mutator must not change it."""
    import yaml

    record = yaml.safe_load((PROMPTS.parent / "generations" / "2026-11-04-round-1-literal.yaml").read_text())
    assert LoadedRole.load(PROMPTS / "generator.yaml").digest == record["role_digest"]
