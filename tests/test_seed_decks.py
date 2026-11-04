"""Content checks on the seeded decks in decks/ (spec: Seed deck size,
Seed decks cover every creative field, Deck files are schema instances)."""

import shutil
import subprocess
from pathlib import Path

import pytest

from seeker.decks import DeckDirectory, FieldCoverage
from seeker.ontology import CreativeField, DeckSet

ROOT = Path(__file__).resolve().parent.parent
DECKS = ROOT / "decks"
CORE_AXES = ("technique", "medium", "historical-artifact", "constraint")
SIZE = {**{axis: (24, 40) for axis in CORE_AXES}, "domain": (12, 20)}
MIN_PER_FIELD = 3


@pytest.fixture(scope="module")
def seeded() -> DeckSet:
    return DeckDirectory(DECKS).load()


def test_seeded_decks_validate(seeded: DeckSet) -> None:
    assert set(DeckSet.REQUIRED_AXES) <= set(seeded.axes)


@pytest.mark.parametrize("axis", sorted(SIZE))
def test_seed_deck_size(seeded: DeckSet, axis: str) -> None:
    low, high = SIZE[axis]
    assert low <= len(seeded.deck(axis)) <= high


@pytest.mark.parametrize("axis", CORE_AXES)
@pytest.mark.parametrize("field", list(CreativeField), ids=str)
def test_seed_decks_cover_every_field(seeded: DeckSet, axis: str, field: CreativeField) -> None:
    (row,) = [r for r in FieldCoverage.of_deck(seeded.deck(axis)) if r.field is field]
    assert row.count >= MIN_PER_FIELD, f"{axis} has only {row.count} {field} cards"


def test_deck_files_are_schema_instances() -> None:
    tool = shutil.which("linkml-validate")
    if tool is None:
        pytest.skip("linkml-validate not installed (install the dev extra)")
    result = subprocess.run(
        [tool, "-s", "schema/seeker.yaml", "-C", "Deck", *sorted(str(p.relative_to(ROOT)) for p in DECKS.glob("*.yaml"))],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_readme_example_is_a_valid_deck() -> None:
    import re

    import yaml

    from seeker.ontology import Deck

    block = re.search(r"```yaml\n(.*?)```", (DECKS / "README.md").read_text(), re.S)
    assert block is not None
    deck = Deck.model_validate(yaml.safe_load(block.group(1)))
    assert deck.cards[0].id == "granular-synthesis"
