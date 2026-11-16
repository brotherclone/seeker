"""Debates copied from the parent run for the ideas a mutated generation carries forward."""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml
from pydantic import ConfigDict, Field

from seeker.ontology import Debate, DebateRun, Generation, MutationKind, SeekerModel


class CarryError(Exception):
    """A mutated generation's carried debates cannot be copied from its parent run."""


class ParentRunChanged(CarryError):
    def __init__(self, path: str) -> None:
        super().__init__(
            f"cannot carry debates: {path} no longer matches the parent run digest the generation recorded"
        )


class CarriedDebates(SeekerModel):
    """The parent's debates, renumbered to the positions their ideas hold in the mutated generation."""

    model_config = ConfigDict(title="CarriedDebates")

    debates: tuple[Debate, ...] = Field(default=(), description="In position order, each with carried_from set.")

    @classmethod
    def for_generation(cls, generation: Generation, root: Path) -> CarriedDebates:
        """Nothing for a drawn generation; for a mutated one, the parent's debates, checked against its digest."""
        origin = generation.mutation
        carried = [i for i in generation.ideas if i.lineage is not None and i.lineage.mutation_kind is MutationKind.CARRIED]
        if origin is None or not carried:
            return cls()
        path = Path(origin.parent_run_path)
        data = (path if path.is_absolute() else root / path).read_bytes()
        if hashlib.sha256(data).hexdigest() != origin.parent_run_digest:
            raise ParentRunChanged(origin.parent_run_path)
        parent = DebateRun.model_validate(yaml.safe_load(data.decode("utf-8")))
        debates = []
        for idea in carried:
            source = parent.debate_at(idea.lineage.parent_position)
            if source is None:
                raise CarryError(
                    f"cannot carry idea {idea.position}: the parent run has no debate at position "
                    f"{idea.lineage.parent_position}"
                )
            debates.append(
                source.model_copy(update={"position": idea.position, "carried_from": idea.lineage.parent_position})
            )
        return cls(debates=tuple(debates))

    @property
    def positions(self) -> frozenset[int]:
        return frozenset(debate.position for debate in self.debates)
