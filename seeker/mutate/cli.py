"""``seeker-mutate``: breed the next round of ideas from a finished debate run's survivors."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from seeker.config import ConfigError, SeekerConfig
from seeker.debate.cli import EXIT_BUDGET
from seeker.decks import DeckValidationFailed
from seeker.generate.generator import GenerationError
from seeker.generate.prompt import SystemPrompt
from seeker.generate.record import GenerationFile
from seeker.generate.role_file import LoadedRole, RoleFileError
from seeker.models import AnthropicModel, LanguageModel
from seeker.mutate.job import MutationJob
from seeker.mutate.plan import MutationError, MutationPlan, PlannedIdea
from seeker.mutate.prompt import MutationPrompt
from seeker.ontology import DeckSet, Generation, MutationKind, Reading, StopReason



class MutateCommand:
    """The ``seeker-mutate`` command line. ``model`` can be injected (tests);
    otherwise the real Anthropic model is built, which needs an API key."""

    def __init__(self, model: LanguageModel | None = None) -> None:
        self.model = model
        self.parser = argparse.ArgumentParser(
            prog="seeker-mutate",
            description=(
                "Breed the next round from a finished debate run: reworkings and card swaps of each survivor, "
                "then the survivors themselves. Debate the result with seeker-debate. "
                "Suggested --out: generations/<date>-round-<n>-<reading>.yaml"
            ),
        )
        self.parser.add_argument("run", type=Path, help="A finished DebateRun YAML file.")
        target = self.parser.add_mutually_exclusive_group()
        target.add_argument("--out", type=Path, help="Write (or resume) the mutated Generation at this path.")
        target.add_argument("--scratch", action="store_true", help="Write under <generations>/scratch/ (git-ignored).")
        self.parser.add_argument("--seed", type=int, help="Mutation seed (default: the parent run's tournament seed).")
        self.parser.add_argument(
            "--budget", type=float, help="Stop once estimated spend reaches this many US dollars (default: budget_usd)."
        )
        self.parser.add_argument("--dry-run", action="store_true", help="Print every planned draw and prompt; make no API call.")
        self.parser.add_argument("--config", type=Path, help="seeker.yaml to use (default: found by walking up).")

    def run(self, argv: Sequence[str] | None = None) -> int:
        args = self.parser.parse_args(argv)
        if not args.dry_run and args.out is None and not args.scratch:
            self.parser.error("give --out PATH or --scratch, so the round can be saved and resumed")
        try:
            config = SeekerConfig.load(args.config)
            job = MutationJob(config, args.run, seed=args.seed)
            plan = job.plan
            if args.dry_run:
                return self._dry_run(plan, job.role, job.deck_set, job.reading)
            model = self.model or AnthropicModel(api_key=config.api_key())
            budget = args.budget if args.budget is not None else config.budget_usd
            sink = GenerationFile(args.out or self._scratch(config, job.parent.label, plan))
            if sink.exists():
                print(f"resuming {sink.path}: {len(sink.read().ideas)} of {plan.batch.size} positions have ideas")
            result = job.run(model, sink, budget)
        except DeckValidationFailed as failed:
            for problem in failed.report.errors:
                print(problem, file=sys.stderr)
            return 1
        except (ConfigError, RoleFileError, GenerationError, MutationError, OSError) as error:
            print(error, file=sys.stderr)
            return 1
        self._print(plan, result)
        print(f"wrote {sink.path}")
        if result.stop_reason is StopReason.BUDGET:
            print(f"stopped at the ${budget:.2f} budget; rerun with a higher --budget to continue")
            return EXIT_BUDGET
        return 0

    @staticmethod
    def _scratch(config: SeekerConfig, parent_label: str, plan: MutationPlan) -> Path:
        stem = Path(parent_label).stem
        return config.paths.generations / "scratch" / f"{date.today().isoformat()}-round-{plan.origin.round}-from-{stem}.yaml"

    @staticmethod
    def _dry_run(plan: MutationPlan, role: LoadedRole, deck_set: DeckSet, reading: Reading) -> int:
        print(f"=== system ({role.role.model}, {reading.value}, role {role.digest[:12]}) ===")
        print(SystemPrompt(role.role, reading).render())
        for entry in plan.children:
            taken = ("(the earlier reworking's statement, once written)",) if plan.siblings_before(entry) else ()
            print(f"\n=== child {entry.position}: {MutateCommand._kind(entry)} ===")
            print(MutationPrompt(entry, deck_set, taken).render())
        for entry in plan.carried:
            print(f"\n=== {entry.position}: carried #{entry.parent.position}, no call: {entry.parent.debate.final_statement}")
        print(
            f"\ndry run: round {plan.origin.round}, {len(plan.children)} children from {len(plan.carried)} survivors, "
            f"{len(plan.carried)} carried, seed {plan.origin.mutation_seed}; no API calls"
        )
        return 0

    @staticmethod
    def _kind(entry: PlannedIdea) -> str:
        lineage = entry.lineage
        if lineage.mutation_kind is MutationKind.CARD_SWAP:
            return f"card swap of #{lineage.parent_position} ({lineage.swapped_axis}: {lineage.replaced_card} -> {entry.new_card})"
        if lineage.mutation_kind is MutationKind.REWORKING:
            return f"reworking {entry.attempt} of #{lineage.parent_position}"
        return f"carried #{lineage.parent_position}"

    @staticmethod
    def _print(plan: MutationPlan, result: Generation) -> None:
        failures = {f.position: f for f in result.failures}
        for entry in plan.entries:
            idea = result.idea_at(entry.position)
            if idea is not None:
                text = idea.statement
            elif entry.position in failures:
                text = f"FAILED  {failures[entry.position].reason}"
            else:
                text = "not yet made"
            print(f"{entry.position:>2}  {MutateCommand._kind(entry)}  {text}")
        usage = result.usage
        print(
            f"round {plan.origin.round} · {len(result.ideas)} ideas · {len(result.failures)} failures · "
            f"{usage.input_tokens:,} in / {usage.output_tokens:,} out tokens · "
            f"est. ${result.estimated_cost_usd:.2f} ({result.model}, {result.reading.value})"
        )


def main(argv: Sequence[str] | None = None) -> int:
    return MutateCommand().run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
