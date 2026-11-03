"""Reading deck YAML strictly: safe loading that refuses duplicate keys."""

from __future__ import annotations

from itertools import groupby
from pathlib import Path

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode


class StrictSafeLoader(yaml.SafeLoader):
    """A SafeLoader that raises on duplicate mapping keys instead of letting
    the last one silently win."""

    def construct_mapping(self, node: MappingNode, deep: bool = False) -> object:
        seen: set[object] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            try:
                duplicate = key in seen
            except TypeError:
                raise ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    f"found unhashable key {key!r}; deck keys must be plain strings",
                    key_node.start_mark,
                ) from None
            if duplicate:
                raise ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    f"found duplicate key {key!r}",
                    key_node.start_mark,
                )
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


class DeckSource:
    """One deck file on disk, read but not yet validated."""

    SUFFIXES = (".yaml", ".yml")

    def __init__(self, path: Path) -> None:
        self.path = path

    @property
    def axis(self) -> str:
        """The axis this file must hold: its file name without the suffix."""
        return self.path.stem

    def read(self) -> object:
        """Parse the file; raises yaml.YAMLError on malformed or duplicate-key YAML."""
        with self.path.open(encoding="utf-8") as handle:
            return yaml.load(handle, Loader=StrictSafeLoader)  # noqa: S506 - StrictSafeLoader is safe

    @classmethod
    def patterns(cls) -> str:
        """The accepted file patterns, for messages: '*.yaml or *.yml'."""
        return " or ".join(f"*{suffix}" for suffix in cls.SUFFIXES)

    @staticmethod
    def duplicated_axes(sources: tuple[DeckSource, ...]) -> tuple[str, ...]:
        """Axes claimed by more than one file (e.g. technique.yaml and technique.yml)."""
        axes = sorted(source.axis for source in sources)
        return tuple(axis for axis, group in groupby(axes) if len(list(group)) > 1)

    @classmethod
    def in_directory(cls, directory: Path) -> tuple[DeckSource, ...]:
        """Every deck file in ``directory``, sorted by axis."""
        paths = (p for p in directory.iterdir() if p.is_file() and p.suffix in cls.SUFFIXES)
        return tuple(cls(path) for path in sorted(paths, key=lambda p: (p.stem, p.suffix)))
