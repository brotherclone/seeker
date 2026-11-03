"""Builders for throwaway deck directories used across the deck tests."""

from pathlib import Path

import yaml

REQUIRED_AXES = ("technique", "medium", "historical-artifact", "constraint", "domain")


def deck_body(axis: str, *cards: dict) -> dict:
    return {
        "axis": axis,
        "name": axis.replace("-", " ").title(),
        "description": f"The {axis} axis.",
        "cards": list(cards) or [{"id": f"{axis}-card", "name": f"{axis} card"}],
    }


def write_deck(directory: Path, axis: str, body: dict | str) -> Path:
    path = directory / f"{axis}.yaml"
    path.write_text(body if isinstance(body, str) else yaml.safe_dump(body, sort_keys=False))
    return path


def valid_directory(root: Path, name: str = "decks") -> Path:
    directory = root / name
    directory.mkdir(parents=True)
    for axis in REQUIRED_AXES:
        write_deck(directory, axis, deck_body(axis))
    return directory
