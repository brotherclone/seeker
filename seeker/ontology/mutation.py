"""The mutation classes from schema/seeker.yaml: ``Lineage`` and
``MutationOrigin``, and the ``MutationKind`` enum."""

from __future__ import annotations

from pydantic import ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

from seeker.ontology.base import DescribedStrEnum, SeekerModel
from seeker.ontology.types import AxisId, CardId, Sha256Digest


class MutationKind(DescribedStrEnum):
    """How an idea in a mutated generation relates to its parent."""

    REWORKING = (
        "reworking",
        "The parent's three cards, rewritten into a different idea after reading the parent's debate.",
    )
    CARD_SWAP = (
        "card_swap",
        "The parent's draw with one non-constraint card replaced by a seeded card from the same deck.",
    )
    CARRIED = "carried", "The parent itself, carried into the next round with its debate."


class Lineage(SeekerModel):
    """Where an idea in a mutated generation came from: its parent in the
    parent debate run, and how it was made from it."""

    model_config = ConfigDict(title="Lineage", json_schema_extra={"class_uri": "seeker:Lineage"})

    parent_position: int = Field(
        title="parent_position",
        ge=1,
        description="The parent idea's position in the parent debate run.",
        examples=[10],
        json_schema_extra={"slot_uri": "seeker:parentPosition"},
    )
    mutation_kind: MutationKind = Field(
        title="mutation_kind",
        description="How the idea was made from its parent.",
        examples=["card_swap"],
        json_schema_extra={"slot_uri": "seeker:mutationKind"},
    )
    swapped_axis: AxisId | None = Field(
        default=None,
        title="swapped_axis",
        description="For a card swap, the axis whose card was replaced.",
        examples=["medium"],
        json_schema_extra={"slot_uri": "seeker:swappedAxis"},
    )
    replaced_card: CardId | None = Field(
        default=None,
        title="replaced_card",
        description="For a card swap, the parent's card that was replaced, referenced by card id.",
        examples=["camera-obscura"],
        json_schema_extra={"slot_uri": "seeker:replacedCard"},
    )

    @model_validator(mode="after")
    def _swap_names_its_card(self) -> Lineage:
        is_swap = self.mutation_kind is MutationKind.CARD_SWAP
        named = (self.swapped_axis is not None, self.replaced_card is not None)
        if is_swap and named != (True, True):
            raise PydanticCustomError("swap", "a card swap names its swapped axis and replaced card")
        if not is_swap and any(named):
            raise PydanticCustomError("swap", "only a card swap names a swapped axis or replaced card")
        return self


class MutationOrigin(SeekerModel):
    """The debate run a mutated generation was bred from, pinned by path and
    digest, with the seed its card swaps came from and its round number."""

    model_config = ConfigDict(title="MutationOrigin", json_schema_extra={"class_uri": "seeker:MutationOrigin"})

    parent_run_path: str = Field(
        title="parent_run_path",
        min_length=1,
        description="The parent debate run, relative to the repository root when inside it.",
        examples=["debates/2026-11-14-round-1-literal.yaml"],
        json_schema_extra={"slot_uri": "seeker:parentRunPath"},
    )
    parent_run_digest: Sha256Digest = Field(
        title="parent_run_digest",
        description=(
            "SHA-256 of the parent run's bytes, so a changed parent is caught on resume and when "
            "its debates are carried."
        ),
        examples=[Sha256Digest.EXAMPLES[0]],
        json_schema_extra={"slot_uri": "seeker:parentRunDigest"},
    )
    mutation_seed: int = Field(
        title="mutation_seed",
        ge=0,
        description="The integer the card swaps are drawn from.",
        examples=[7],
        json_schema_extra={"slot_uri": "seeker:mutationSeed"},
    )
    round: int = Field(
        title="round",
        ge=2,
        description=(
            "Which round of the loop this generation is. A generation drawn from a batch is round 1; "
            "each mutation adds one."
        ),
        examples=[2],
        json_schema_extra={"slot_uri": "seeker:round"},
    )
