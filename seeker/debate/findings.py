"""Caching the prosecutor's web finds as Work notes, so later checks see them offline."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import ClassVar
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import ConfigDict, Field

from seeker.ontology import CaptureSource, Citation, Critique, SeekerModel, WorkId, WorkKind
from seeker.works.catalog import WorkCatalog, WorkNotes
from seeker.works.note import FrontmatterEntry, NoteFile


class NormalUrl:
    """A URL reduced for comparison: lowercase scheme and host, no trailing slash,
    no fragment and no ``utm_*`` tracking parameters."""

    def __init__(self, url: str) -> None:
        parts = urlsplit(url.strip())
        query = urlencode([(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not k.lower().startswith("utm_")])
        path = parts.path.rstrip("/")
        self.value = urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, query, ""))

    def __eq__(self, other: object) -> bool:
        return isinstance(other, NormalUrl) and other.value == self.value

    def __hash__(self) -> int:
        return hash(self.value)


class NoteName:
    """A file name for a new work note: the title with characters files and
    wikilinks cannot hold removed, suffixed `` (2)``, `` (3)``... when taken."""

    UNSAFE: ClassVar[re.Pattern[str]] = re.compile(r'[\\/:*?"<>|\[\]#^]+')
    MAX_LENGTH: ClassVar[int] = 120

    def __init__(self, title: str) -> None:
        cleaned = " ".join(self.UNSAFE.sub(" ", title).split()).strip(" .")
        self.stem = cleaned[: self.MAX_LENGTH].rstrip(" .") or "Untitled work"

    def free_path(self, folder: Path, taken_ids: frozenset[str]) -> Path:
        for attempt in range(1, 1000):
            stem = self.stem if attempt == 1 else f"{self.stem} ({attempt})"
            path = folder / f"{stem}.md"
            if not path.exists() and str(WorkId.from_note_name(stem)) not in taken_ids:
                return path
        raise FileExistsError(f"no free note name for {self.stem!r} in {folder}")


class UrlIndex:
    """Which captured work, if any, already has a URL, compared as normal URLs."""

    def __init__(self, catalog: WorkCatalog) -> None:
        self._entries: list[tuple[NormalUrl, WorkId]] = [
            (NormalUrl(str(work.url)), work.id) for work in catalog.works if work.url is not None
        ]

    def work_for(self, url: str) -> WorkId | None:
        key = NormalUrl(url)
        return next((work_id for known, work_id in self._entries if known == key), None)

    def add(self, url: str, work_id: WorkId) -> None:
        self._entries.append((NormalUrl(url), work_id))


class CapturedWork(SeekerModel):
    """One new work note written for a citation."""

    model_config = ConfigDict(title="CapturedWork")

    path: Path = Field(description="The note written.")
    work_id: WorkId = Field(description="The id the note gives the work.")
    url: str = Field(description="The cited URL.")


class ProsecutorFindings(SeekerModel):
    """What one prosecution added to the vault, and the critique with its known URLs pointed at works."""

    model_config = ConfigDict(title="ProsecutorFindings")

    critique: Critique = Field(description="The prosecution, with citations of already-captured URLs rewritten to work ids.")
    captured: tuple[CapturedWork, ...] = Field(default=(), description="New notes written, in citation order.")

    @classmethod
    def capture(cls, critique: Critique, works: WorkNotes, today: date) -> ProsecutorFindings:
        """Write a note for every cited URL the catalog does not have. Existing notes are never touched."""
        catalog = works.catalog()
        known = UrlIndex(catalog)
        taken = frozenset(str(work.id) for work in catalog.works)
        citations: list[Citation] = []
        captured: list[CapturedWork] = []
        for citation in critique.citations:
            if citation.url is None:
                citations.append(citation)
                continue
            existing = known.work_for(str(citation.url))
            if existing is not None:
                citations.append(
                    Citation(
                        title=citation.title,
                        cited_work=existing,
                        relevance=citation.relevance,
                        embodied_cards=citation.embodied_cards,
                    )
                )
                continue
            path = NoteName(citation.title).free_path(works.folder, taken)
            cls._note(path, citation, today).save()
            work_id = WorkId.from_note_name(path.stem)
            captured.append(CapturedWork(path=path, work_id=work_id, url=str(citation.url)))
            known.add(str(citation.url), work_id)
            taken = taken | {str(work_id)}
            citations.append(citation)
        rewritten = Critique.model_validate({**critique.model_dump(), "citations": [c.model_dump() for c in citations]})
        return cls(critique=rewritten, captured=tuple(captured))

    @staticmethod
    def _note(path: Path, citation: Citation, today: date) -> NoteFile:
        entries = (
            FrontmatterEntry(key="type", value="work"),
            FrontmatterEntry(key="title", value=citation.title),
            FrontmatterEntry(key="url", value=str(citation.url)),
            FrontmatterEntry(key="kind", value=WorkKind.OTHER.value),
            FrontmatterEntry(key="cards", value=[f"[[{card}]]" for card in citation.embodied_cards]),
            FrontmatterEntry(key="summary", value=citation.relevance),
            FrontmatterEntry(key="captured_by", value=CaptureSource.PROSECUTOR.value),
            FrontmatterEntry(key="captured_on", value=today),
        )
        return NoteFile.new(path).with_values(entries)
