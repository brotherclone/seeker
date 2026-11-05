"""Obsidian notes as Seeker reads and writes them.

A note is optional YAML frontmatter between ``---`` lines, then a free-form
body. Seeker never owns a whole note: it changes individual top-level
frontmatter keys and named managed blocks in the body, and leaves every other
byte as Gabe wrote it. Edits are surgical: changing a key rewrites only that
key's lines, so other keys keep their formatting, quoting and comments.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

import yaml
from pydantic import ConfigDict, Field

from seeker.ontology import SeekerModel

FENCE = "---"
_TOP_LEVEL_KEY = re.compile(r"^[^\s#-]")


class NoteFormatError(Exception):
    """A note's frontmatter is not a YAML mapping Seeker can read."""


class FrontmatterEntry(SeekerModel):
    """One top-level frontmatter key and its parsed YAML value."""

    model_config = ConfigDict(title="FrontmatterEntry", str_strip_whitespace=False)

    key: str = Field(description="The property name.")
    value: object = Field(default=None, description="The parsed YAML value, as written.")


class Frontmatter(SeekerModel):
    """A note's frontmatter: its entries in written order."""

    model_config = ConfigDict(title="Frontmatter")

    entries: tuple[FrontmatterEntry, ...] = Field(default=(), description="Entries in written order.")

    @classmethod
    def parse(cls, text: str) -> Frontmatter:
        try:
            raw = yaml.safe_load(text) if text.strip() else None
        except yaml.YAMLError as exc:
            raise NoteFormatError(f"frontmatter is not valid YAML: {' '.join(str(exc).split())}") from exc
        if raw is None:
            return cls()
        if not isinstance(raw, dict):
            raise NoteFormatError("frontmatter is not a mapping of properties")
        return cls(entries=tuple(FrontmatterEntry(key=str(key), value=value) for key, value in raw.items()))

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(entry.key for entry in self.entries)

    def has(self, key: str) -> bool:
        return key in self.keys

    def get(self, key: str) -> object:
        """The value under ``key``, or None when absent."""
        return next((entry.value for entry in self.entries if entry.key == key), None)

    def to_yaml_source(self) -> object:
        """The entries as the plain mapping YAML and Pydantic validation expect."""
        return {entry.key: entry.value for entry in self.entries}


class ManagedBlock(SeekerModel):
    """A region of a note body that Seeker rewrites wholesale, between
    ``<!-- seeker:NAME -->`` and ``<!-- /seeker:NAME -->``."""

    model_config = ConfigDict(title="ManagedBlock")

    name: str = Field(pattern="^[a-z][a-z0-9-]*$", description="The block's name, e.g. card.")

    @property
    def opening(self) -> str:
        return f"<!-- seeker:{self.name} -->"

    @property
    def closing(self) -> str:
        return f"<!-- /seeker:{self.name} -->"

    def render(self, content: str) -> str:
        return f"{self.opening}\n{content.strip(chr(10))}\n{self.closing}"

    def apply(self, body: str, content: str) -> str:
        """``body`` with this block's content replaced, or the block inserted at
        the top when the body has none."""
        block = self.render(content)
        start = body.find(self.opening)
        end = body.find(self.closing, start + len(self.opening)) if start >= 0 else -1
        if start >= 0 and end >= 0:
            return body[:start] + block + body[end + len(self.closing):]
        rest = body.lstrip("\n")
        return f"\n{block}\n" + (f"\n{rest}" if rest else "")


