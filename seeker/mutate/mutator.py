"""The mutator role applied to a plan: one validated child per planned position, parents copied."""

from __future__ import annotations

from datetime import datetime, timezone

from seeker.config import PriceTable
from seeker.generate.draft import DraftProblem, IdeaDraft
from seeker.generate.generator import MAX_ATTEMPTS, ResumeMismatch, UnpricedModel
from seeker.generate.prompt import SystemPrompt
from seeker.generate.record import GenerationSink
from seeker.generate.role_file import LoadedRole
from seeker.models import LanguageModel, ModelCallFailed, ModelRequest, RetryContext
from seeker.mutate.plan import MutationPlan, PlannedIdea
from seeker.mutate.prompt import MutationPrompt
from seeker.ontology import (
    DeckSet,
    Generation,
    GenerationFailure,
    GitCommit,
    Idea,
    MutationKind,
    Reading,
    StopReason,
    Usage,
)


class IdeaMutator:
    """Makes every child of a plan through the mutator role, retried once, and copies the carried parents.

    With a ``budget_usd``, it checks the generation's recorded spend before each child's model call
    and stops cleanly once the spend has reached the budget, saving ``stop_reason: budget``."""

    def __init__(
        self,
        role: LoadedRole,
        model: LanguageModel,
        deck_set: DeckSet,
        prices: PriceTable,
        budget_usd: float | None = None,
    ) -> None:
        if prices.price_for(role.role.model) is None:
            raise UnpricedModel(role.role.model)
        self.role = role
        self.model = model
        self.deck_set = deck_set
        self.prices = prices
        self.budget_usd = budget_usd
        self.output = IdeaDraft.output_spec()

    def reached(self, current: Generation) -> bool:
        """Whether the generation's recorded spend has reached the budget."""
        return self.budget_usd is not None and current.estimated_cost_usd >= self.budget_usd

    def system(self, reading: Reading) -> str:
        return SystemPrompt(self.role.role, reading).render()

    def mutate(
        self,
        plan: MutationPlan,
        reading: Reading,
        record: Generation | None = None,
        sink: GenerationSink | None = None,
        git_commit: GitCommit | None = None,
    ) -> Generation:
        if record is not None:
            self._check_resume(record, plan, reading)
        current = record or self._empty(plan, reading, git_commit)
        current = current.model_copy(update={"stop_reason": None})
        system = self.system(reading)
        for entry in plan.entries:
            if current.idea_at(entry.position) is not None:
                continue
            if entry.kind is MutationKind.CARRIED:
                outcome: Idea | GenerationFailure = self.carried(entry)
            else:
                if self.reached(current):
                    current = current.model_copy(update={"stop_reason": StopReason.BUDGET})
                    if sink is not None:
                        sink.save(current)
                    return current
                outcome = self._one(entry, system, self.taken(entry, plan, current))
            current = self._with(current, outcome)
            if sink is not None:
                sink.save(current)
        return current

    @staticmethod
    def carried(entry: PlannedIdea) -> Idea:
        """The parent itself at its new position, with a carried lineage and no usage of its own."""
        return entry.parent.idea.model_copy(
            update={"position": entry.position, "lineage": entry.lineage, "usage": Usage.zero()}
        )

    @staticmethod
    def taken(entry: PlannedIdea, plan: MutationPlan, current: Generation) -> tuple[str, ...]:
        """Statements of this parent's earlier reworkings already written."""
        found = (current.idea_at(sibling.position) for sibling in plan.siblings_before(entry))
        return tuple(idea.statement for idea in found if idea is not None)

    # -- one child ---------------------------------------------------------------------

    def _one(self, entry: PlannedIdea, system: str, taken: tuple[str, ...]) -> Idea | GenerationFailure:
        prompt = MutationPrompt(entry, self.deck_set, taken).render()
        spent = Usage.zero()
        retry: RetryContext | None = None
        problems: tuple[DraftProblem, ...] = ()
        for _attempt in range(MAX_ATTEMPTS):
            request = ModelRequest(
                model=self.role.role.model,
                system=system,
                prompt=prompt,
                output=self.output,
                max_tokens=self.role.role.max_output_tokens,
                effort=self.role.role.effort,
                retry=retry,
            )
            try:
                reply = self.model.reply(request)
            except ModelCallFailed as exc:
                return GenerationFailure(position=entry.position, reason=f"model call failed: {exc}", usage=spent)
            spent = spent + reply.usage
            draft, problems = IdeaDraft.parse(reply.output_json)
            if draft is not None:
                problems = draft.problems_for(entry.draw)
                if not problems:
                    return draft.to_idea(entry.position, spent).model_copy(update={"lineage": entry.lineage})
            retry = RetryContext(previous_output=reply.output_json, feedback=DraftProblem.feedback(problems))
        reason = "; ".join(str(problem) for problem in problems)
        return GenerationFailure(position=entry.position, reason=f"invalid after retry: {reason}", usage=spent)

    # -- records -----------------------------------------------------------------------

    def _empty(self, plan: MutationPlan, reading: Reading, git_commit: GitCommit | None) -> Generation:
        return Generation(
            draw_batch=plan.batch,
            reading=reading,
            role_name=self.role.role.role_name,
            model=self.role.role.model,
            role_digest=self.role.digest,
            git_commit=git_commit,
            generated_at=datetime.now(timezone.utc),
            usage=Usage.zero(),
            estimated_cost_usd=0.0,
            mutation=plan.origin,
        )

    def _with(self, current: Generation, outcome: Idea | GenerationFailure) -> Generation:
        ideas = tuple(i for i in current.ideas if i.position != outcome.position)
        failures = tuple(f for f in current.failures if f.position != outcome.position)
        if isinstance(outcome, Idea):
            ideas += (outcome,)
        else:
            failures += (outcome,)
        ideas = tuple(sorted(ideas, key=lambda idea: idea.position))
        failures = tuple(sorted(failures, key=lambda failure: failure.position))
        total = Usage.total(tuple(r.usage for r in (*ideas, *failures)))
        return Generation.model_validate(
            {
                **current.model_dump(),
                "ideas": [i.model_dump() for i in ideas],
                "failures": [f.model_dump() for f in failures],
                "usage": total.model_dump(),
                "estimated_cost_usd": round(self.prices.cost(self.role.role.model, total), 6),
            }
        )

    def _check_resume(self, record: Generation, plan: MutationPlan, reading: Reading) -> None:
        recorded = record.mutation
        if recorded is None:
            raise ResumeMismatch("mutation origin", "none (a drawn generation)", plan.origin.parent_run_path)
        checks = (
            ("parent run digest", recorded.parent_run_digest[:12], plan.origin.parent_run_digest[:12]),
            ("mutation seed", str(recorded.mutation_seed), str(plan.origin.mutation_seed)),
            ("deck-set digest", record.draw_batch.deck_set_digest[:12], plan.deck_set_digest[:12]),
            ("reading", record.reading.value, reading.value),
            ("role digest", record.role_digest[:12], self.role.digest[:12]),
            ("model", str(record.model), str(self.role.role.model)),
        )
        for field, was, now in checks:
            if was != now:
                raise ResumeMismatch(field, was, now)
        if record.draw_batch != plan.batch:
            raise ResumeMismatch("draw batch", "the recorded draws", "different draws")
