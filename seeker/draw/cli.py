"""``seeker-draw``: draw a balanced, reproducible batch of card triples."""

from __future__ import annotations

import argparse
import secrets
import sys
from collections.abc import Sequence
from pathlib import Path

import yaml

from seeker.decks import DeckDirectory
from seeker.draw.drawer import BatchDrawer
from seeker.draw.errors import DrawError
from seeker.ontology import DeckSet, DrawBatch

SCRATCH_DIR = Path("batches") / "scratch"
UNSEEDED_RANGE = 2**31
RECORD_HEADER = (
    "# DrawBatch record (schema/seeker.yaml). The seed and deck-set digest pin this\n"
    "# batch exactly: redrawing with the same seed and size from decks with the same\n"
    "# digest reproduces it card for card.\n"
)


class DrawCommand:
    """The ``seeker-draw`` command line."""

    def __init__(self) -> None:
        self.parser = argparse.ArgumentParser(
            prog="seeker-draw", description="Draw card triples from Seeker's decks."
        )
        commands = self.parser.add_subparsers(dest="command", required=True)
        batch = commands.add_parser("batch", help="Draw a balanced batch of triples.")
        batch.add_argument("--seed", type=int, help="Seed (default: chosen at random and printed).")
        batch.add_argument("--size", type=int, default=12, help="Number of draws (default: 12).")
        batch.add_argument("--dir", type=Path, default=Path("decks"), help="Deck directory (default: decks).")
        target = batch.add_mutually_exclusive_group()
        target.add_argument("--out", type=Path, help="Write the batch record (YAML) to this path.")
        target.add_argument(
            "--scratch",
            action="store_true",
            help=f"Write the record to {SCRATCH_DIR}/<seed>.yaml (gitignored).",
        )

    def run(self, argv: Sequence[str] | None = None) -> int:
        args = self.parser.parse_args(argv)
        if args.seed is not None and args.seed < 0:
            self.parser.error("--seed must be non-negative")
        return self.batch(args.dir, args.seed, args.size, args.out, args.scratch)

    def batch(self, directory: Path, seed: int | None, size: int, out: Path | None, scratch: bool) -> int:
        report = DeckDirectory(directory).validate()
        if not report.ok or report.deck_set is None:
            for error in report.errors:
                print(error, file=sys.stderr)
            print(f"decks in {directory} are invalid; run `seeker-decks validate`", file=sys.stderr)
            return 1
        seed = secrets.randbelow(UNSEEDED_RANGE) if seed is None else seed
        try:
            batch = BatchDrawer(report.deck_set).draw(seed, size)
        except DrawError as error:
            print(error, file=sys.stderr)
            return 1

        self.print_batch(report.deck_set, batch)
        target = SCRATCH_DIR / f"{seed}.yaml" if scratch else out
        if target is not None:
            self.write(batch, target)
            print(f"wrote {target}")
        return 0

    @staticmethod
    def print_batch(deck_set: DeckSet, batch: DrawBatch) -> None:
        width = len(str(batch.size))
        for draw in batch.draws:
            cards = " | ".join(
                f"{axis}: {deck_set.card(card_id).name}" for axis, card_id in zip(draw.axes, draw.drawn_cards)
            )
            print(f"{draw.position:>{width}}  {draw.home_field.value:<11}  {cards}")
        print(f"seed {batch.seed}  decks {batch.deck_set_digest.short}  {batch.size} draws")

    @staticmethod
    def write(batch: DrawBatch, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        body = yaml.safe_dump(batch.model_dump(mode="json"), sort_keys=False, allow_unicode=True)
        target.write_text(RECORD_HEADER + body, encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    return DrawCommand().run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