class NoteFile(SeekerModel):
    """One Markdown note: where it lives, its frontmatter source text, its body,
    and what is on disk now, so a save happens only when something changed."""

    model_config = ConfigDict(title="NoteFile", str_strip_whitespace=False)

    path: Path = Field(description="The note's file.")
    frontmatter_text: str | None = Field(
        default=None, description="The YAML between the fences, verbatim; None when the note has no frontmatter."
    )
    body: str = Field(default="", description="Everything after the frontmatter, verbatim.")
    on_disk: str | None = Field(default=None, description="The file's text when read; None for a new note.")

    @classmethod
    def read(cls, path: Path) -> NoteFile:
        text = path.read_text(encoding="utf-8")
        frontmatter_text, body = cls._split(text)
        return cls(path=path, frontmatter_text=frontmatter_text, body=body, on_disk=text)

    @classmethod
    def new(cls, path: Path) -> NoteFile:
        return cls(path=path)

    @classmethod
    def read_or_new(cls, path: Path) -> NoteFile:
        return cls.read(path) if path.is_file() else cls.new(path)

    @staticmethod
    def _split(text: str) -> tuple[str | None, str]:
        lines = text.splitlines(keepends=True)
        if not lines or lines[0].rstrip("\r\n") != FENCE:
            return None, text
        for index in range(1, len(lines)):
            if lines[index].rstrip("\r\n") == FENCE:
                return "".join(lines[1:index]), "".join(lines[index + 1:])
        return None, text

    @property
    def stem(self) -> str:
        return self.path.stem

    @property
    def has_frontmatter(self) -> bool:
        return self.frontmatter_text is not None

    @property
    def frontmatter(self) -> Frontmatter:
        """The parsed frontmatter; raises NoteFormatError when it is not a mapping."""
        return Frontmatter.parse(self.frontmatter_text or "")

    @property
    def text(self) -> str:
        if self.frontmatter_text is None:
            return self.body
        return f"{FENCE}\n{self.frontmatter_text}{FENCE}\n{self.body}"

    @property
    def changed(self) -> bool:
        return self.text != self.on_disk

    def with_value(self, key: str, value: object) -> NoteFile:
        """This note with ``key`` set to ``value``. Only that key's lines change;
        a missing key is appended after the existing ones."""
        if self.frontmatter.get(key) == value and self.frontmatter.has(key):
            return self
        rendered = yaml.safe_dump({key: value}, sort_keys=False, allow_unicode=True, default_flow_style=False)
        blocks = self._key_blocks()
        for index, (block_key, _) in enumerate(blocks):
            if block_key == key:
                blocks[index] = (key, rendered)
                break
        else:
            blocks.append((key, rendered))
        return self.model_copy(update={"frontmatter_text": "".join(text for _, text in blocks)})

    def with_values(self, entries: tuple[FrontmatterEntry, ...]) -> NoteFile:
        note = self
        for entry in entries:
            note = note.with_value(entry.key, entry.value)
        return note

    def with_block(self, block: ManagedBlock, content: str) -> NoteFile:
        return self.model_copy(update={"body": block.apply(self.body, content)})

    def _key_blocks(self) -> list[tuple[str | None, str]]:
        """The frontmatter text split into top-level key blocks, in order. Lines
        before the first key (comments, blank lines) form a keyless block."""
        blocks: list[tuple[str | None, str]] = []
        for line in (self.frontmatter_text or "").splitlines(keepends=True):
            if _TOP_LEVEL_KEY.match(line):
                blocks.append((self._key_of(line), line))
            elif blocks:
                key, text = blocks[-1]
                blocks[-1] = (key, text + line)
            else:
                blocks.append((None, line))
        if blocks and not blocks[-1][1].endswith("\n"):
            key, text = blocks[-1]
            blocks[-1] = (key, text + "\n")
        return blocks

    @staticmethod
    def _key_of(line: str) -> str | None:
        head = line.split(":", 1)[0] if ":" in line else line
        try:
            parsed = yaml.safe_load(head)
        except yaml.YAMLError:
            return None
        return None if parsed is None else str(parsed)

    def save(self) -> bool:
        """Write the note atomically if it changed. Returns True when written."""
        if not self.changed:
            return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle, temp = tempfile.mkstemp(dir=self.path.parent, prefix=f".{self.path.name}.", suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8", newline="") as stream:
                stream.write(self.text)
            os.replace(temp, self.path)
        except BaseException:
            Path(temp).unlink(missing_ok=True)
            raise
        return True
