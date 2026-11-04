"""Turning every draw of a batch into one validated Idea."""

from __future__ import annotations

from datetime import datetime, timezone

from seeker.config import ModelPrice, PriceTable
from seeker.generate.draft import DraftProblem, IdeaDraft
from seeker.generate.prompt import DrawPrompt, SystemPrompt
from seeker.generate.record import GenerationSink
from seeker.generate.role_file import LoadedRole
from seeker.models import LanguageModel, ModelCallFailed, ModelRequest, RetryContext
from seeker.ontology import (
    DeckSet,
    Draw,
    DrawBatch,
    Generation,
    GenerationFailure,
    GitCommit,
    Idea,
    Reading,
    Usage,
)

MAX_ATTEMPTS = 2


class GenerationError(Exception):
    """A generation cannot start."""


class UnpricedModel(GenerationError):
    def __init__(self, model: str) -> None:
        super().__init__(f"model {model} has no entry in the price table (seeker.yaml: prices.models)")


class ResumeMismatch(GenerationError):
    def __init__(self, field: str, recorded: str, requested: str) -> None:
        self.field = field
        super().__init__(
            f"cannot resume: the existing record's {field} is {recorded!r} but this run's is {requested!r}; "
            "use a new output path"
        )


class IdeaGenerator:
    """The generator role applied to a batch: one idea per draw, retried once."""

    def __init__(self, role: LoadedRole, model: LanguageModel, deck_set: DeckSet, prices: PriceTable) -> None:
        price = prices.price_for(role.role.model)
        if price is None:
            raise UnpricedModel(role.role.model)
        self.role = role
        self.model = model
        self.deck_set = deck_set
        self.price: ModelPrice = price
        self.output = IdeaDraft.output_spec()

    def prompts(self, batch: DrawBatch, reading: Reading) -> tuple[str, tuple[str, ...]]:
        """The system block and every draw's user prompt, exactly as they would be sent."""
        return SystemPrompt(self.role.role, reading).render(), tuple(
            DrawPrompt(draw, self.deck_set).render() for draw in batch.draws
        )

    def generate(
        self,
        batch: DrawBatch,
        reading: Reading = Reading.LITERAL,
        record: Generation | None = None,
        sink: GenerationSink | None = None,
        git_commit: GitCommit | None = None,
    ) -> Generation:
        if record is not None:
            self._check_resume(record, batch, reading)
        current = record or self._empty(batch, reading, git_commit)
        system = SystemPrompt(self.role.role, reading).render()
        done = {idea.position for idea in current.ideas}
        for draw in batch.draws:
            if draw.position in done:
                continue
            outcome = self._one(draw, system)
            current = self._with(current, outcome)
            if sink is not None:
                sink.save(current)
        return current

    # -- one draw --------------------------------------------------------------

    def _one(self, draw: Draw, system: str) -> Idea | GenerationFailure:
        prompt = DrawPrompt(draw, self.deck_set).render()
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
                return GenerationFailure(position=draw.position, reason=f"model call failed: {exc}", usage=spent)
            spent = spent + reply.usage
            draft, problems = IdeaDraft.parse(reply.output_json)
            if draft is not None:
                problems = draft.problems_for(draw)
                if not problems:
                    return draft.to_idea(draw.position, spent)
            retry = RetryContext(previous_output=reply.output_json, feedback=DraftProblem.feedback(problems))
        reason = "; ".join(str(problem) for problem in problems)
        return GenerationFailure(position=draw.position, reason=f"invalid after retry: {reason}", usage=spent)

    # -- records -----------------------------------------------------------------

    def _empty(self, batch: DrawBatch, reading: Reading, git_commit: GitCommit | None) -> Generation:
        return Generation(
            draw_batch=batch,
            reading=reading,
            role_name=self.role.role.role_name,
            model=self.role.role.model,
            role_digest=self.role.digest,
            git_commit=git_commit,
            generated_at=datetime.now(timezone.utc),
            usage=Usage.zero(),
            estimated_cost_usd=0.0,
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
        return current.model_copy(
            update={
                "ideas": ideas,
                "failures": failures,
                "usage": total,
                "estimated_cost_usd": round(self.price.cost(total), 6),
            }
        )

    def _check_resume(self, record: Generation, batch: DrawBatch, reading: Reading) -> None:
        checks = (
            ("batch seed", str(record.draw_batch.seed), str(batch.seed)),
            ("deck-set digest", record.draw_batch.deck_set_digest.short, batch.deck_set_digest.short),
            ("batch size", str(record.draw_batch.size), str(batch.size)),
            ("reading", record.reading.value, reading.value),
            ("role digest", record.role_digest.short, self.role.digest.short),
            ("model", str(record.model), str(self.role.role.model)),
        )
        for field, recorded, requested in checks:
            if recorded != requested:
                raise ResumeMismatch(field, recorded, requested)
        if record.draw_batch != batch:
            raise ResumeMismatch("draw batch", "the recorded draws", "different draws")
