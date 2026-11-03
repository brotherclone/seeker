"""``seeker-decks``: validate the deck directory from the command line."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from seeker.decks.digest import DeckSetDigest
from seeker.decks.loader import DeckDirectory


class DecksCommand:
    """The ``seeker-decks`` command line."""

    def __init__(self) -> None:
        self.parser = argparse.ArgumentParser(
            prog="seeker-decks", description="Work with Seeker's topic-card decks."
        )
        commands = self.parser.add_subparsers(dest="command", required=True)
        validate = commands.add_parser(
            "validate", help="Validate every deck file and print per-deck and set digests."
        )
        validate.add_argument(
            "--dir", type=Path, default=Path("decks"), help="Deck directory (default: decks)."
        )

    def run(self, argv: Sequence[str] | None = None) -> int:
        args = self.parser.parse_args(argv)
        return self.validate(args.dir)

    def validate(self, directory: Path) -> int:
        report = DeckDirectory(directory).validate()
        if not report.ok or report.deck_set is None:
            for error in report.errors:
                print(error, file=sys.stderr)
            count = len(report.errors)
            print(f"{count} error{'s' if count != 1 else ''} in {directory}", file=sys.stderr)
            return 1
        digest = DeckSetDigest.of(report.deck_set)
        width = max(len(str(d.axis)) for d in digest.decks)
        for deck in digest.decks:
            print(f"{deck.axis:<{width}}  {deck.card_count:>4} cards  {deck.short}")
        print(f"{'deck set':<{width}}  {digest.card_count:>4} cards  {digest.short}")
        return 0


def main(argv: Sequence[str] | None = None) -> int:
    return DecksCommand().run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
