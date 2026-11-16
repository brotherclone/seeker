"""How healthy a run's judging and debating looked: position bias, split pairs, severities, outcomes.

Everything is counted from the record; no API call. Carried debates belong to the
parent run, so the severity and outcome counts leave them out."""

from __future__ import annotations

from collections import Counter

from pydantic import ConfigDict, Field

from seeker.ontology import Comparison, DebateRun, DefenseOutcome, RoleName, ScoreAxis, SeekerModel, Severity


class AxisBias(SeekerModel):
    """On one axis: how often the idea shown as A won, and how often a pair's two orders disagreed."""

    model_config = ConfigDict(title="AxisBias")

    axis: ScoreAxis
    a_wins: int = Field(ge=0, description="Comparisons won by the idea shown as A.")
    judged: int = Field(ge=0, description="Comparisons with a verdict on this axis.")
    splits: int | None = Field(default=None, ge=0, description="Pairs whose two orders named different winners; None when single-order.")
    pairs: int | None = Field(default=None, ge=0, description="Pairs judged in both orders; None when single-order.")

    @property
    def a_share(self) -> float:
        return self.a_wins / self.judged if self.judged else 0.0


class SeverityCount(SeekerModel):
    """How many critiques one critic gave at one severity."""

    model_config = ConfigDict(title="SeverityCount")

    critic: RoleName
    severity: Severity
    count: int = Field(ge=0)


class OutcomeCount(SeekerModel):
    """How many debates ended with one defense outcome."""

    model_config = ConfigDict(title="OutcomeCount")

    outcome: DefenseOutcome
    count: int = Field(ge=0)


class JudgeHealth(SeekerModel):
    """A run's position bias per axis, plus the spread of its critics' severities and the advocate's outcomes."""

    model_config = ConfigDict(title="JudgeHealth")

    both_orders: bool
    axes: tuple[AxisBias, ...] = ()
    severities: tuple[SeverityCount, ...] = ()
    outcomes: tuple[OutcomeCount, ...] = ()

    @classmethod
    def of(cls, run: DebateRun) -> JudgeHealth:
        tournament = run.tournament
        comparisons = tuple(c for c in (tournament.comparisons if tournament else ()) if not c.failed)
        both = bool(tournament and tournament.both_orders)
        axes = tuple(cls._axis(axis, comparisons, both) for axis in ScoreAxis)
        own = tuple(d for d in run.debates if d.carried_from is None)
        tally = Counter((c.role_name, c.severity) for d in own for c in d.critiques)
        severities = tuple(
            SeverityCount(critic=role, severity=severity, count=tally[(role, severity)])
            for role in (RoleName.PROSECUTOR, RoleName.SKEPTIC, RoleName.TASTE_CRITIC)
            for severity in Severity
        )
        ends = Counter(d.defense.outcome for d in own)
        outcomes = tuple(OutcomeCount(outcome=outcome, count=ends[outcome]) for outcome in DefenseOutcome)
        return cls(both_orders=both, axes=axes, severities=severities, outcomes=outcomes)

    @staticmethod
    def _axis(axis: ScoreAxis, comparisons: tuple[Comparison, ...], both: bool) -> AxisBias:
        verdicts = [(c, v) for c in comparisons if (v := c.verdict_on(axis)) is not None]
        a_wins = sum(1 for c, v in verdicts if v.winner == c.first)
        if not both:
            return AxisBias(axis=axis, a_wins=a_wins, judged=len(verdicts))
        keys = {frozenset(comparison.pair) for comparison, _ in verdicts}
        found = [tuple(v.winner for c, v in verdicts if frozenset(c.pair) == key) for key in keys]
        complete = [winners for winners in found if len(winners) == 2]
        splits = sum(1 for first, second in complete if first != second)
        return AxisBias(axis=axis, a_wins=a_wins, judged=len(verdicts), splits=splits, pairs=len(complete))

    def severity_count(self, critic: RoleName, severity: Severity) -> int:
        return next((s.count for s in self.severities if s.critic is critic and s.severity is severity), 0)

    def bias_on(self, axis: ScoreAxis) -> AxisBias:
        return next(a for a in self.axes if a.axis is axis)
