"""``seeker-schedule``: run, inspect, approve and install the scheduled round."""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

import yaml

from seeker.config import ConfigError, SeekerConfig
from seeker.debate.cli import EXIT_BUDGET
from seeker.models import LanguageModel
from seeker.ontology import ReviewSignOff, ScheduleOutcome
from seeker.schedule.cadence import Cadence
from seeker.schedule.launchd import Launchctl, LaunchAgent
from seeker.schedule.lineage import LineageError, LineageRecords
from seeker.schedule.log import RunLog
from seeker.schedule.trigger import Scheduler

EXIT_STATUS = {
    ScheduleOutcome.ADVANCED: 0,
    ScheduleOutcome.TOO_SOON: 0,
    ScheduleOutcome.AWAITING_REVIEW: 0,
    ScheduleOutcome.LOCKED: 0,
    ScheduleOutcome.BUDGET: EXIT_BUDGET,
    ScheduleOutcome.FAILED: 1,
}
OUTPUT_FOLDERS = ("generations", "debates", "reports", "reviews")


class NotApprovable(ConfigError):
    """Only the current lineage head, finished, can be signed off."""


class ScheduleCommand:
    """The ``seeker-schedule`` command line. ``model``, ``launchctl`` and ``agents_dir`` can be
    injected (tests); otherwise the real ones are used."""

    def __init__(
        self,
        model: LanguageModel | None = None,
        launchctl: Launchctl | None = None,
        agents_dir: Path | None = None,
        uv: Path | None = None,
    ) -> None:
        self.model = model
        self.launchctl = launchctl
        self.agents_dir = agents_dir
        self.uv = uv
        self.parser = argparse.ArgumentParser(
            prog="seeker-schedule",
            description=(
                "Advance the idea lineage one round at a time: launchd fires `run` daily, which mutates, "
                "debates and reports when the cadence allows and no review is pending."
            ),
        )
        self.parser.add_argument("--config", type=Path, help="seeker.yaml to use (default: found by walking up).")
        commands = self.parser.add_subparsers(dest="command", required=True)
        commands.add_parser("run", help="One trigger: advance a round if due, and record what happened.")
        commands.add_parser("status", help="Where the lineage stands; makes no API call.")
        approve = commands.add_parser("approve", help="Sign off the lineage head at a review point.")
        approve.add_argument("run", type=Path, help="The head DebateRun file.")
        approve.add_argument("--note", help="What to remember about the review.")
        commands.add_parser("install", help="Write and load the LaunchAgent (daily at schedule.hour).")
        commands.add_parser("uninstall", help="Unload and remove the LaunchAgent.")

    def run(self, argv: Sequence[str] | None = None) -> int:
        args = self.parser.parse_args(argv)
        try:
            config = SeekerConfig.load(args.config)
            handler = {
                "run": self._run,
                "status": self._status,
                "approve": self._approve,
                "install": self._install,
                "uninstall": self._uninstall,
            }[args.command]
            return handler(config, args)
        except (ConfigError, LineageError, OSError) as error:
            print(error, file=sys.stderr)
            return 1

    def agent(self, config: SeekerConfig) -> LaunchAgent:
        return LaunchAgent(config, launchctl=self.launchctl, agents_dir=self.agents_dir, uv=self.uv)

    # -- run -------------------------------------------------------------------------

    def _run(self, config: SeekerConfig, args: argparse.Namespace) -> int:
        record = Scheduler(config, self.model).trigger()
        head = f" from {record.head_run_path} (round {record.head_round})" if record.head_run_path else ""
        print(
            f"{record.started_at:%Y-%m-%d %H:%M} {record.schedule_outcome.value}{head}: "
            f"est. ${record.estimated_cost_usd:.2f} of ${record.budget_usd:.2f}"
        )
        for path in record.written_paths:
            print(f"wrote {path}")
        if record.failure_message:
            print(record.failure_message, file=sys.stderr)
        return EXIT_STATUS[record.schedule_outcome]

    # -- status ----------------------------------------------------------------------

    def _status(self, config: SeekerConfig, args: argparse.Namespace) -> int:
        log = RunLog(config.paths.runs)
        try:
            state = LineageRecords(config).state()
        except LineageError as error:
            print(f"lineage: {error}")
            state = None
        if state is not None:
            head = state.head
            print(f"head: {head.label} (round {head.round}, {head.reading.value})")
            if state.in_progress is not None:
                print(f"in progress: {Path(state.in_progress).name}; the next trigger resumes it")
            elif state.awaiting_review:
                print(f"gate: awaiting review at round {head.round}; approve with:")
                print(f"  uv run seeker-schedule approve {head.label}")
            elif state.at_review_point:
                print(f"gate: round {head.round} signed off")
            else:
                every = config.schedule.review_every
                print(f"gate: open; next review at round {head.round + every - head.round % every}")
        last = log.last()
        if last is None:
            print("last trigger: none yet")
        else:
            print(
                f"last trigger: {last.started_at:%Y-%m-%d %H:%M} {last.schedule_outcome.value}, "
                f"est. ${last.estimated_cost_usd:.2f} of ${last.budget_usd:.2f}"
            )
            if last.failure_message:
                print(f"  {last.failure_message}")
        advanced = log.last_advanced()
        due_at = Cadence(days=config.schedule.cadence_days).due_at(advanced.ended_at if advanced else None)
        hour = config.schedule.hour
        when = f"from {due_at:%Y-%m-%d %H:%M}" if due_at else "now"
        if state is not None and state.in_progress is None and state.awaiting_review:
            when = f"after sign-off (cadence: {when})"
        print(f"next round: due {when}; triggers fire daily at {hour:02d}:00, every {config.schedule.cadence_days} days")
        print(f"launch agent: {'loaded' if self.agent(config).loaded() else 'not loaded'}")
        pending = self._uncommitted(config)
        if pending:
            print(f"uncommitted outputs ({len(pending)}):")
            for line in pending:
                print(f"  {line}")
        return 0

    @staticmethod
    def _uncommitted(config: SeekerConfig) -> tuple[str, ...]:
        try:
            done = subprocess.run(
                ["git", "status", "--porcelain", "--", *OUTPUT_FOLDERS],
                cwd=config.root, capture_output=True, text=True, check=False,
            )
        except OSError:
            return ()
        return tuple(line for line in done.stdout.splitlines() if line.strip()) if done.returncode == 0 else ()

    # -- approve ---------------------------------------------------------------------

    def _approve(self, config: SeekerConfig, args: argparse.Namespace) -> int:
        records = LineageRecords(config)
        path = args.run if args.run.is_absolute() else (Path.cwd() / args.run)
        if not path.is_file():
            raise NotApprovable(f"{args.run}: no such debate run")
        if not records.is_finished(records.run_at(path)):
            raise NotApprovable(f"{args.run}: the run is not finished, so it cannot be signed off")
        head = records.head()
        if path.resolve() != head.path.resolve():
            raise NotApprovable(f"{args.run} is not the lineage head; the head is {head.label}")
        signed = ReviewSignOff(
            reviewed_run_path=head.label,
            reviewed_run_digest=hashlib.sha256(path.read_bytes()).hexdigest(),
            signed_at=datetime.now().astimezone(),
            review_note=args.note,
        )
        config.paths.reviews.mkdir(parents=True, exist_ok=True)
        out = config.paths.reviews / f"{head.path.stem}.yaml"
        out.write_text(yaml.safe_dump(signed.model_dump(mode="json", exclude_none=True), sort_keys=False))
        print(f"signed off {head.label} (round {head.round}); wrote {records.label(out)}")
        return 0

    # -- launch agent ----------------------------------------------------------------

    def _install(self, config: SeekerConfig, args: argparse.Namespace) -> int:
        path = self.agent(config).install()
        print(f"installed {path}; fires daily at {config.schedule.hour:02d}:00, logs in {config.paths.logs}")
        return 0

    def _uninstall(self, config: SeekerConfig, args: argparse.Namespace) -> int:
        removed = self.agent(config).uninstall()
        print("removed the launch agent" if removed else "no launch agent was installed")
        return 0


def main(argv: Sequence[str] | None = None) -> int:
    return ScheduleCommand().run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
