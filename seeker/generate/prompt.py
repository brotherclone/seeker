"""What the generator sees: the system block for a reading, and one draw's cards."""

from __future__ import annotations

from seeker.ontology import Card, DeckSet, Draw, Reading, Role



class SystemPrompt:
    """The persona, the role's rules, and the guidance for one reading only.

    It is identical for every draw in a generation, which is what makes it cacheable.
    """

    def __init__(self, role: Role, reading: Reading) -> None:
        self.role = role
        self.reading = reading

    def render(self) -> str:
        return (
            f"{self.role.persona.strip()}\n\n"
            f"{self.role.system_prompt.strip()}\n\n"
            f"Reading: {self.reading.value}. {self.role.guidance_for(self.reading).strip()}"
        )


class DrawPrompt:
    """One draw, presented the way a person reading the decks would see it."""

    def __init__(self, draw: Draw, deck_set: DeckSet) -> None:
        self.draw = draw
        self.deck_set = deck_set

    def cards(self) -> tuple[Card, ...]:
        return tuple(self._card(card_id) for card_id in self.draw.drawn_cards)

    def _card(self, card_id: str) -> Card:
        card = self.deck_set.card(card_id)
        if card is None:
            raise KeyError(f"draw {self.draw.position} names card {card_id!r}, which is not in the decks")
        return card

    def card_lines(self) -> list[str]:
        """The home field and every card with its synonyms, fields and note."""
        lines = [f"Home field: {self.draw.home_field.value}", "", "Cards:"]
        for index, (axis, card) in enumerate(zip(self.draw.axes, self.cards()), start=1):
            lines.append(f"{index}. {axis}: {card.name}  (id: {card.id})")
            if card.synonyms:
                lines.append(f"   also known as: {', '.join(card.synonyms)}")
            fields = ", ".join(field.value for field in card.fields) or "any (cross-cutting)"
            lines.append(f"   fields: {fields}")
            if card.note:
                lines.append(f"   note: {card.note}")
        return lines

    def render(self) -> str:
        lines = self.card_lines()
        order = ", ".join(self.draw.drawn_cards)
        lines += [
            "",
            "Collide these three cards into one idea and answer with the JSON object only. "
            f"Give exactly one card reading per card, in this order of ids: {order}.",
        ]
        return "\n".join(lines)
