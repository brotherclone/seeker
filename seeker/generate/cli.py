"""``seeker-generate``: turn a draw batch into ideas with the generator role."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

import yaml

from seeker.config import ConfigError, SeekerConfig
from seeker.decks import DeckDirectory, DeckValidationFailed
from seeker.draw import BatchDrawer, DrawError
from seeker.generate.generator import GenerationError, IdeaGenerator
from seeker.generate.prompt import DrawPrompt, SystemPrompt
from seeker.generate.provenance import GitRepo
from seeker.generate.record import GenerationFile
from seeker.generate.role_file import LoadedRole, RoleFileError
from seeker.models import AnthropicModel, LanguageModel
from seeker.ontology import DeckSet, DrawBatch, Generation, Reading

ROLE_FILE = "generator.yaml"


class GenerateCommand:
    """The ``seeker-generate`` command line. ``model`` can be injected (tests);
    otherwise the real Anthropic model is built, which needs an API key."""

    def __init__(self, model: LanguageModel | None = None) -> None:
        self.model = model
        self.parser = argparse.ArgumentParser(
            prog="seeker-generate", description="Generate one idea per draw with the generator role."
        )
        commands = self.parser.add_subparsers(dest="command", required=True)
        run = commands.add_parser("run", help="Generate ideas for a batch.")
        source = run.add_mutually_exclusive_group(required=True)
        source.add_argument("--batch", type=Path, help="A recorded DrawBatch YAML file.")
        source.add_argument("--seed", type=int, help="Draw a fresh batch with this seed.")
        run.add_argument("--size", type=int, default=12, help="Batch size with --seed (default: 12).")
        run.add_argument(
            "--reading",
            default=Reading.LITERAL.value,
            help=f"How freely to read the cards: {', '.join(r.value for r in Reading)} (default: literal).",
        )
        run.add_argument("--role", type=Path, help=f"Role file (default: <prompts>/{ROLE_FILE}).")
        run.add_argument("--config", type=Path, help="seeker.yaml to use (default: found by walking up).")
        target = run.add_mutually_exclusive_group()
        target.add_argument("--out", type=Path, help="Write (or resume) the Generation record at this path.")
        target.add_argument("--label", help="Write to <generations>/<date>-<label>.yaml (committed).")
        target.add_argument("--scratch", action="store_true", help="Write under <generations>/scratch/ (git-ignored).")
        run.add_argument("--dry-run", action="store_true", help="Print every prompt; make no API call.")

    def run(self, argv: Sequence[str] | None = None) -> int:
        args = self.parser.parse_args(argv)
        try:
            reading = Reading(args.reading)
        except ValueError:
            self.parser.error(f"--reading must be one of {', '.join(r.value for r in Reading)}; got {args.reading!r}")
        try:
            config = SeekerConfig.load(args.config)
            deck_set = DeckDirectory(config.paths.decks).load()
            batch = self._batch(args, deck_set)
            role = LoadedRole.load(args.role or config.paths.prompts / ROLE_FILE)
            if args.dry_run:
                return self._dry_run(role, deck_set, batch, reading)
            model = self.model or AnthropicModel(api_key=config.api_key())
            generator = IdeaGenerator(role, model, deck_set, config.prices)
            sink = self._sink(args, config, batch, reading)
            record = sink.read() if sink is not None and sink.exists() else None
            if record is not None:
                print(f"resuming {sink.path}: {len(record.ideas)} of {batch.size} draws have ideas")
            result = generator.generate(batch, reading, record=record, sink=sink, git_commit=GitRepo(config.root).commit())
        except DeckValidationFailed as failed:
            for problem in failed.report.errors:
                print(problem, file=sys.stderr)
            return 1
        except (ConfigError, RoleFileError, GenerationError, DrawError) as error:
            print(error, file=sys.stderr)
            return 1
        self._print(deck_set, result)
        if sink is not None:
            print(f"wrote {sink.path}")
        return 0

    # -- inputs and outputs ------------------------------------------------------

    @staticmethod
    def _batch(args: argparse.Namespace, deck_set: DeckSet) -> DrawBatch:
        drawer = BatchDrawer(deck_set)
        if args.batch is None:
            return drawer.draw(args.seed, args.size)
        recorded = DrawBatch.model_validate(yaml.safe_load(args.batch.read_text(encoding="utf-8")))
        return drawer.replay(recorded)

    @staticmethod
    def _sink(
        args: argparse.Namespace, config: SeekerConfig, batch: DrawBatch, reading: Reading
    ) -> GenerationFile | None:
        today = date.today().isoformat()
        if args.out is not None:
            return GenerationFile(args.out)
        if args.label:
            return GenerationFile(config.paths.generations / f"{today}-{args.label}.yaml")
        if args.scratch:
            return GenerationFile(config.paths.generations / "scratch" / f"{today}-{batch.seed}-{reading.value}.yaml")
        return None

    @staticmethod
    def _dry_run(role: LoadedRole, deck_set: DeckSet, batch: DrawBatch, reading: Reading) -> int:
        print(f"=== system ({role.role.model}, {reading.value}, role {role.digest.short}) ===")
        print(SystemPrompt(role.role, reading).render())
        for draw in batch.draws:
            print(f"\n=== draw {draw.position} ===")
            print(DrawPrompt(draw, deck_set).render())
        print(f"\ndry run: {batch.size} prompts, no API calls")
        return 0

    @staticmethod
    def _print(deck_set: DeckSet, result: Generation) -> None:
        draws = result.draw_batch.draws
        rows = sorted(
            [(i.position, f"[{draws[i.position - 1].home_field.value}]  {i.statement}") for i in result.ideas]
            + [(f.position, f"FAILED  {f.reason}") for f in result.failures]
        )
        width = len(str(result.draw_batch.size))
        for position, text in rows:
            print(f"{position:>{width}}  {text}")
        usage = result.usage
        print(
            f"{len(result.ideas)} ideas · {len(result.failures)} failures · "
            f"{usage.input_tokens:,} in / {usage.output_tokens:,} out / {usage.cache_read_tokens:,} cache-read tokens · "
            f"est. ${result.estimated_cost_usd:.2f} ({result.model}, {result.reading.value})"
        )


def main(argv: Sequence[str] | None = None) -> int:
    return GenerateCommand().run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
