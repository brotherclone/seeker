"""The vault note a scheduled trigger leaves when it did work: what happened, what it cost,
and the survivors of the run it ended on."""

from __future__ import annotations

from pathlib import Path

from seeker.debate.health import SearchHealth
from seeker.ontology import DebateRun, ScheduledRun, ScheduleOutcome, ScoreAxis

HEADLINES = {
    ScheduleOutcome.ADVANCED: "Round {round} finished.",
    ScheduleOutcome.BUDGET: "Round {round} stopped at the cap; it resumes at the next trigger.",
    ScheduleOutcome.AWAITING_REVIEW: "Round {round} waits for review; nothing ran.",
    ScheduleOutcome.FAILED: "The trigger failed.",
}


class RunNote:
    """One Markdown note per trigger that did work, in the vault's runs folder."""

    def __init__(
        self,
        record: ScheduledRun,
        round_: int | None,
        run: DebateRun | None = None,
        report: str | None = None,
        approve_command: str | None = None,
    ) -> None:
        self.record = record
        self.round = round_
        self.run = run
        self.report = report
        self.approve_command = approve_command

    @property
    def name(self) -> str:
        when = self.record.started_at.strftime("%Y-%m-%d %H%M")
        round_ = f" round-{self.round}" if self.round is not None else ""
        return f"{when}{round_} {self.record.schedule_outcome.value}.md"

    def render(self) -> str:
        record = self.record
        outcome = record.schedule_outcome
        lines = [
            "---",
            "type: note",
            "tags:",
            "- seeker",
            "- scheduled-run",
            f"outcome: {outcome.value}",
            *([f"round: {self.round}"] if self.round is not None else []),
            f"cost_usd: {record.estimated_cost_usd:.2f}",
            "---",
            "",
            "Back to [[Seeker]] · A [[ScheduledRun]] ending in [[ScheduleOutcome]] `" + outcome.value + "`",
            "",
            HEADLINES[outcome].format(round=self.round if self.round is not None else "?"),
            "",
            f"- Started {record.started_at:%Y-%m-%d %H:%M}, ended {record.ended_at:%H:%M}",
            f"- Cost: ${record.estimated_cost_usd:.2f} of ${record.budget_usd:.2f}",
        ]
        if record.head_run_path:
            lines.append(f"- Started from `{record.head_run_path}` (round {record.head_round})")
        lines += [f"- Wrote `{path}`" for path in record.written_paths]
        if self.report:
            lines.append(f"- Report: `{self.report}`")
        if record.failure_message:
            lines += ["", "## Problem", "", record.failure_message]
        if self.approve_command and outcome is ScheduleOutcome.AWAITING_REVIEW:
            lines += ["", "## To continue", "", f"Review the report, then run `{self.approve_command}`."]
        lines += self._survivors()
        return "\n".join(lines) + "\n"

    def _survivors(self) -> list[str]:
        run = self.run
        if run is None or run.tournament is None or not run.tournament.survivors:
            return []
        lines = ["", "## Survivors", ""]
        for rank, position in enumerate(run.tournament.survivors, start=1):
            promise = run.tournament.rating_of(position, ScoreAxis.PROMISE)
            rating = f"{promise.rating:.0f}" if promise is not None else "?"
            debate = run.debate_at(position)
            statement = debate.final_statement if debate is not None else "(no debate)"
            lines.append(f"{rank}. **#{position}** (promise {rating}): {statement}")
        health = SearchHealth.of(run)
        found = f"{health.line}, {health.citations} citations" if health is not None else "No search outcomes recorded."
        lines += ["", "## Prior-art search", "", found]
        return lines

    def write(self, folder: Path) -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / self.name
        path.write_text(self.render(), encoding="utf-8")
        return path
