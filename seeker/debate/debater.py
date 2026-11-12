"""One idea's round of debate: three critics, then the advocate, each retried once."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from pydantic import ConfigDict, Field

from seeker.debate.drafts import CritiqueDraft, DefenseDraft, ProsecutorDraft
from seeker.debate.findings import CapturedWork, ProsecutorFindings
from seeker.debate.prompts import AdvocatePrompt, CriticPrompt, ProsecutorPrompt
from seeker.debate.roles import DebateRoles
from seeker.generate.draft import DraftProblem
from seeker.generate.prompt import SystemPrompt
from seeker.generate.role_file import LoadedRole
from seeker.models import LanguageModel, ModelCallFailed, ModelReply, ModelRequest, OutputSpec, RetryContext
from seeker.ontology import (
    Card,
    Critique,
    Debate,
    DebateFailure,
    Defense,
    DeckSet,
    Draw,
    Idea,
    Reading,
    RoleName,
    SeekerModel,
    Usage,
)
from seeker.works.catalog import WorkNotes
from seeker.works.check import DrawPriorArt

MAX_ATTEMPTS = 2


class Feedback:
    """The follow-up turn after a rejected answer."""

    @staticmethod
    def text(problems: tuple[DraftProblem, ...]) -> str:
        bullets = "\n".join(f"- {problem}" for problem in problems)
        return f"That answer was rejected:\n{bullets}\nAnswer again with the corrected JSON object."


class DebateOutcome(SeekerModel):
    """What debating one idea produced: the debate (unless the advocate failed or every critic did),
    the role failures, and any works the prosecutor captured."""

    model_config = ConfigDict(title="DebateOutcome")

    debate: Debate | None = Field(default=None, description="The finished debate, when there is one.")
    failures: tuple[DebateFailure, ...] = Field(default=(), description="Roles that gave no valid answer, in role order.")
    captured: tuple[CapturedWork, ...] = Field(default=(), description="New work notes the prosecution wrote.")

    @property
    def usage(self) -> Usage:
        parts = [f.usage for f in self.failures] + [c.usage for f in self.failures for c in f.discarded_critiques]
        if self.debate is not None:
            parts += [c.usage for c in self.debate.critiques] + [self.debate.defense.usage]
        return Usage.total(tuple(parts))


class Attempt(SeekerModel):
    """The result of asking one role, with every call's usage summed."""

    model_config = ConfigDict(title="Attempt")

    reply: ModelReply | None = Field(default=None, description="The accepted reply, if any.")
    problems: tuple[DraftProblem, ...] = Field(default=(), description="Why the last answer was rejected.")
    failure: str = Field(default="", description="Why the role produced nothing, when it did not.")
    usage: Usage = Field(default_factory=Usage.zero, description="Every call made for this role.")


