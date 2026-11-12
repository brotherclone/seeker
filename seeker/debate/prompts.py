"""What the critics and the advocate see. The judge's blinded prompt lives with the tournament."""

from __future__ import annotations

from seeker.generate.prompt import DrawPrompt
from seeker.ontology import Critique, DeckSet, Draw, Idea, RoleName
from seeker.works.check import DrawPriorArt


class IdeaBlock:
    """One idea with its draw: the cards in full, the statement, its parts and the card readings."""

    def __init__(self, idea: Idea, draw: Draw, deck_set: DeckSet) -> None:
        self.idea = idea
        self.draw = draw
        self.deck_set = deck_set

    def lines(self) -> list[str]:
        lines = DrawPrompt(self.draw, self.deck_set).card_lines()
        lines += [
            "",
            f"Idea: {self.idea.statement}",
            f"- subject (X): {self.idea.subject}",
            f"- behavior (Y): {self.idea.behavior}",
            f"- rationale (Z): {self.idea.rationale}",
            "",
            "Card readings:",
        ]
        lines += [f"- {reading.card}: {reading.interpretation}" for reading in self.idea.card_readings]
        return lines


class CriticPrompt:
    """What the skeptic and the taste critic see: the idea alone, never another critique."""

    CLOSING = (
        "Attack this idea as your role directs and answer with the JSON object only. "
        "If the target is card_reading, set target_card to that card's id; otherwise leave it empty."
    )

    def __init__(self, idea: Idea, draw: Draw, deck_set: DeckSet) -> None:
        self.block = IdeaBlock(idea, draw, deck_set)

    def render(self) -> str:
        return "\n".join([*self.block.lines(), "", self.CLOSING])


class ProsecutorPrompt(CriticPrompt):
    """The idea plus what Seeker's own catalog already holds for its cards."""

    def __init__(self, idea: Idea, draw: Draw, deck_set: DeckSet, prior_art: DrawPriorArt) -> None:
        super().__init__(idea, draw, deck_set)
        self.prior_art = prior_art

    def catalog_lines(self) -> list[str]:
        if not self.prior_art.hits:
            return ["Catalog: the catalog has no prior art for this draw (no captured work links two of its cards)."]
        lines = ["Catalog: captured works that already link two or more of this draw's cards:"]
        for hit in self.prior_art.hits:
            scope = "all three cards" if hit.full else "cards " + ", ".join(hit.shared)
            lines.append(f"- work id {hit.work_id}: {hit.title} (links {scope})")
        lines.append("Cite a catalog work by its work id, in work_id, with url left empty.")
        return lines

    def render(self) -> str:
        return "\n".join(
            [
                *self.block.lines(),
                "",
                *self.catalog_lines(),
                "",
                "Then search the web. Cite search results by their exact URL, in url, with work_id left empty.",
                self.CLOSING,
            ]
        )


class AdvocatePrompt:
    """The idea and every critique it faced, each labelled with the critic role it must be answered as."""

    def __init__(self, idea: Idea, draw: Draw, deck_set: DeckSet, critiques: tuple[Critique, ...]) -> None:
        self.block = IdeaBlock(idea, draw, deck_set)
        self.critiques = critiques

    def critique_lines(self, critique: Critique) -> list[str]:
        target = critique.target.value + (f" ({critique.target_card})" if critique.target_card else "")
        lines = [
            f"Critique from {critique.role_name.value} (severity {critique.severity.value}, target {target}):",
            f"  Failure: {critique.failure}",
            f"  Argument: {critique.argument}",
        ]
        if critique.none_found:
            lines.append("  The prosecutor found no prior art.")
        for citation in critique.citations:
            source = citation.url or f"catalog work {citation.cited_work}"
            lines.append(f"  Evidence: {citation.title} <{source}>: {citation.relevance}")
        return lines

    def render(self) -> str:
        lines = [*self.block.lines(), ""]
        for critique in self.critiques:
            lines += [*self.critique_lines(critique), ""]
        roles = ", ".join(c.role_name.value for c in self.critiques)
        lines.append(
            f"Reply to each critique exactly once, by its critic role ({roles}), then choose the outcome. "
            "Leave statement, subject, behavior and rationale empty unless the outcome is revised. "
            "Answer with the JSON object only."
        )
        return "\n".join(lines)

    @property
    def roles(self) -> tuple[RoleName, ...]:
        return tuple(critique.role_name for critique in self.critiques)
