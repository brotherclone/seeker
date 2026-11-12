"""The offline prior-art check: which captured works already combine a draw's cards.

Pure set work over the catalog. A work sharing two of a draw's three cards is
a partial precedent; one sharing all three is a full one. The debate's
prosecutor reads this before spending anything on web search.
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import ConfigDict, Field

from seeker.ontology import CardId, Draw, DrawBatch, SeekerModel, Sha256Digest, Work, WorkId
from seeker.works.catalog import WorkCatalog


class PriorArtHit(SeekerModel):
    """A work that links at least two of a draw's cards."""

    model_config = ConfigDict(title="PriorArtHit")

    MINIMUM_SHARED: ClassVar[int] = 2

    work_id: WorkId = Field(description="The work.")
    title: str = Field(description="The work's title, for reports.")
    shared: tuple[CardId, ...] = Field(min_length=2, description="The draw's cards the work links, in draw order.")
    full: bool = Field(description="True when the work links every card in the draw.")

    @classmethod
    def between(cls, work: Work, draw: Draw) -> PriorArtHit | None:
        shared = work.shared_cards(draw.drawn_cards)
        if len(shared) < cls.MINIMUM_SHARED:
            return None
        return cls(work_id=work.id, title=work.title, shared=shared, full=len(shared) == len(draw.drawn_cards))

    @property
    def sort_key(self) -> tuple[int, str]:
        return (-len(self.shared), str(self.work_id))


class DrawPriorArt(SeekerModel):
    """The prior art for one draw, most-overlapping works first."""

    model_config = ConfigDict(title="DrawPriorArt")

    draw: Draw = Field(description="The draw checked.")
    hits: tuple[PriorArtHit, ...] = Field(default=(), description="By shared count descending, then work id.")

    @classmethod
    def of(cls, catalog: WorkCatalog, draw: Draw) -> DrawPriorArt:
        hits = (hit for work in catalog.works if (hit := PriorArtHit.between(work, draw)) is not None)
        return cls(draw=draw, hits=tuple(sorted(hits, key=lambda hit: hit.sort_key)))

    @property
    def has_full_hit(self) -> bool:
        return any(hit.full for hit in self.hits)


class BatchCheck(SeekerModel):
    """A whole batch checked against the catalog, every draw reported."""

    model_config = ConfigDict(title="BatchCheck")

    catalog_digest: Sha256Digest = Field(description="The catalog the check saw.")
    work_count: int = Field(ge=0, description="How many works the catalog held.")
    draws: tuple[DrawPriorArt, ...] = Field(description="One entry per draw, in position order.")

    @classmethod
    def run(cls, catalog: WorkCatalog, batch: DrawBatch) -> BatchCheck:
        return cls(
            catalog_digest=catalog.digest,
            work_count=len(catalog),
            draws=tuple(DrawPriorArt.of(catalog, draw) for draw in batch.draws),
        )

    @property
    def draws_with_prior_art(self) -> int:
        return sum(1 for entry in self.draws if entry.hits)
