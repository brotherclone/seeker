"""Debate role files and the role set (debate-ideas tasks 4.1-4.2)."""

import shutil
from pathlib import Path

import pytest
import yaml

from seeker.config import SeekerConfig
from seeker.debate import DebateRoles, IdenticalCritics, UnpricedRole
from seeker.generate import LoadedRole, RoleFileError
from seeker.ontology import Reading, RoleName

ROOT = Path(__file__).resolve().parent.parent
PROMPTS = ROOT / "prompts"
PRICES = SeekerConfig.load(ROOT / "seeker.yaml").prices
DEBATE = ("prosecutor", "skeptic", "taste_critic", "advocate", "judge")


@pytest.mark.parametrize("name", DEBATE)
def test_role_file_loads_with_every_reading(name: str) -> None:
    role = LoadedRole.load(PROMPTS / f"{name}.yaml").role
    assert role.role_name.value == name
    assert {g.reading for g in role.reading_guidance} == set(Reading)


def test_only_the_prosecutor_searches() -> None:
    roles = DebateRoles.load(PROMPTS, PRICES)
    assert roles.role(RoleName.PROSECUTOR).role.max_searches == 3
    assert all(roles.role(n).role.max_searches == 0 for n in DebateRoles.ALL if n is not RoleName.PROSECUTOR)


def test_critics_differ_in_model_or_persona() -> None:
    roles = DebateRoles.load(PROMPTS, PRICES)
    voices = {(roles.role(n).role.model, roles.role(n).role.persona) for n in DebateRoles.CRITICS}
    assert len(voices) == 3


def test_digests_cover_the_five_roles() -> None:
    digests = DebateRoles.load(PROMPTS, PRICES).digests
    assert [d.role_name for d in digests] == list(DebateRoles.ALL)
    assert all(len(d.role_digest) == 64 for d in digests)


@pytest.fixture
def prompts(tmp_path: Path) -> Path:
    for name in DEBATE:
        shutil.copy(PROMPTS / f"{name}.yaml", tmp_path / f"{name}.yaml")
    return tmp_path


def test_identical_critics_are_refused(prompts: Path) -> None:
    skeptic = yaml.safe_load((prompts / "skeptic.yaml").read_text())
    taste = yaml.safe_load((prompts / "taste_critic.yaml").read_text())
    taste.update(model=skeptic["model"], persona=skeptic["persona"])
    (prompts / "taste_critic.yaml").write_text(yaml.safe_dump(taste, sort_keys=False))
    with pytest.raises(IdenticalCritics) as caught:
        DebateRoles.load(prompts, PRICES)
    assert "skeptic.yaml" in str(caught.value) and "taste_critic.yaml" in str(caught.value)


def test_unpriced_role_is_refused(prompts: Path) -> None:
    judge = prompts / "judge.yaml"
    judge.write_text(judge.read_text().replace("model: claude-sonnet-5-5", "model: claude-fable-5-2"))
    with pytest.raises(UnpricedRole, match="claude-fable-5-2"):
        DebateRoles.load(prompts, PRICES)


def test_misnamed_role_file_is_refused(prompts: Path) -> None:
    judge = prompts / "judge.yaml"
    judge.write_text(judge.read_text().replace("role_name: judge", "role_name: advocate"))
    with pytest.raises(RoleFileError, match="expected judge"):
        DebateRoles.load(prompts, PRICES)


def test_missing_role_file(prompts: Path) -> None:
    (prompts / "advocate.yaml").unlink()
    with pytest.raises(RoleFileError, match="advocate.yaml"):
        DebateRoles.load(prompts, PRICES)
