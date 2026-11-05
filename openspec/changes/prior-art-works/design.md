# Design

## Context

- The ontology, its conformance test, and the tooling-model pattern (models that declare no `class_uri`) are established. `DeckSet` gives card lookup, and `Card.matches` already compares names and synonyms case-insensitively.
- `seeker.yaml` has `paths.vault: null`. On Gabe's Mac the vault is `~/Documents/Claude/Projects/Bracers/Projects`, which already holds `Seeker/` notes (the hub, `Ontology/`, `Decisions/`, `Notes/`).
- The Obsidian Web Clipper imports templates as JSON:
  - `schemaVersion`, `name`, `behavior: create`;
  - `noteNameFormat`, `path`, `noteContentFormat`;
  - `properties`: a list of `{name, value, type}`, where the type is one of `text`, `multitext`, `number`, `checkbox`, `date` or `datetime`;
  - `triggers`.

  Its AI interpreter uses `{{"prompt"}}` variables. Users report these work in the note body but not reliably inside properties.
- Motivation is in proposal.md; requirements are in `specs/prior-art-works/spec.md`.

## Goals / Non-Goals

**Goals:**
- Capture takes no extra work for Gabe: one Web Clipper click, with the card links filled in by Seeker afterwards.
- Seeker never damages a note. It owns specific frontmatter keys and one marked block, and leaves everything else alone.
- Make `check` fast and deterministic, so the prosecutor can rely on it before spending on web search.

**Non-Goals:**
- The prosecutor itself.
- Web search.
- Embeddings or fuzzy matching.
- A custom extension.
- Creator notes as a class.
- Exporters.
- Syncing the vault anywhere.

## Decisions

### 1. Ontology

```yaml
types:
  WorkId: {typeof: string, pattern: "^[a-z0-9]+(-[a-z0-9]+)*$"}   # from the note's file name

enums:
  WorkKind:      {piece, recording, instrument, software, game, publication, performance, installation, paper, product, other}
  CaptureSource: {gabe, prosecutor, import}

slots (new): title (string, required), creators (string*), year (integer, optional),
             url (uri, optional), kind (WorkKind, required), summary (string, optional),
             captured_by (CaptureSource, required), captured_on (date, required)

classes:
  Work:
    slots: [id, title, creators, year, url, kind, fields, cards, summary, captured_by, captured_on]
    slot_usage:
      id:    {range: WorkId}
      cards: {range: Card, inlined: false, required: false, minimum_cardinality: 0}
```

- **Reuse through `slot_usage`.** `id`, `fields` and `cards` are reused, so a work's `cards` and a deck's `cards` mean the same thing, cards, with the usage deciding whether they're inlined.
  - The conformance test already reads induced slots, so it checks the usage version.
  - If the LinkML toolchain rejects overriding `minimum_cardinality`, the fallback is a dedicated `linked_cards` slot. That changes only the frontmatter key, and the decision note would record it.
- **Creators are plain strings**, written as wikilinks in notes (`[[Daphne Oram]]`), so people show up in the graph without a `Creator` class yet. Brackets are removed on read.
- **The conformance test gains `date` → `datetime.date` and `uri` → a `Url` named type,** a pattern-checked string. The style rules say domain scalars must be named types.

### 2. Notes are the source of truth, and Seeker owns only what it writes

- **Format.** A work note is YAML frontmatter between `---` lines, then the body.
  - `NoteFile` parses and writes notes, keeping unknown frontmatter keys and their order.
  - It writes with `yaml.safe_dump(sort_keys=False, allow_unicode=True)`, and only when something changed.
  - Every write is atomic (a temp file, then `os.replace`).
- **Reading a `Work`:**
  - wikilinks become ids: `[[x]]` and `[[x|label]]` become `x`;
  - `type` and unknown keys are dropped;
  - `id` is derived from the file name: lowercase, with runs of anything outside `[a-z0-9]` collapsed to `-`;
  - the result is validated as a `Work`.
- **Validation is two passes**, like the decks: each note is validated on its own, then the set is checked (unknown cards against the `DeckSet`, duplicate ids). Everything goes into a `WorksReport` made of `WorkProblem`s.
- **Card notes:**
  - Seeker owns the frontmatter keys `type`, `card_id`, `axis`, `fields`, `tags` and `aliases`, and the body between `<!-- seeker:card -->` and `<!-- /seeker:card -->`.
  - Everything else is Gabe's.
  - A missing block is inserted at the top of the body. A note with no frontmatter gets some.
  - `aliases` holds the name plus the synonyms, so `[[microsound]]` and `[[Granular synthesis]]` both resolve to `granular-synthesis.md`.

### 3. Suggesting card links

- `CardMatcher` builds one case-insensitive whole-word regex per card from its name and synonyms. "Whole word" uses boundaries that allow hyphens and spaces inside a term ("Karplus-Strong", "drawn sound").
- It searches the title, summary and body, and skips cards the work already links.
- **Guard against false positives:** single-word terms of three characters or fewer (like `CA` and `FDN`) only match in their exact case. The suggestion list is still shown to Gabe before `--apply`.
- `--apply` adds wikilinks to `cards` through `NoteFile`, which preserves the note.

