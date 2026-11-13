"""``seeker-debate``: debate a recorded generation's ideas, rank them, and report the survivors."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from seeker.config import ConfigError, SeekerConfig, VaultNotConfigured
from seeker.debate.debater import Debater, DebateOutcome
from seeker.debate.meter import CostMeter
from seeker.debate.prompts import CriticPrompt, ProsecutorPrompt
from seeker.debate.record import DebateFile, DebateResumeMismatch
from seeker.debate.report import SurvivorReport
from seeker.debate.roles import DebateRoleError, DebateRoles
from seeker.debate.runner import DebateRunner, GenerationInput
from seeker.debate.schedule import Schedule
from seeker.debate.tournament import TournamentRunner
from seeker.decks import DeckDirectory, DeckValidationFailed
from seeker.generate.prompt import SystemPrompt
from seeker.generate.provenance import GitRepo
from seeker.generate.role_file import RoleFileError
from seeker.models import AnthropicModel, LanguageModel
from seeker.ontology import DebateRun, DeckSet, RoleName, ScoreAxis, StopReason
from seeker.works.catalog import WorkNotes, WorksInvalid
from seeker.works.check import DrawPriorArt

EXIT_BUDGET = 3
COMMANDS = ("run", "report")
CALLS_PER_DEBATE = 4


class DebateCommand:
    """The ``seeker-debate`` command line. ``model`` can be injected (tests);
    otherwise the real Anthropic model is built, which needs an API key."""

    def __init__(self, model: LanguageModel | None = None) -> None:
        self.model = model
        self.parser = argparse.ArgumentParser(
            prog="seeker-debate",
            description="Debate a generation's ideas, rank them blind, and report the survivors.",
        )
        commands = self.parser.add_subparsers(dest="command", required=True)
        run = commands.add_parser("run", help="Debate and rank a recorded generation (the default command).")
        run.add_argument("generation", type=Path, help="A recorded Generation YAML file.")
        target = run.add_mutually_exclusive_group()
        target.add_argument("--out", type=Path, help="Write (or resume) the DebateRun record at this path.")
        target.add_argument("--scratch", action="store_true", help="Write under <debates>/scratch/ (git-ignored).")
        run.add_argument("--seed", type=int, help="Tournament seed (default: the generation's batch seed).")
        run.add_argument("--budget", type=float, help="Stop once estimated spend reaches this many US dollars.")
        run.add_argument("--no-tournament", action="store_true", help="Debate every idea, then stop before ranking.")
        run.add_argument("--dry-run", action="store_true", help="Print the prompts and planned calls; make no API call.")
        run.add_argument("--config", type=Path, help="seeker.yaml to use (default: found by walking up).")
        report = commands.add_parser("report", help="Render the survivors report for a finished run.")
        report.add_argument("run", type=Path, help="A DebateRun YAML file.")
        report.add_argument("--config", type=Path, help="seeker.yaml to use (default: found by walking up).")

    def run(self, argv: Sequence[str] | None = None) -> int:
        given = list(sys.argv[1:] if argv is None else argv)
        if given and given[0] not in COMMANDS and given[0] not in ("-h", "--help"):
            given = ["run", *given]
        args = self.parser.parse_args(given)
        try:
            if args.command == "report":
                return self._report(args)
            return self._run(args)
        except DeckValidationFailed as failed:
            for problem in failed.report.errors:
                print(problem, file=sys.stderr)
            return 1
        except WorksInvalid as invalid:
            print(invalid, file=sys.stderr)
            return 1
        except (ConfigError, RoleFileError, DebateRoleError, DebateResumeMismatch, OSError) as error:
            print(error, file=sys.stderr)
            return 1

    # -- run -------------------------------------------------------------------------

    def _run(self, args: argparse.Namespace) -> int:
        config = SeekerConfig.load(args.config)
        deck_set = DeckDirectory(config.paths.decks).load()
        source = GenerationInput.read(args.generation, config.root)
        roles = DebateRoles.load(config.paths.prompts, config.prices)
        seed = args.seed if args.seed is not None else source.generation.draw_batch.seed
        budget = args.budget if args.budget is not None else config.budget_usd
        if args.dry_run:
            return self._dry_run(config, deck_set, source, roles, seed)
        if args.out is None and not args.scratch:
            self.parser.error("give --out PATH or --scratch, so the run can be saved and resumed")
        works = WorkNotes(folder=config.vault().works, deck_set=deck_set)
        model = self.model or AnthropicModel(api_key=config.api_key())
        meter = CostMeter(config.prices, budget)
        reading = source.generation.reading
        debater = Debater(roles, model, deck_set, works, reading, date.today())
        runner = DebateRunner(roles, debater, meter)
        sink = DebateFile(args.out or config.paths.debates / "scratch" / f"{date.today().isoformat()}-{args.generation.stem}.yaml")
        record = sink.read() if sink.exists() else None
        if record is not None:
            print(f"resuming {sink.path}: {len(record.debates)} debates recorded")
        progress = runner.debate_all(source, seed, sink=sink, record=record, git_commit=GitRepo(config.root).commit())
        for outcome in progress.debated:
            print(self._debate_line(outcome))
        current = progress.run
        if current.stop_reason is not StopReason.BUDGET:
            if args.no_tournament:
                current = DebateRun.model_validate({**current.model_dump(), "stop_reason": StopReason.NO_TOURNAMENT})
                sink.save(current)
            else:
                tournament = TournamentRunner(
                    roles.role(RoleName.JUDGE), model, reading, meter, config.tournament.max_comparisons
                )
                current = tournament.play(current, source.generation, sink)
        self._summary(current)
        print(f"wrote {sink.path}")
        return EXIT_BUDGET if current.stop_reason is StopReason.BUDGET else 0

    def _dry_run(
        self, config: SeekerConfig, deck_set: DeckSet, source: GenerationInput, roles: DebateRoles, seed: int
    ) -> int:
        reading = source.generation.reading
        try:
            works = WorkNotes(folder=config.vault().works, deck_set=deck_set)
        except VaultNotConfigured:
            print("note: no vault configured; showing the prosecutor an empty catalog")
            works = WorkNotes(folder=config.root / ".no-vault", deck_set=deck_set)
        catalog = works.catalog()
        for name in DebateRoles.ALL:
            loaded = roles.role(name)
            print(f"=== system: {name.value} ({loaded.role.model}, {reading.value}, role {loaded.digest[:12]}) ===")
            print(SystemPrompt(loaded.role, reading).render())
        draws = {draw.position: draw for draw in source.generation.draw_batch.draws}
        for idea in source.generation.ideas:
            draw = draws[idea.position]
            print(f"\n=== idea {idea.position}: prosecutor ===")
            print(ProsecutorPrompt(idea, draw, deck_set, DrawPriorArt.of(catalog, draw)).render())
            print(f"\n=== idea {idea.position}: skeptic and taste critic ===")
            print(CriticPrompt(idea, draw, deck_set).render())
        debates = len(source.generation.ideas)
        positions = tuple(idea.position for idea in source.generation.ideas)
        comparisons = len(Schedule.build(positions, seed, config.tournament.max_comparisons))
        searches = debates * roles.role(RoleName.PROSECUTOR).role.max_searches
        print(
            f"\ndry run: {debates} debates, {debates * CALLS_PER_DEBATE} debate calls (up to {searches} searches), "
            f"up to {comparisons} comparisons if none is withdrawn; no API calls"
        )
        return 0

    @staticmethod
    def _debate_line(outcome: DebateOutcome) -> str:
        if outcome.debate is None:
            failed = ", ".join(f"{f.role_name.value}: {f.failure_reason}" for f in outcome.failures)
            position = outcome.failures[0].position if outcome.failures else "?"
            return f"{position:>3}  NO DEBATE  ({failed})"
        debate = outcome.debate
        severities = " ".join(f"{c.role_name.value}={c.severity.value}" for c in debate.critiques)
        flags = " (short a critique)" if debate.short_a_critique else ""
        return f"{debate.position:>3}  {debate.defense.outcome.value:<9}  {severities}{flags}"

    @staticmethod
    def _summary(run: DebateRun) -> None:
        usage = run.usage
        withdrawn = sum(1 for d in run.debates if not d.competes)
        print(
            f"{len(run.debates)} debates · {withdrawn} withdrawn · {len(run.debate_failures)} role failures · "
            f"{usage.input_tokens:,} in / {usage.output_tokens:,} out tokens · {usage.web_search_requests} searches · "
            f"est. ${run.estimated_cost_usd:.2f} of ${run.budget_usd:.2f}"
        )
        if run.stop_reason is StopReason.BUDGET:
            print("stopped at the budget; rerun with a higher --budget to continue")
        if run.tournament is not None and run.tournament.survivors:
            for rank, position in enumerate(run.tournament.survivors, start=1):
                ratings = " ".join(
                    f"{axis.value}={run.tournament.rating_of(position, axis).rating:.0f}" for axis in ScoreAxis
                )
                debate = run.debate_at(position)
                print(f"survivor {rank}: #{position}  {ratings}  {debate.final_statement}")

    # -- report ----------------------------------------------------------------------

    def _report(self, args: argparse.Namespace) -> int:
        config = SeekerConfig.load(args.config)
        deck_set = DeckDirectory(config.paths.decks).load()
        run = DebateFile(args.run).read()
        source = GenerationInput.read(config.root / run.generation_path, config.root)
        if source.digest != run.generation_digest:
            print(f"{run.generation_path} has changed since the run; the report may not match", file=sys.stderr)
        path = SurvivorReport(run, source.generation, deck_set, config.prices).write(config.paths.reports, args.run.stem)
        print(f"wrote {path}")
        return 0


def main(argv: Sequence[str] | None = None) -> int:
    return DebateCommand().run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
