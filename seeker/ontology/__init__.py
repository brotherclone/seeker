"""Pydantic models mirroring the Seeker LinkML schema (schema/seeker.yaml).

The schema is the source of truth; tests/test_conformance.py fails if these
models and the schema drift apart. Change the schema first.
"""

from seeker.ontology.base import DescribedStrEnum, LinkMLString, SeekerModel
from seeker.ontology.card import Card
from seeker.ontology.debate import (
    Citation,
    Critique,
    CritiqueTarget,
    Debate,
    DebateFailure,
    Defense,
    DefenseMove,
    DefenseOutcome,
    IdeaRevision,
    Reply,
    Severity,
)
from seeker.ontology.deck import Deck
from seeker.ontology.deck_set import DeckSet, SharedCardId
from seeker.ontology.draw import Draw, DrawBatch
from seeker.ontology.fields import CreativeField
from seeker.ontology.generation import CardReading, Generation, GenerationFailure, Idea, Usage
from seeker.ontology.reading import Effort, Reading, RoleName
from seeker.ontology.role import ReadingGuidance, Role
from seeker.ontology.run import DebateRun, RoleDigest, StopReason
from seeker.ontology.tournament import AxisVerdict, Comparison, Rating, ScoreAxis, Tournament
from seeker.ontology.types import AxisId, CardId, GitCommit, ModelId, Sha256Digest, Synonym, Tag, Url, WorkId
from seeker.ontology.work import CaptureSource, Work, WorkKind

__all__ = [
    "AxisId",
    "AxisVerdict",
    "CaptureSource",
    "Card",
    "CardId",
    "CardReading",
    "Citation",
    "Comparison",
    "CreativeField",
    "Critique",
    "CritiqueTarget",
    "Debate",
    "DebateFailure",
    "DebateRun",
    "Deck",
    "DeckSet",
    "Defense",
    "DefenseMove",
    "DefenseOutcome",
    "DescribedStrEnum",
    "Draw",
    "DrawBatch",
    "Effort",
    "Generation",
    "GenerationFailure",
    "GitCommit",
    "Idea",
    "IdeaRevision",
    "LinkMLString",
    "ModelId",
    "Rating",
    "Reading",
    "ReadingGuidance",
    "Reply",
    "Role",
    "RoleDigest",
    "RoleName",
    "ScoreAxis",
    "SeekerModel",
    "Severity",
    "Sha256Digest",
    "SharedCardId",
    "StopReason",
    "Synonym",
    "Tag",
    "Tournament",
    "Url",
    "Usage",
    "Work",
    "WorkId",
    "WorkKind",
]
