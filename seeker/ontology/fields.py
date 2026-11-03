"""The ``CreativeField`` enum from schema/seeker.yaml."""

from __future__ import annotations

from enum import StrEnum


class CreativeField(StrEnum):
    """The creative fields Seeker draws ideas from. A card belongs to every field
    it lists; a card listing none is cross-cutting and applies to all fields.
    Cards spanning several fields are the bridges between literatures that
    literature-based discovery looks for."""

    description: str

    def __new__(cls, value: str, description: str) -> CreativeField:
        member = str.__new__(cls, value)
        member._value_ = value
        member.description = description
        return member

    MUSIC = "music", "Composition, performance, sound design, synthesis and audio production."
    VISUAL_ART = (
        "visual-art",
        "Drawing, painting, printmaking, generative and computational visual art, installation.",
    )
    FILM = "film", "Film, video, animation and moving-image work of any length or format."
    ELECTRONICS = (
        "electronics",
        "Sensors, circuits, microcontrollers, displays and physical computing.",
    )
    WRITING = "writing", "Creative writing, poetry, interactive and procedural text, audio drama."
    COMICS = "comics", "Comics, sequential art, strips, webcomics and minicomics."
    GAMES = "games", "Board, card, tabletop role-playing and electronic games."
