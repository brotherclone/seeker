"""One trigger of the scheduled run, from lock to record to vault note.

Every path out of ``Scheduler.trigger`` writes a ScheduledRun, an unexpected exception
included, so a quiet failure at 2am cannot go unrecorded."""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from pathlib import Path

from seeker.config import SeekerConfig
from seeker.debate.job import ReportJob
from seeker.debate.meter import CostMeter
from seeker.debate.record import DebateFile
from seeker.generate.record import GenerationFile
from seeker.models import AnthropicModel, LanguageModel
from seeker.ontology import DebateRun, ScheduledRun, ScheduleOutcome
from seeker.schedule.cadence import Cadence
from seeker.schedule.lineage import LineageRecords, LineageState
from seeker.schedule.log import RunLog, RunLock
from seeker.schedule.note import RunNote
from seeker.schedule.round import RoundResult, RoundRunner


class Scheduler:
    """Decides whether this trigger may work, does one round if so, and records what happened.

    ``model`` can be injected (tests); otherwise the Anthropic model is built only when a round
    actually runs, so a skipped trigger needs no API key."""

    def __init__(self, config: SeekerConfig, model: LanguageModel | None = None) -> None:
        self.config = config
        self.model = model
        self.log = RunLog(config.paths.runs)
        self.cadence = Cadence(days=config.schedule.cadence_days)
        self._clock_start = time.monotonic()

    def label(self, path: Path) -> str:
        resolved = path.resolve()
        root = self.config.root.resolve()
        return str(resolved.relative_to(root)) if resolved.is_relative_to(root) else str(resolved)

    def approve_command(self, state: LineageState) -> str:
        return f"uv run seeker-schedule approve {state.head.label}"

    # -- the trigger -----------------------------------------------------------------

    def trigger(self, now: datetime | None = None) -> ScheduledRun:
        started = now or datetime.now().astimezone()
        self._clock_start = time.monotonic()
        lock = RunLock(self.config.paths.runs)
        if not lock.acquire():
            return self._finish(started, ScheduleOutcome.LOCKED)
        try:
            return self._locked_trigger(started)
        finally:
            lock.release()

    def _locked_trigger(self, started: datetime) -> ScheduledRun:
        state: LineageState | None = None
        written: tuple[Path, ...] = ()
        spend_before = 0.0
        try:
            state = LineageRecords(self.config).state()
            if state.report_missing:
                written += (ReportJob(self.config).write(state.head.path).path,)
            if state.in_progress is None:
                if state.awaiting_review:
                    return self._finish(started, ScheduleOutcome.AWAITING_REVIEW, state, written)
                last = self.log.last_advanced()
                if not self.cadence.due(last.ended_at if last else None, started):
                    return self._finish(started, ScheduleOutcome.TOO_SOON, state, written)
            spend_before = self._spent(state)
            model = self.model or AnthropicModel(api_key=self.config.api_key())
            result = RoundRunner(self.config, model, started.date()).advance(state, self.config.budget_usd)
            return self._finish(started, result.outcome, state, written + result.written, result.cost_usd, result=result)
        except Exception as error:  # noqa: BLE001 - the trigger must record every failure
            cost = max(0.0, self._spent(state) - spend_before) if state is not None else 0.0
            message = f"{type(error).__name__}: {error}"
            return self._finish(started, ScheduleOutcome.FAILED, state, written, cost, failure=message)

    def _spent(self, state: LineageState | None) -> float:
        """What the round after the head has spent so far, by its records; 0 when there is none."""
        if state is None:
            return 0.0
        try:
            records = LineageRecords(self.config)
            generation = state.in_progress or records.child_of(state.head)
            if generation is None:
                return 0.0
            spent = GenerationFile(generation).read().estimated_cost_usd
            run_path = records.run_of(generation)
            if run_path is not None:
                spent += CostMeter(self.config.prices, 0.0).spent(DebateFile(run_path).read())
            return spent
        except Exception:  # noqa: BLE001 - a cost estimate must never mask the original failure
            return 0.0

    # -- recording -------------------------------------------------------------------

    def _finish(
        self,
        started: datetime,
        outcome: ScheduleOutcome,
        state: LineageState | None = None,
        written: tuple[Path, ...] = (),
        cost: float = 0.0,
        failure: str | None = None,
        result: RoundResult | None = None,
    ) -> ScheduledRun:
        record = ScheduledRun(
            started_at=started,
            ended_at=started + timedelta(seconds=time.monotonic() - self._clock_start),
            schedule_outcome=outcome,
            head_run_path=state.head.label if state is not None else None,
            head_round=state.head.round if state is not None else None,
            written_paths=tuple(self.label(p) for p in written),
            budget_usd=self.config.budget_usd,
            estimated_cost_usd=round(cost, 6),
            failure_message=failure,
        )
        if outcome.did_work:
            problem = self._note(record, state, result)
            if problem is not None:
                joined = f"{failure}; {problem}" if failure else problem
                record = record.model_copy(update={"failure_message": joined})
        self.log.write(record)
        return record

    def _note(self, record: ScheduledRun, state: LineageState | None, result: RoundResult | None) -> str | None:
        """Write the vault note; return a problem message instead of failing the trigger."""
        try:
            folder = self.config.vault().runs
            run: DebateRun | None = None
            report: str | None = None
            round_: int | None = state.head.round if state is not None else None
            if result is not None:
                round_ = result.round
                if result.debate_run is not None and result.outcome is ScheduleOutcome.ADVANCED:
                    run = DebateFile(result.debate_run).read()
                if result.report is not None:
                    report = self.label(result.report)
            elif state is not None and record.schedule_outcome is ScheduleOutcome.AWAITING_REVIEW:
                run = DebateFile(state.head.path).read()
                head_report = self.config.paths.reports / f"{state.head.path.stem}.md"
                report = self.label(head_report) if head_report.is_file() else None
            approve = self.approve_command(state) if state is not None else None
            RunNote(record, round_, run=run, report=report, approve_command=approve).write(folder)
        except Exception as error:  # noqa: BLE001 - a missing vault must not fail the round
            return f"vault note not written: {type(error).__name__}: {error}"
        return None
