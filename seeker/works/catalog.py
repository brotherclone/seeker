"""Loading the vault's works folder into a validated ``WorkCatalog``.

Validation runs in two passes, like the decks: each note on its own, then the
set (cards against the deck set, duplicate ids). Every problem is collected
into a ``WorksReport`` so one run shows everything that needs fixing.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from pydantic import ConfigDict, Field, ValidationError
from pydantic_core import ErrorDetails

from seeker.ontology import DeckSet, SeekerModel, Sha256Digest, Work, WorkId
from seeker.works.note import Frontmatter, FrontmatterEntry, NoteFile, NoteFormatError

WORK_TYPE = "work"
_WIKILINK = re.compile(r"^\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]$")
LINKED_SLOTS = ("cards", "creators")


class Wikilink:
    """Obsidian wikilink helpers: ``[[target]]``, ``[[target|label]]``."""

    @staticmethod
    def target(value: str) -> str:
        """The link target when ``value`` is a wikilink, else ``value`` itself."""
        match = _WIKILINK.match(value.strip())
        return match.group(1).strip() if match else value.strip()

    @staticmethod
    def to(target: str) -> str:
        return f"[[{target}]]"


class WorkProblem(SeekerModel):
    """One problem found in the works folder, located by note, then slot, then
    the offending value."""

    model_config = ConfigDict(title="WorkProblem")

    note: Path = Field(description="The note, relative to the works folder.")
    slot: str | None = Field(default=None, description="The frontmatter property at fault.")
    value: str | None = Field(default=None, description="The offending value as written.")
    message: str = Field(description="What is wrong, in words a person can act on.")

    def __str__(self) -> str:
        location = [str(self.note)]
        if self.slot is not None:
            location.append(self.slot)
        if self.value is not None:
            location.append(repr(self.value))
        return f"{': '.join(location)}: {self.message}"


class WorkNote(SeekerModel):
    """A work together with the note it was read from."""

    model_config = ConfigDict(title="WorkNote")

    note: NoteFile = Field(description="The note on disk.")
    work: Work = Field(description="The validated work.")

    @property
    def searchable_text(self) -> str:
        """Title, summary and body: the text card suggestions search."""
        return "\n".join((self.work.title, self.work.summary or "", self.note.body))


class WorkCatalog(SeekerModel):
    """Every valid work in the vault, ordered by id."""

    model_config = ConfigDict(title="WorkCatalog")

    works: tuple[Work, ...] = Field(default=(), description="The works, ordered by WorkId.")

    @classmethod
    def of(cls, works: tuple[Work, ...]) -> WorkCatalog:
        return cls(works=tuple(sorted(works, key=lambda work: work.id)))

    def __len__(self) -> int:
        return len(self.works)

    def work(self, work_id: str) -> Work | None:
        return next((work for work in self.works if work.id == work_id), None)

    @property
    def digest(self) -> Sha256Digest:
        """SHA-256 over canonical JSON of the works in id order. Note formatting,
        key order and body text never change it."""
        payload = [work.model_dump(mode="json") for work in self.works]
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return Sha256Digest(hashlib.sha256(canonical.encode("utf-8")).hexdigest())


class WorksReport(SeekerModel):
    """The outcome of loading a works folder: every problem, the notes that
    loaded, and the catalog when there were no problems."""

    model_config = ConfigDict(title="WorksReport")

    folder: Path = Field(description="The works folder that was read.")
    problems: tuple[WorkProblem, ...] = Field(default=(), description="Every problem, in note order.")
    notes: tuple[WorkNote, ...] = Field(default=(), description="Every note that validated as a work.")

    @property
    def ok(self) -> bool:
        return not self.problems

    @property
    def catalog(self) -> WorkCatalog | None:
        return WorkCatalog.of(tuple(entry.work for entry in self.notes)) if self.ok else None


class WorksInvalid(Exception):
    """The works folder has problems; carries the full report."""

    def __init__(self, report: WorksReport) -> None:
        self.report = report
        super().__init__(f"{len(report.problems)} problem(s) in {report.folder}")


class WorkNotes(SeekerModel):
    """The works folder of a vault, read against a deck set."""

    model_config = ConfigDict(title="WorkNotes")

    folder: Path = Field(description="The works folder.")
    deck_set: DeckSet = Field(description="The cards work notes may link.")

    def note_paths(self) -> tuple[Path, ...]:
        if not self.folder.is_dir():
            return ()
        return tuple(
            sorted(
                path for path in self.folder.rglob("*.md")
                if not any(part.startswith(".") for part in path.relative_to(self.folder).parts)
            )
        )

    def load(self) -> WorksReport:
        problems: list[WorkProblem] = []
        loaded: list[WorkNote] = []
        for path in self.note_paths():
            entry, found = self._load_one(path)
            problems += found
            if entry is not None:
                loaded.append(entry)
        problems += self._set_problems(tuple(loaded))
        bad_notes = {problem.note for problem in problems}
        good = tuple(entry for entry in loaded if self._relative(entry.note.path) not in bad_notes)
        return WorksReport(folder=self.folder, problems=tuple(problems), notes=good)

    def catalog(self) -> WorkCatalog:
        """The catalog; raises WorksInvalid when any note has a problem."""
        report = self.load()
        if report.catalog is None:
            raise WorksInvalid(report)
        return report.catalog

    def _relative(self, path: Path) -> Path:
        return path.relative_to(self.folder)

    def _load_one(self, path: Path) -> tuple[WorkNote | None, list[WorkProblem]]:
        where = self._relative(path)
        try:
            note = NoteFile.read(path)
            frontmatter = note.frontmatter
        except (OSError, UnicodeDecodeError) as exc:
            return None, [WorkProblem(note=where, message=f"cannot read note ({exc})")]
        except NoteFormatError as exc:
            return None, [WorkProblem(note=where, message=str(exc))]
        if frontmatter.get("type") != WORK_TYPE:
            return None, []
        work_id = WorkId.from_note_name(path.stem)
        if work_id is None:
            return None, [WorkProblem(note=where, slot="id", value=path.stem, message="file name gives no usable id")]
        try:
            work = Work.model_validate({**self._normalized(frontmatter).to_yaml_source(), "id": str(work_id)})
        except ValidationError as exc:
            return None, [self._from_pydantic(where, error) for error in exc.errors()]
        return WorkNote(note=note, work=work), []

    @staticmethod
    def _normalized(frontmatter: Frontmatter) -> Frontmatter:
        """Work slots only, empty values dropped, wikilinks reduced to targets."""
        slots = set(Work.model_fields) - {"id"}
        entries: list[FrontmatterEntry] = []
        for entry in frontmatter.entries:
            if entry.key not in slots or entry.value in (None, "", [], ()):
                continue
            value = entry.value
            if entry.key in LINKED_SLOTS:
                items = value if isinstance(value, list) else [value]
                value = [Wikilink.target(item) if isinstance(item, str) else item for item in items if item not in (None, "")]
                if not value:
                    continue
            entries.append(FrontmatterEntry(key=entry.key, value=value))
        return Frontmatter(entries=tuple(entries))

    @staticmethod
    def _from_pydantic(where: Path, error: ErrorDetails) -> WorkProblem:
        location = error["loc"]
        slot = str(location[0]) if location else None
        value = error.get("input")
        shown = None if slot is None or isinstance(value, (dict, list)) else str(value)
        return WorkProblem(note=where, slot=slot, value=shown, message=error["msg"])

    def _set_problems(self, loaded: tuple[WorkNote, ...]) -> list[WorkProblem]:
        problems: list[WorkProblem] = []
        for entry in loaded:
            for card in entry.work.cards:
                if self.deck_set.card(card) is None:
                    problems.append(
                        WorkProblem(
                            note=self._relative(entry.note.path),
                            slot="cards",
                            value=str(card),
                            message="unknown card: not in the current decks",
                        )
                    )
        by_id: list[tuple[WorkId, Path]] = sorted((entry.work.id, self._relative(entry.note.path)) for entry in loaded)
        for index in range(1, len(by_id)):
            (previous_id, previous), (work_id, note) = by_id[index - 1], by_id[index]
            if work_id == previous_id:
                problems.append(
                    WorkProblem(
                        note=note,
                        slot="id",
                        value=str(work_id),
                        message=f"duplicate work id: {previous} reduces to the same id",
                    )
                )
        return problems