class Debater:
    """Runs one round of debate per idea against a model, the decks and the works catalog."""

    def __init__(
        self,
        roles: DebateRoles,
        model: LanguageModel,
        deck_set: DeckSet,
        works: WorkNotes,
        reading: Reading,
        today: date,
    ) -> None:
        self.roles = roles
        self.model = model
        self.deck_set = deck_set
        self.works = works
        self.reading = reading
        self.today = today

    def system(self, name: RoleName) -> str:
        return SystemPrompt(self.roles.role(name).role, self.reading).render()

    def debate(self, idea: Idea, draw: Draw) -> DebateOutcome:
        critiques: list[Critique] = []
        failures: list[DebateFailure] = []
        captured: tuple[CapturedWork, ...] = ()
        prosecution = self._prosecute(idea, draw)
        if isinstance(prosecution, DebateFailure):
            failures.append(prosecution)
        else:
            findings = ProsecutorFindings.capture(prosecution, self.works, self.today)
            critiques.append(findings.critique)
            captured = findings.captured
        for name in (RoleName.SKEPTIC, RoleName.TASTE_CRITIC):
            result = self._critique(name, idea, draw)
            (failures if isinstance(result, DebateFailure) else critiques).append(result)
        if not critiques:
            return DebateOutcome(failures=tuple(failures), captured=captured)
        defense = self._defend(idea, draw, tuple(critiques))
        if isinstance(defense, DebateFailure):
            kept = defense.model_copy(update={"discarded_critiques": tuple(critiques)})
            return DebateOutcome(failures=(*failures, DebateFailure.model_validate(kept.model_dump())), captured=captured)
        final = defense.revision.statement if defense.revision is not None else idea.statement
        debate = Debate(position=idea.position, critiques=tuple(critiques), defense=defense, final_statement=final)
        return DebateOutcome(debate=debate, failures=tuple(failures), captured=captured)

    # -- roles -------------------------------------------------------------------------

    def _prosecute(self, idea: Idea, draw: Draw) -> Critique | DebateFailure:
        loaded = self.roles.role(RoleName.PROSECUTOR)
        catalog = self.works.catalog()
        work_ids = frozenset(str(work.id) for work in catalog.works)
        prompt = ProsecutorPrompt(idea, draw, self.deck_set, DrawPriorArt.of(catalog, draw)).render()
        card_words = self._card_words(draw)

        def check(reply: ModelReply) -> tuple[DraftProblem, ...]:
            parsed, problems = ProsecutorDraft.parse(reply.output_json)
            if parsed is None:
                return problems
            return parsed.problems_for(idea, draw, card_words) + parsed.evidence_problems(reply.result_urls, work_ids)

        attempt = self._ask(loaded, prompt, ProsecutorDraft.output_spec(), check)
        if attempt.reply is None:
            return self._failure(idea, loaded, attempt)
        parsed, _ = ProsecutorDraft.parse(attempt.reply.output_json)
        return parsed.to_prosecution(loaded.role.model, attempt.usage, draw)

    def _critique(self, name: RoleName, idea: Idea, draw: Draw) -> Critique | DebateFailure:
        loaded = self.roles.role(name)
        card_words = self._card_words(draw)

        def check(reply: ModelReply) -> tuple[DraftProblem, ...]:
            parsed, problems = CritiqueDraft.parse(reply.output_json)
            return problems if parsed is None else parsed.problems_for(idea, draw, card_words)

        attempt = self._ask(loaded, CriticPrompt(idea, draw, self.deck_set).render(), CritiqueDraft.output_spec(), check)
        if attempt.reply is None:
            return self._failure(idea, loaded, attempt)
        parsed, _ = CritiqueDraft.parse(attempt.reply.output_json)
        return parsed.to_critique(name, loaded.role.model, attempt.usage)

    def _defend(self, idea: Idea, draw: Draw, critiques: tuple[Critique, ...]) -> Defense | DebateFailure:
        loaded = self.roles.role(RoleName.ADVOCATE)
        foreign = self._foreign_cards(draw)

        def check(reply: ModelReply) -> tuple[DraftProblem, ...]:
            parsed, problems = DefenseDraft.parse(reply.output_json)
            return problems if parsed is None else parsed.problems_for(critiques, foreign)

        prompt = AdvocatePrompt(idea, draw, self.deck_set, critiques).render()
        attempt = self._ask(loaded, prompt, DefenseDraft.output_spec(), check)
        if attempt.reply is None:
            return self._failure(idea, loaded, attempt)
        parsed, _ = DefenseDraft.parse(attempt.reply.output_json)
        return parsed.to_defense(loaded.role.model, attempt.usage)

    # -- calls -------------------------------------------------------------------------

    def _ask(
        self, loaded: LoadedRole, prompt: str, output: OutputSpec, check: Callable[[ModelReply], tuple[DraftProblem, ...]]
    ) -> Attempt:
        """Ask once, and once more with feedback if the answer is rejected."""
        spent = Usage.zero()
        retry: RetryContext | None = None
        problems: tuple[DraftProblem, ...] = ()
        for _attempt in range(MAX_ATTEMPTS):
            request = ModelRequest(
                model=loaded.role.model,
                system=self.system(loaded.role.role_name),
                prompt=prompt,
                output=output,
                max_tokens=loaded.role.max_output_tokens,
                effort=loaded.role.effort,
                retry=retry,
                max_searches=loaded.role.max_searches,
            )
            try:
                reply = self.model.reply(request)
            except ModelCallFailed as exc:
                return Attempt(failure=f"model call failed: {exc}", usage=spent)
            spent = spent + reply.usage
            problems = check(reply)
            if not problems:
                return Attempt(reply=reply, usage=spent)
            retry = RetryContext(previous_output=reply.output_json, feedback=Feedback.text(problems))
        reason = "; ".join(str(problem) for problem in problems)
        return Attempt(problems=problems, failure=f"invalid after retry: {reason}", usage=spent)

    @staticmethod
    def _failure(idea: Idea, loaded: LoadedRole, attempt: Attempt) -> DebateFailure:
        return DebateFailure(
            position=idea.position,
            role_name=loaded.role.role_name,
            model=loaded.role.model,
            failure_reason=attempt.failure,
            usage=attempt.usage,
        )

    def _card_words(self, draw: Draw) -> frozenset[str]:
        words: set[str] = set()
        for card_id in draw.drawn_cards:
            card = self.deck_set.card(card_id)
            names = (card.name, *card.synonyms) if card is not None else (card_id,)
            for name in (*names, card_id):
                words.update(name.lower().replace("-", " ").split())
        return frozenset(words)

    def _foreign_cards(self, draw: Draw) -> tuple[Card, ...]:
        return tuple(card for deck in self.deck_set.decks for card in deck.cards if card.id not in draw.drawn_cards)
