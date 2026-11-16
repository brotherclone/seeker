"""What the mutator sees: the parent as it survived its debate, then the cards the child must use."""

from __future__ import annotations

from seeker.generate.prompt import DrawPrompt
from seeker.mutate.plan import Parent, PlannedIdea
from seeker.ontology import Critique, DeckSet, MutationKind


class ParentBlock:
    """The survivor in its final form, how its cards were read, and its debate with the advocate's replies.

    Critiques keep their role names here: the mutator is not judging, and knowing an
    objection came from the prior-art prosecutor is useful to it."""

    def __init__(self, parent: Parent) -> None:
        self.parent = parent

    def lines(self) -> list[str]:
        idea, debate = self.parent.idea, self.parent.debate
        final = debate.defense.revision or idea
        lines = [f"Parent idea (as it survived its debate): {debate.final_statement}"]
        if debate.defense.revision is not None:
            lines.append(f"  (originally: {idea.statement})")
        lines += [
            f"- subject (X): {final.subject}",
            f"- behavior (Y): {final.behavior}",
            f"- rationale (Z): {final.rationale}",
            "",
            "Parent card readings:",
        ]
        lines += [f"- {reading.card}: {reading.interpretation}" for reading in idea.card_readings]
        lines += ["", f"The parent's debate (outcome: {debate.defense.outcome.value}):"]
        for critique in debate.critiques:
            lines += self.critique_lines(critique)
        return lines

    def critique_lines(self, critique: Critique) -> list[str]:
        lines = [
            f"- {critique.role_name.value} ({critique.severity.value}): {critique.failure}",
            f"  Argument: {critique.argument}",
        ]
        reply = self.parent.debate.defense.reply_to(critique.role_name)
        if reply is not None:
            lines.append(f"  Advocate {reply.move.value}s: {reply.argument}")
        return lines


class MutationPrompt:
    """One child's prompt: the parent block, the task, and the child's draw."""

    def __init__(self, entry: PlannedIdea, deck_set: DeckSet, taken: tuple[str, ...] = ()) -> None:
        if entry.kind is MutationKind.CARRIED:
            raise ValueError("a carried parent is copied, not prompted")
        self.entry = entry
        self.deck_set = deck_set
        self.taken = taken

    def task_lines(self) -> list[str]:
        entry = self.entry
        if entry.kind is MutationKind.REWORKING:
            lines = [
                "Task: reworking. The cards below are the parent's own. Do not polish the parent; find a "
                "different idea in the same collision that answers its strongest objection."
            ]
            if self.taken:
                lines.append("Already taken (go elsewhere: a different subject or a different behavior):")
                lines += [f"- {statement}" for statement in self.taken]
            return lines
        new = self.deck_set.card(entry.new_card or "")
        old = self.deck_set.card(entry.lineage.replaced_card or "")
        return [
            f"Task: card swap. On the {entry.lineage.swapped_axis} axis, "
            f"{new.name if new else entry.new_card} (id: {entry.new_card}) is new and replaces "
            f"{old.name if old else entry.lineage.replaced_card} (id: {entry.lineage.replaced_card}). "
            "Use all three cards below, the new one included. Keep what the debate showed works in the "
            "parent and drop what it showed fails."
        ]

    def render(self) -> str:
        draw = self.entry.draw
        order = ", ".join(draw.drawn_cards)
        lines = [
            *ParentBlock(self.entry.parent).lines(),
            "",
            *self.task_lines(),
            "",
            *DrawPrompt(draw, self.deck_set).card_lines(),
            "",
            "Write one new idea from these three cards and answer with the JSON object only. "
            f"Give exactly one card reading per card, in this order of ids: {order}.",
        ]
        return "\n".join(lines)
