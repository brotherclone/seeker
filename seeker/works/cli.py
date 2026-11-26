"""``seeker-works``: the works catalog in the Obsidian vault, from the command line."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

import yaml
from pydantic import ValidationError

from seeker.config import ConfigError, SeekerConfig, VaultLayout
from seeker.decks.digest import DeckSetDigest
from seeker.decks.loader import DeckDirectory
from seeker.decks.report import DeckValidationFailed
from seeker.ontology import DeckSet, DrawBatch
from seeker.works.cards_sync import CardNotes
from seeker.works.catalog import WorkNotes, WorksReport
from seeker.works.check import BatchCheck, DrawPriorArt
from seeker.works.matcher import CardMatcher


class WorksCommand:
    """The ``seeker-works`` command line."""

    def __init__(self) -> None:
        self.parser = argparse.ArgumentParser(
            prog="seeker-works",
            description="Works captured in the Obsidian vault: validate, sync card notes, suggest card links, check draws.",
        )
        self.parser.add_argument("--config", type=Path, help="seeker.yaml to use (default: nearest one).")
        commands = self.parser.add_subparsers(dest="command", required=True)
        commands.add_parser("validate", help="Report every problem in the works folder, or the count and digest.")
        commands.add_parser("sync-cards", help="Write or update one note per deck card in the cards folder.")
        suggest = commands.add_parser("suggest", help="Suggest card links from each work's title, summary and body.")
        suggest.add_argument("--apply", action="store_true", help="Add the suggested cards to the notes.")
        check = commands.add_parser("check", help="List the works that already combine each draw's cards.")
        check.add_argument("--batch", type=Path, required=True, help="A draw batch file.")

    def run(self, argv: Sequence[str] | None = None) -> int:
        args = self.parser.parse_args(argv)
        try:
            config = SeekerConfig.load(args.config)
            layout = config.vault()
            deck_set = DeckDirectory(config.paths.decks).load()
            if args.command == "validate":
                return self.validate(layout, deck_set)
            if args.command == "sync-cards":
                return self.sync_cards(layout, deck_set)
            if args.command == "suggest":
                return self.suggest(layout, deck_set, args.apply)
            return self.check(layout, deck_set, args.batch)
        except DeckValidationFailed as failed:
            for problem in failed.report.errors:
                print(problem, file=sys.stderr)
            return 1
        except ConfigError as error:
            print(error, file=sys.stderr)
            return 1

    @staticmethod
    def _report(layout: VaultLayout, deck_set: DeckSet) -> WorksReport:
        return WorkNotes(folder=layout.works, deck_set=deck_set).load()

    @staticmethod
    def _print_problems(report: WorksReport) -> None:
        for problem in report.problems:
            print(problem, file=sys.stderr)
        count = len(report.problems)
        print(f"{count} problem{'s' if count != 1 else ''} in {report.folder}", file=sys.stderr)

    def validate(self, layout: VaultLayout, deck_set: DeckSet) -> int:
        report = self._report(layout, deck_set)
        if report.catalog is None:
            self._print_problems(report)
            return 1
        count = len(report.catalog)
        print(f"{count} work{'s' if count != 1 else ''} in {layout.works}  catalog {report.catalog.digest.short}")
        return 0

    @staticmethod
    def sync_cards(layout: VaultLayout, deck_set: DeckSet) -> int:
        report = CardNotes.of(layout).sync(deck_set)
        for card in report.skipped:
            print(f"{report.folder / f'{card}.md'}: frontmatter is not valid YAML; left untouched", file=sys.stderr)
        print(
            f"{len(report.created)} created, {len(report.updated)} updated, "
            f"{len(report.unchanged)} unchanged in {report.folder}"
        )
        return 0

    def suggest(self, layout: VaultLayout, deck_set: DeckSet, apply: bool) -> int:
        report = self._report(layout, deck_set)
        if report.problems:
            self._print_problems(report)
            print("suggesting for the notes that validate", file=sys.stderr)
        matcher = CardMatcher.of(deck_set)
        pending = tuple(s for entry in report.notes if (s := matcher.suggest(entry)).suggestions)
        for suggestions in pending:
            print(f"{suggestions.path.relative_to(layout.works)}")
            for suggestion in suggestions.suggestions:
                print(f"  + {suggestion.card}  ({suggestion.found!r})")
        cards = sum(len(s.suggestions) for s in pending)
        if apply:
            written = sum(1 for s in pending if s.apply())
            print(f"added {cards} card link{'s' if cards != 1 else ''} to {written} note{'s' if written != 1 else ''}")
        elif pending:
            print(f"{cards} suggestion{'s' if cards != 1 else ''}; run with --apply to add them")
        else:
            print("no new card suggestions")
        return 0

    def check(self, layout: VaultLayout, deck_set: DeckSet, batch_path: Path) -> int:
        try:
            batch = DrawBatch.model_validate(yaml.safe_load(batch_path.read_text(encoding="utf-8")))
        except (OSError, yaml.YAMLError, ValidationError) as error:
            print(f"{batch_path}: not a readable draw batch ({' '.join(str(error).split())})", file=sys.stderr)
            return 1
        report = self._report(layout, deck_set)
        if report.catalog is None:
            self._print_problems(report)
            return 1
        if batch.deck_set_digest != DeckSetDigest.of(deck_set).sha256:
            print(f"note: {batch_path} was drawn from different decks than the current ones", file=sys.stderr)
        result = BatchCheck.run(report.catalog, batch)
        for entry in result.draws:
            self._print_draw(entry)
        print(
            f"{result.draws_with_prior_art} of {len(result.draws)} draws have prior art "
            f"among {result.work_count} works (catalog {result.catalog_digest.short})"
        )
        return 0

    @staticmethod
    def _print_draw(entry: DrawPriorArt) -> None:
        print(f"#{entry.draw.position:>2}  {' × '.join(entry.draw.drawn_cards)}")
        if not entry.hits:
            print("     no prior art in the vault")
        for hit in entry.hits:
            marker = "all 3" if hit.full else f"{len(hit.shared)} of {len(entry.draw.drawn_cards)}"
            print(f"     [{marker}] {hit.title} ({hit.work_id}): {', '.join(hit.shared)}")


def main(argv: Sequence[str] | None = None) -> int:
    return WorksCommand().run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