### 4. The prior-art check

- `WorkCatalog.overlaps(draw)` gives each work's shared cards: the intersection of the draw's `drawn_cards` and the work's `cards`. Works sharing at least 2 cards come back as `PriorArtHit` (work id, title, shared cards, `full = len == 3`), sorted by shared count descending, then id.
- `BatchCheck` produces one `DrawPriorArt` per draw.
- This is pure set work: hundreds of works times 12 draws is instantaneous.

### 5. The catalog digest

SHA-256 over canonical JSON of the `Work` models sorted by id, matching the deck digest. Body text isn't part of `Work` (only `summary` is), so editing the body leaves the digest unchanged.

### 6. Config

```yaml
paths:
  vault: ~/Documents/Claude/Projects/Bracers/Projects     # set in Gabe's local seeker.yaml
vault_folders:
  works: Seeker/Works
  cards: Seeker/Cards
```

- `vault_folders` is optional, and defaults to the values above.
- `SeekerConfig.vault()` returns a `VaultLayout`, a model with `root`, `works` and `cards`, or raises `VaultNotConfigured`.
- The repo's `seeker.yaml` keeps `vault: null` with a comment. Gabe sets his own path locally: a personal absolute path doesn't belong in the shared default.

### 7. The capture template

`capture/seeker-work.clipper.json`:

```json
{
  "schemaVersion": "0.1.0",
  "name": "Seeker work",
  "behavior": "create",
  "noteNameFormat": "{{title|safe_name}}",
  "path": "Seeker/Works",
  "properties": [
    {"name": "type",        "value": "work",                         "type": "text"},
    {"name": "title",       "value": "{{title}}",                    "type": "text"},
    {"name": "creators",    "value": "{{author|wikilink}}",          "type": "multitext"},
    {"name": "year",        "value": "{{published|date:\"YYYY\"}}",  "type": "number"},
    {"name": "url",         "value": "{{url}}",                      "type": "text"},
    {"name": "kind",        "value": "other",                        "type": "text"},
    {"name": "fields",      "value": "",                             "type": "multitext"},
    {"name": "cards",       "value": "",                             "type": "multitext"},
    {"name": "summary",     "value": "{{description}}",              "type": "text"},
    {"name": "captured_by", "value": "gabe",                         "type": "text"},
    {"name": "captured_on", "value": "{{date|date:\"YYYY-MM-DD\"}}", "type": "date"}
  ],
  "noteContentFormat": "{{selection}}\n\n{{\"In 3 sentences: what this work is, how it was made, and what techniques, media or historical machines it uses.\"}}"
}
```

- The interpreter prompt sits in the **body**, which is reliable. That gives `suggest` more text to match cards against.
- If `published` is missing, `year` comes out empty, and the reader treats an empty value as absent.
- A test checks that every property name is `type` or a `Work` slot, and that `path` equals the default works folder.
- Importing the template and clipping a real page is a manual check for Gabe, recorded in the tasks, because it needs a browser.

### 7a. Code layout

`seeker/works/`:
- `note.py`: `NoteFile`;
- `catalog.py`: `WorkNotes`, `WorkCatalog`, `WorksReport`;
- `cards_sync.py`: `CardNotes`;
- `matcher.py`: `CardMatcher`;
- `check.py`: `BatchCheck`, `PriorArtHit`, `DrawPriorArt`;
- `cli.py`: the `seeker-works` command.

Ontology models go in `seeker/ontology/work.py`.

### 8. Obsidian

- A concept note: `Seeker/Ontology/Work.md`.
- A decision note: `2026-11-05 Works in the vault`.
- A hub update.

The generated `Seeker/Cards/` notes become graph nodes in their own right. Card notes, work notes and the ontology notes then form one connected graph.

## Risks / Trade-offs

- [Writing into a hand-edited vault could damage notes] → Seeker owns only named keys and one marked block. Writes are atomic and only happen on change, sync never deletes, and tests cover round-tripping personal content.
- [YAML round-trips can reformat frontmatter Gabe wrote by hand] → Only `suggest --apply` and `sync-cards` rewrite frontmatter, and only on notes they're changing. Key order is kept. Comments in frontmatter are rare in Obsidian and may be lost, which the docs say.
- [Matching on short synonyms gives false positives] → An exact-case rule for short single words, and a review before `--apply`.
- [The Web Clipper's variables and filters may differ by version] → The template uses only the basic, documented variables. The manual check catches the rest, and the template is plain JSON that's easy to tweak.
- [A vault on iCloud or synced elsewhere may show files mid-sync] → Reads tolerate unparseable notes by reporting them, never crashing.

## Open Questions

- Should captures of the same URL be detected as duplicates? This can be added to `validate` as a warning later, and it doesn't change the specs.
