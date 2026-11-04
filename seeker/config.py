"""Local configuration: where things live, what models cost, and the API key.

Everything location-dependent comes from ``seeker.yaml`` so a run can move
(local Mac today, the cloud later) by changing config, not code. The API key
is never read from ``seeker.yaml``: it comes from ``ANTHROPIC_API_KEY`` or a
git-ignored ``.env`` beside it.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import ClassVar

import yaml
from pydantic import ConfigDict, Field, SecretStr, ValidationError

from seeker.ontology import ModelId, SeekerModel, Usage

CONFIG_NAME = "seeker.yaml"
CONFIG_ENV = "SEEKER_CONFIG"
KEY_ENV = "ANTHROPIC_API_KEY"
PER_MILLION = 1_000_000
FORBIDDEN_KEYS = ("api_key", "anthropic_api_key")


class ConfigError(Exception):
    """seeker.yaml is missing, malformed, or asks for something it must not hold."""


class MissingApiKey(ConfigError):
    def __init__(self, env_file: Path) -> None:
        super().__init__(
            f"no API key: set {KEY_ENV} in the environment or add {KEY_ENV}=... to {env_file} (git-ignored)"
        )


class PathsConfig(SeekerModel):
    """Where Seeker's files live, resolved to absolute paths."""

    model_config = ConfigDict(title="PathsConfig")

    decks: Path = Field(description="Deck directory.")
    batches: Path = Field(description="Committed draw-batch records.")
    generations: Path = Field(description="Committed generation records.")
    prompts: Path = Field(description="Role files.")
    vault: Path | None = Field(default=None, description="Obsidian vault root, when used.")

    def resolved(self, root: Path) -> PathsConfig:
        def place(path: Path) -> Path:
            expanded = path.expanduser()
            return expanded if expanded.is_absolute() else (root / expanded).resolve()

        return PathsConfig(
            decks=place(self.decks),
            batches=place(self.batches),
            generations=place(self.generations),
            prompts=place(self.prompts),
            vault=place(self.vault) if self.vault is not None else None,
        )


class ModelPrice(SeekerModel):
    """List prices for one model, in US dollars per million tokens."""

    model_config = ConfigDict(title="ModelPrice")

    model: ModelId = Field(description="The model these prices apply to.")
    input: float = Field(ge=0, description="Uncached input tokens.")
    output: float = Field(ge=0, description="Output tokens.")
    cache_read: float = Field(ge=0, description="Input tokens read from the prompt cache.")
    cache_write: float = Field(ge=0, description="Input tokens written to the prompt cache.")

    def cost(self, usage: Usage) -> float:
        """Estimated US dollars for ``usage`` at these prices."""
        return (
            usage.input_tokens * self.input
            + usage.output_tokens * self.output
            + usage.cache_read_tokens * self.cache_read
            + usage.cache_write_tokens * self.cache_write
        ) / PER_MILLION


class PriceTable(SeekerModel):
    """Model prices as data, dated so stale prices are visible."""

    model_config = ConfigDict(title="PriceTable")

    as_of: date = Field(description="When these prices were last checked.")
    models: tuple[ModelPrice, ...] = Field(min_length=1, description="One entry per priced model.")

    def price_for(self, model: str) -> ModelPrice | None:
        return next((price for price in self.models if price.model == model), None)


class SeekerConfig(SeekerModel):
    """The parsed seeker.yaml, with paths resolved against the file's folder."""

    model_config = ConfigDict(title="SeekerConfig")

    SECTIONS: ClassVar[tuple[str, ...]] = ("paths", "prices")

    root: Path = Field(description="Folder holding seeker.yaml; relative paths resolve against it.")
    paths: PathsConfig
    prices: PriceTable

    @classmethod
    def find(cls, start: Path | None = None) -> Path:
        """seeker.yaml from $SEEKER_CONFIG, else the nearest one walking up from ``start``."""
        override = os.environ.get(CONFIG_ENV)
        if override:
            path = Path(override).expanduser()
            if not path.is_file():
                raise ConfigError(f"{CONFIG_ENV} points at {path}, which does not exist")
            return path.resolve()
        here = (start or Path.cwd()).resolve()
        for folder in (here, *here.parents):
            candidate = folder / CONFIG_NAME
            if candidate.is_file():
                return candidate
        raise ConfigError(f"no {CONFIG_NAME} found in {here} or any parent folder")

    @classmethod
    def load(cls, path: Path | None = None) -> SeekerConfig:
        source = path.resolve() if path is not None else cls.find()
        try:
            raw = yaml.safe_load(source.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise ConfigError(f"{source}: invalid YAML: {' '.join(str(exc).split())}") from exc
        if not isinstance(raw, dict):
            raise ConfigError(f"{source}: expected a mapping with {', '.join(cls.SECTIONS)}")
        leaked = [key for key in raw if str(key).lower() in FORBIDDEN_KEYS]
        if leaked:
            raise ConfigError(
                f"{source}: '{leaked[0]}' does not belong in {CONFIG_NAME}; API keys go in the "
                f"{KEY_ENV} environment variable or a git-ignored .env file"
            )
        try:
            parsed = cls.model_validate({**raw, "root": source.parent})
        except ValidationError as exc:
            raise ConfigError(f"{source}: {exc}") from exc
        return parsed.model_copy(update={"paths": parsed.paths.resolved(parsed.root)})

    @property
    def env_file(self) -> Path:
        return self.root / ".env"

    def api_key(self) -> SecretStr:
        """The API key from the environment, else .env; raises MissingApiKey."""
        value = os.environ.get(KEY_ENV) or DotEnv(self.env_file).get(KEY_ENV)
        if not value:
            raise MissingApiKey(self.env_file)
        return SecretStr(value)


class DotEnv:
    """A minimal KEY=value .env reader (comments, blank lines, optional quotes, `export`)."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def get(self, key: str) -> str | None:
        if not self.path.is_file():
            return None
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, _, value = line.removeprefix("export ").partition("=")
            if name.strip() == key:
                return value.strip().strip("'\"")
        return None
