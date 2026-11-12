"""Ranking a run's debated ideas: blind comparisons in seeded order, per-axis Elo, survivors."""

from __future__ import annotations

from seeker.debate.debater import Feedback
from seeker.debate.elo import Ratings, Survivors
from seeker.debate.judging import Entrant, JudgePrompt, JudgmentDraft
from seeker.debate.meter import CostMeter
from seeker.debate.record import DebateResumeMismatch, DebateSink
from seeker.debate.schedule import Pairing, Schedule
from seeker.generate.draft import DraftProblem
from seeker.generate.prompt import SystemPrompt
from seeker.generate.role_file import LoadedRole
from seeker.models import LanguageModel, ModelCallFailed, ModelRequest, RetryContext
from seeker.ontology import Comparison, DebateRun, Generation, Reading, StopReason, Tournament, Usage

K_FACTOR = 32.0
INITIAL_RATING = 1500.0
MAX_ATTEMPTS = 2


class TournamentRunner:
    """Judges the scheduled comparisons a run's record does not have yet, saving after each one."""

    def __init__(
        self, judge: LoadedRole, model: LanguageModel, reading: Reading, meter: CostMeter, max_comparisons: int
    ) -> None:
        self.judge = judge
        self.model = model
        self.reading = reading
        self.meter = meter
        self.max_comparisons = max_comparisons

    @staticmethod
    def entrants(run: DebateRun, generation: Generation) -> tuple[Entrant, ...]:
        """Ideas whose debate ended defended or revised, in position order."""
        ideas = {idea.position: idea for idea in generation.ideas}
        return tuple(Entrant(idea=ideas[d.position], debate=d) for d in run.debates if d.competes)

    def schedule(self, run: DebateRun, generation: Generation) -> Schedule:
        positions = tuple(e.position for e in self.entrants(run, generation))
        return Schedule.build(positions, run.tournament_seed, self.max_comparisons)

    def play(self, run: DebateRun, generation: Generation, sink: DebateSink | None = None) -> DebateRun:
        entrants = self.entrants(run, generation)
        positions = tuple(e.position for e in entrants)
        if len(positions) < 2:
            skipped = self._tournament(positions, (), skipped=True)
            return self._save(run, skipped, StopReason.FINISHED, sink)
        schedule = Schedule.build(positions, run.tournament_seed, self.max_comparisons)
        done = self._played(run, schedule, positions)
        system = SystemPrompt(self.judge.role, self.reading).render()
        for pairing in schedule.pairings[len(done) :]:
            if self.meter.reached(run):
                return self._save(run, self._tournament(positions, done), StopReason.BUDGET, sink)
            done += (self._judge(pairing, entrants, run.tournament_seed, system),)
            run = self._save(run, self._tournament(positions, done), None, sink)
        final = self._tournament(positions, done)
        final = final.model_copy(update={"survivors": Survivors.pick(final.ratings)})
        return self._save(run, Tournament.model_validate(final.model_dump()), StopReason.FINISHED, sink)

    # -- internals -------------------------------------------------------------------

    def _played(self, run: DebateRun, schedule: Schedule, positions: tuple[int, ...]) -> tuple[Comparison, ...]:
        """Comparisons already recorded, which must be a prefix of this schedule."""
        if run.tournament is None:
            return ()
        recorded = run.tournament.comparisons
        if tuple(run.tournament.entrants) != positions:
            raise DebateResumeMismatch("tournament entrants", str(run.tournament.entrants), str(positions))
        expected = schedule.pairings[: len(recorded)]
        if tuple((c.first, c.second) for c in recorded) != tuple((p.first, p.second) for p in expected):
            raise DebateResumeMismatch("tournament schedule", "the recorded comparisons", "a different schedule")
        return recorded

    def _judge(self, pairing: Pairing, entrants: tuple[Entrant, ...], seed: int, system: str) -> Comparison:
        side = {e.position: e for e in entrants}
        prompt = JudgePrompt(pairing, side[pairing.first], side[pairing.second], seed).render()
        spent = Usage.zero()
        retry: RetryContext | None = None
        for _attempt in range(MAX_ATTEMPTS):
            request = ModelRequest(
                model=self.judge.role.model,
                system=system,
                prompt=prompt,
                output=JudgmentDraft.output_spec(),
                max_tokens=self.judge.role.max_output_tokens,
                effort=self.judge.role.effort,
                retry=retry,
            )
            try:
                reply = self.model.reply(request)
            except ModelCallFailed:
                return JudgmentDraft.failed(pairing, self.judge.role.model, spent)
            spent = spent + reply.usage
            draft, problems = JudgmentDraft.parse(reply.output_json)
            if draft is not None:
                problems = draft.problems()
                if not problems:
                    return draft.to_comparison(pairing, self.judge.role.model, spent)
            retry = RetryContext(previous_output=reply.output_json, feedback=Feedback.text(problems or self._no_answer()))
        return JudgmentDraft.failed(pairing, self.judge.role.model, spent)

    @staticmethod
    def _no_answer() -> tuple[DraftProblem, ...]:
        return (DraftProblem(field="answer", message="give one verdict per axis"),)

    def _tournament(self, positions: tuple[int, ...], comparisons: tuple[Comparison, ...], skipped: bool = False) -> Tournament:
        return Tournament(
            k_factor=K_FACTOR,
            initial_rating=INITIAL_RATING,
            max_comparisons=self.max_comparisons,
            entrants=positions,
            comparisons=comparisons,
            ratings=() if skipped else Ratings.recompute(positions, comparisons, K_FACTOR, INITIAL_RATING),
            survivors=(),
            skipped=skipped,
        )

    def _save(self, run: DebateRun, tournament: Tournament, stop: StopReason | None, sink: DebateSink | None) -> DebateRun:
        updated = DebateRun.model_validate(
            {**run.model_dump(), "tournament": tournament.model_dump(), "stop_reason": stop}
        )
        updated = self.meter.totals(updated)
        if sink is not None:
            sink.save(updated)
        return updated
