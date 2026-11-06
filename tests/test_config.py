"""seeker.yaml loading, path resolution, prices and the API key."""

from pathlib import Path

import pytest

from seeker.config import ConfigError, DotEnv, MissingApiKey, SeekerConfig, VaultNotConfigured
from seeker.ontology import Usage

ROOT = Path(__file__).resolve().parent.parent

MINIMAL = """\
paths: {decks: decks, batches: batches, generations: gens, prompts: prompts, vault: ~/vault}
prices:
  as_of: 2026-11-04
  models:
    - {model: claude-opus-5-5, input: 4.0, output: 20.0, cache_read: 0.4, cache_write: 5.0}
"""


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SEEKER_CONFIG", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def write(folder: Path, text: str = MINIMAL) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "seeker.yaml"
    path.write_text(text)
    return path


def test_repo_config_loads() -> None:
    config = SeekerConfig.load(ROOT / "seeker.yaml")
    assert config.paths.decks == ROOT / "decks"
    assert config.prices.price_for("claude-haiku-5-5") is not None


def test_discovery_walks_up(tmp_path: Path) -> None:
    write(tmp_path)
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    assert SeekerConfig.find(nested) == tmp_path / "seeker.yaml"


def test_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = write(tmp_path / "elsewhere")
    monkeypatch.setenv("SEEKER_CONFIG", str(path))
    assert SeekerConfig.find(tmp_path) == path.resolve()


def test_missing_config(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        SeekerConfig.find(tmp_path)


def test_paths_resolve_relative_and_home(tmp_path: Path) -> None:
    config = SeekerConfig.load(write(tmp_path))
    assert config.paths.generations == (tmp_path / "gens").resolve()
    assert config.paths.vault == Path("~/vault").expanduser()


def test_api_key_in_config_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="ANTHROPIC_API_KEY environment variable or a git-ignored .env"):
        SeekerConfig.load(write(tmp_path, MINIMAL + "api_key: sk-nope\n"))


def test_api_key_precedence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = SeekerConfig.load(write(tmp_path))
    with pytest.raises(MissingApiKey, match=r"\.env"):
        config.api_key()
    (tmp_path / ".env").write_text("# comment\nexport ANTHROPIC_API_KEY='from-dotenv'\n")
    assert config.api_key().get_secret_value() == "from-dotenv"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-env")
    assert config.api_key().get_secret_value() == "from-env"


def test_dotenv_missing_file(tmp_path: Path) -> None:
    assert DotEnv(tmp_path / ".env").get("X") is None


def test_unpriced_model_and_cost(tmp_path: Path) -> None:
    prices = SeekerConfig.load(write(tmp_path)).prices
    assert prices.price_for("claude-sonnet-5-5") is None
    usage = Usage(input_tokens=1_000_000, output_tokens=500_000, cache_read_tokens=2_000_000, cache_write_tokens=100_000)
    # 4.00 + 10.00 + 0.80 + 0.50
    assert prices.price_for("claude-opus-5-5").cost(usage) == pytest.approx(15.30)


def test_missing_config_path_is_a_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="no such config file"):
        SeekerConfig.load(tmp_path / "missing.yaml")


def test_unreadable_config_is_a_config_error(tmp_path: Path) -> None:
    folder = tmp_path / "seeker.yaml"
    folder.mkdir()  # a directory where a file is expected: read_text raises IsADirectoryError
    with pytest.raises(ConfigError, match="cannot read config"):
        SeekerConfig.load(folder)


def test_non_utf8_config_is_a_config_error(tmp_path: Path) -> None:
    path = tmp_path / "seeker.yaml"
    path.write_bytes(b"paths: \xff\xfe\n")
    with pytest.raises(ConfigError, match="not UTF-8"):
        SeekerConfig.load(path)


class TestVault:
    @pytest.fixture(autouse=True)
    def no_vault_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SEEKER_VAULT", raising=False)

    NO_VAULT = MINIMAL.replace(", vault: ~/vault", "")

    def test_folder_defaults(self, tmp_path: Path) -> None:
        layout = SeekerConfig.load(write(tmp_path)).vault()
        assert layout.root == Path("~/vault").expanduser()
        assert layout.works == layout.root / "Works"
        assert layout.cards == layout.root / "Cards"

    def test_folder_overrides(self, tmp_path: Path) -> None:
        text = MINIMAL + "vault_folders: {works: Library/Works, cards: Library/Cards}\n"
        layout = SeekerConfig.load(write(tmp_path, text)).vault()
        assert layout.works == layout.root / "Library" / "Works"
        assert layout.cards == layout.root / "Library" / "Cards"

    @pytest.mark.parametrize("folder", ["/abs/Works", "../outside"])
    def test_folders_must_stay_inside_the_vault(self, tmp_path: Path, folder: str) -> None:
        with pytest.raises(ConfigError):
            SeekerConfig.load(write(tmp_path, MINIMAL + f"vault_folders: {{works: {folder}}}\n"))

    def test_dotenv_value(self, tmp_path: Path) -> None:
        config = SeekerConfig.load(write(tmp_path, self.NO_VAULT))
        (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=x\nSEEKER_VAULT=~/notes\n")
        assert config.vault().root == Path.home() / "notes"

    def test_dotenv_beats_paths_vault(self, tmp_path: Path) -> None:
        config = SeekerConfig.load(write(tmp_path))
        (tmp_path / ".env").write_text(f"SEEKER_VAULT={tmp_path / 'from-env'}\n")
        assert config.vault().root == tmp_path / "from-env"

    def test_environment_beats_dotenv_and_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        config = SeekerConfig.load(write(tmp_path))
        (tmp_path / ".env").write_text("SEEKER_VAULT=/from/dotenv\n")
        monkeypatch.setenv("SEEKER_VAULT", str(tmp_path / "from-environment"))
        assert config.vault().root == tmp_path / "from-environment"

    def test_relative_value_resolves_against_config_folder(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SEEKER_VAULT", "vault")
        assert SeekerConfig.load(write(tmp_path, self.NO_VAULT)).vault().root == tmp_path / "vault"

    def test_not_configured(self, tmp_path: Path) -> None:
        config = SeekerConfig.load(write(tmp_path, self.NO_VAULT))
        with pytest.raises(VaultNotConfigured, match="SEEKER_VAULT") as caught:
            config.vault()
        assert ".env" in str(caught.value)

    def test_repo_config_has_no_vault_committed(self) -> None:
        config = SeekerConfig.load(ROOT / "seeker.yaml")
        assert config.paths.vault is None
        assert str(config.vault_folders.works) == "Works"
