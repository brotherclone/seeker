# Proposal

## Why

The prior-art prosecutor needs something to search before it reaches for the web. Gabe also wants to capture art, music and games he comes across as ontology-shaped entries. These are the same need from two sides. A store of works that already exist, each tagged with Seeker's own cards, does two jobs:
- **A personal prior-art map.** It records what Gabe has seen.
- **A free, offline novelty check.** "Has anyone already combined these cards?" becomes a local query before it's a web search.

It is also Swanson's method built into everyday browsing. Cards that keep appearing separately but never together are the gaps worth drawing. The vault is the agreed store (see `openspec/config.yaml` context), so this change builds that store and the tools around it, before the debate change builds the prosecutor on top.

## What Changes

- **Ontology:**
  - a `Work` class: a creative work, instrument, game, publication or paper that already exists;
  - the `WorkKind` and `CaptureSource` enums;
  - a `WorkId` type;
  - slots for the work's title, creators, year, URL, kind, creative fields, linked cards, capture source and capture date.
- **Works are Obsidian notes.**
  - Each `Work` is one note in the vault's works folder, with frontmatter matching the class and a free-form body.
  - Cards are linked as wikilinks (`[[granular-synthesis]]`), so the graph view shows which cards real works connect.
- **Card notes in the vault.** `seeker-works sync-cards` writes one note per deck card into the vault's cards folder. Each note has:
  - the card's axis and fields;
  - its synonyms as Obsidian `aliases`, so `[[microsound]]` resolves to the granular-synthesis note;
  - a Seeker-managed block that's rewritten on every sync, while anything Gabe writes outside it is kept.
- **Reading and validating the vault.**
  - `seeker-works validate` loads every work note into a `WorkCatalog`.
  - Every problem is reported at once (bad frontmatter, unknown card links, duplicate ids), naming the note and the field.
- **Local card matching.** `seeker-works suggest` finds card names and synonyms in each work's title, summary and body, and proposes card links. `--apply` adds them to the note. It's free, deterministic and editable, so the capture step can stay simple.
- **Local prior-art check.** `seeker-works check --batch <file>` lists, for every draw, the works that already combine two or all three of its cards.
- **Capture template.** A ready-to-import Obsidian Web Clipper template (`capture/seeker-work.clipper.json`) that saves the current page as a `Work` note in the works folder. Its properties come from the page metadata: title, URL, author, published year and description. That settles the plugin question for v1: no custom extension.
- **Config:** the vault root comes from `SEEKER_VAULT` (the environment or the git-ignored `.env`), falling back to `paths.vault`. `seeker.yaml` gains `vault_folders` (works and cards, relative to the vault). The vault commands say clearly when no vault is set.

Out of scope:
- **The prosecutor:** the debate change will query this catalog and cache what it finds as `CaptureSource: prosecutor` works.
- **A custom browser extension:** it gets its own repo, and only if the Web Clipper falls short.
- **Exporters** (YAML, table catalogs), **creator notes as their own class**, and **fuzzy or semantic matching**.

## Capabilities

### New Capabilities
- `prior-art-works`: works captured in the Obsidian vault as ontology-shaped notes linked to cards, validated, matched to cards, and queried for prior art against draws.

### Modified Capabilities
None. Decks, draws and generation only feed this capability; their requirements are unchanged.

## Impact

- **Engine stage:** this adds the prior-art layer between the draw and the debate. No agent role changes yet. `check` is the deterministic precursor to the prior-art prosecutor.
- **Reproducibility:**
  - The vault is mutable, hand-edited data, so a prior-art check reflects the vault as it is when it runs.
  - `WorkCatalog` exposes a digest over its normalized works, like the deck digest. A future run can record exactly what prior art it saw.
  - Resumability is unaffected.
- **Ontology:**
  - class `Work`;
  - enums `WorkKind` and `CaptureSource`;
  - type `WorkId`;
  - new slots `title`, `creators`, `year`, `url`, `kind`, `captured_by`, `captured_on` and `summary`.
  - Existing slots reused through `slot_usage`: `id` (ranged as `WorkId` for works), `fields`, and `cards` (as card references, not inlined, and optional for works).
  - The conformance test learns `date` and `uri` ranges.
- **Writes into Gabe's vault:**
  - `Cards/` gets 153 card notes, plus Seeker-managed blocks inside them.
  - `suggest --apply` edits the `cards` property of work notes.
  - Nothing else in the vault is touched.
- **Code:**
  - `seeker/works/`: the note reader and writer, catalog, matcher, checker and CLI;
  - `capture/`: the template;
  - `docs/works.md`.
- **Dependencies:** none. Frontmatter is parsed with PyYAML.
