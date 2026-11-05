"""Pydantic models mirroring the Seeker LinkML schema (schema/seeker.yaml).

The schema is the source of truth; tests/test_conformance.py fails if these
models and the schema drift apart. Change the schema first.
"""

from seeker.ontology.base import DescribedStrEnum, LinkMLString, SeekerModel
from seeker.ontology.card import Card
from seeker.ontology.deck import Deck
from seeker.ontology.deck_set import DeckSet, SharedCardId
from seeker.ontology.draw import Draw, DrawBatch
from seeker.ontology.fields import CreativeField
from seeker.ontology.generation import CardReading, Generation, GenerationFailure, Idea, Usage
from seeker.ontology.reading import Effort, Reading, RoleName
from seeker.ontology.role import ReadingGuidance, Role
from seeker.ontology.types import AxisId, CardId, GitCommit, ModelId, Sha256Digest, Synonym, Tag, Url, WorkId
from seeker.ontology.work import CaptureSource, Work, WorkKind

__all__ = [
    "AxisId",
    "CaptureSource",
    "Card",
    "CardId",
    "CardReading",
    "CreativeField",
    "Deck",
    "DeckSet",
    "DescribedStrEnum",
    "Draw",
    "DrawBatch",
    "Effort",
    "Generation",
    "GenerationFailure",
    "GitCommit",
    "Idea",
    "LinkMLString",
    "ModelId",
    "Reading",
    "ReadingGuidance",
    "Role",
    "RoleName",
    "SeekerModel",
    "Sha256Digest",
    "SharedCardId",
    "Synonym",
    "Tag",
    "Url",
    "Usage",
    "Work",
    "WorkId",
    "WorkKind",
]
