"""Builders for throwaway Obsidian vaults used by the works tests."""

from functools import lru_cache
from pathlib import Path

from seeker.decks.loader import DeckDirectory
from seeker.ontology import DeckSet

ROOT = Path(__file__).resolve().parent.parent


@lru_cache(maxsize=1)
def repo_decks() -> DeckSet:
    return DeckDirectory(ROOT / "decks").load()


def work_note(
    works: Path,
    name: str,
    *,
    cards: str = "[]",
    extra: str = "",
    body: str = "",
    title: str | None = None,
) -> Path:
    works.mkdir(parents=True, exist_ok=True)
    path = works / f"{name}.md"
    path.write_text(
        "---\n"
        "type: work\n"
        f"title: {title or name!r}\n"
        "kind: recording\n"
        f"cards: {cards}\n"
        "captured_by: gabe\n"
        "captured_on: 2026-11-05\n"
        f"{extra}"
        "---\n"
        f"{body}",
        encoding="utf-8",
    )
    return path
