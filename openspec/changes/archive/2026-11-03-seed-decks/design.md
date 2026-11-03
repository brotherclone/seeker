# Design

## Context

The repo has no code yet. `docs/concept.md` fixes the stack (Python orchestrator, YAML decks and prompts in git, SQLite run state) and the five starting axes. The project conventions in `openspec/config.yaml` and `CLAUDE.md` are:

- ontology-first LinkML;
- object-oriented Pydantic v2 with metadata matching the schema;
- no dataclasses and no generic typing above the primitive level;
- design notes kept in Obsidian.

Requirements are in `specs/card-decks/spec.md`. This design covers the schema, the models that mirror it, the loader, and the seed content.

## Goals / Non-Goals

**Goals:**
- A LinkML schema that later changes extend (`Idea`, `Role`, `Run`, `Debate` and so on) rather than replace.
- One loader that every later stage imports: draw, generator prompts, and prior-art query expansion.
- Errors a human can fix from the message alone: the file, the card id and the slot.
- Digests stable enough to compare runs across prompt and deck edits.

**Non-Goals:**
- Card weighting, rarity, cross-field draw rules, or "never pair X with Y" rules. These belong to the draw change, as new optional slots.
- Mapping cards or fields to external vocabularies (Wikidata, Getty AAT). LinkML `meaning` and `exact_mappings` can add these later without breaking existing decks.
- Hot reloading or a deck editor UI.

## Decisions

### 1. LinkML schema is the source of truth

`schema/seeker.yaml`:

- **Header:** `id: https://github.com/brotherclone/seeker/schema`, `prefixes: {seeker: …/schema/, linkml: …}`, `default_prefix: seeker`, `imports: [linkml:types]`.
- **Types** (each with a description and pattern):
  - `CardId` and `AxisId`: `typeof: string`, `pattern: ^[a-z0-9]+(-[a-z0-9]+)*$`;
  - `Tag`: the same pattern;
  - `Synonym`: a non-empty string.
- **Enum** `CreativeField`, with a description on each permissible value. Values: `music`, `visual-art`, `film`, `electronics`, `writing`, `comics`, `games`. The description of `games` covers board, card and electronic games.
- **Classes:**
  - `Card`, with slots `id` (identifier, `CardId`), `name`, `synonyms` (multivalued `Synonym`), `fields` (multivalued `CreativeField`), `tags` (multivalued `Tag`) and `note`;
  - `Deck`, with slots `axis` (`AxisId`), `name`, `description` and `cards` (multivalued, inlined as a list of `Card`);
  - `DeckSet` (`tree_root: true`), with slot `decks` (multivalued, inlined `Deck`).
- **Metadata:** `title`, `description`, `examples` and, where they help, `aliases`/`see_also`. For example, `Card` has `see_also` pointing to Zwicky's morphological box.
- **Exports:** a `make schema` target runs `gen-shacl` and `gen-owl` into `schema/generated/`, and the generated files are committed so ontology diffs show up in review. `linkml-lint` runs in tests.
- **Second check on deck files:** `linkml-validate -s schema/seeker.yaml -C Deck decks/*.yaml` gives an independent check of each file. The Python loader remains the authority for the cross-file rules: global id uniqueness, axis matching the file name, and required axes.

### 2. Hand-written object-oriented Pydantic models, kept in sync by a conformance test

`seeker/ontology/` holds one module per concept:

- `types.py`: `CardId`, `AxisId`, `Tag` and `Synonym` as named `Annotated[str, StringConstraints(...)]` types, with the same patterns as the schema.
- `fields.py`: `CreativeField(StrEnum)`, with a description for each member.
- `card.py`, `deck.py`, `deck_set.py`: the classes themselves.

Each class follows the schema:

- It subclasses a shared `SeekerModel(BaseModel)` configured with `extra="forbid"`, `frozen=True` and `str_strip_whitespace=True`.
- The class `title` and docstring come from the schema.
- Every slot is a `Field(title=…, description=…, examples=…, json_schema_extra={"slot_uri": "seeker:…"})`.
- Multivalued slots are `tuple[...]` of named types. Tuples are immutable, and their order is meaningful to the digest.

Behavior lives on the models:

- `Card.matches(term)` checks the name and synonyms.
- `Card.in_field(field)` treats a card with no fields as cross-cutting, so it matches every field.
- `Deck.card(card_id)`, `Deck.by_field(field)` and `Deck.digest`.
- `DeckSet.load(path)`, `DeckSet.card(card_id)`, `DeckSet.coverage()` and `DeckSet.digest`.
- Reports are models too: `DeckDigest`, `FieldCoverage`, `DeckError` (file, card id, slot, message) and `ValidationReport`.

`tests/test_conformance.py` uses `linkml_runtime.SchemaView`. For every schema class it asserts that a Pydantic model exists with the same slots, required flags, multivaluedness, ranges and descriptions. For `CreativeField` it asserts the same values and descriptions. Drift in either direction fails the test. The schema changes first, then the model.

*Alternative considered: generating the models with `gen-pydantic` and subclassing them for behavior.*
- It was rejected because the generated code is flat, uses generic `Optional[List[...]]`/`Any`-style typing and a catch-all config base, and gets overwritten on every regeneration.
- That cuts against the object-oriented, named-type style.
- The conformance test gives the same guarantee without the generated layer.

*Alternative considered: putting the descriptions only in the schema.*
- It was rejected because the model metadata is what IDEs, `model_json_schema()` and future agent tool schemas actually see.

**What "no generic typing above the primitive level" means here:**
- No `Any`, no `dict[...]` payloads, no `TypedDict`, no `NamedTuple`, no dataclasses, no `TypeVar`/`Generic` classes.
- Containers are allowed only as `tuple[NamedModel, ...]` or `tuple[NamedType, ...]`.
- Domain scalars are never a bare `str`.

### 3. Loading and validation

- **YAML:** PyYAML `safe_load`, with a custom loader that rejects duplicate keys. Plain `safe_load` silently lets the last one win.
- **Pass one:** each file builds a `Deck` through Pydantic. Errors are converted to `DeckError`s carrying the file, card id and slot.
- **Pass two:** set-level checks (axis matches the file name, required axes, global id uniqueness).
- **Result:** every error from both passes goes into a single `ValidationReport`.

### 4. Digests

- **Per deck:** SHA-256 over canonical JSON of the validated model. Uses `model_dump(mode="json")` with defaults filled in, then `sort_keys=True`, compact separators and `ensure_ascii=False`.
- **Set digest:** SHA-256 over the axis-ordered `(axis, digest)` pairs.
- **Card order is part of the digest on purpose**, so a later seeded draw can depend on order.
- **Display:** the CLI shows 12 hex characters; run records keep the full hash.

### 5. Card ids are global

- Run records will store card ids alone, so a concept that appears on two axes needs two ids. For example, `tape` (a medium) and `phonogene` (a historical machine).

### 6. Command line

- `python -m seeker.decks validate [--dir decks]`, also installed as the `seeker-decks` console script.
- argparse is enough for a single subcommand. Revisit once the orchestrator has a real CLI.

### 7. Seed content

The decks span seven creative fields, and the existing music cards stay as they are. Cards that span several fields are the most valuable kind (Swanson's bridges), so cross-field fields are assigned wherever they're honest. Synonyms are added where the specialist vocabulary differs (granular synthesis also goes by "microsound"; Oramics by "drawn sound"), and nowhere else.

- **technique** (36)
  - existing music cards: granular, physical modeling, cellular automata, L-systems, FM, wavetable, Karplus-Strong, phase vocoder, concatenative, convolution, Markov chains, genetic algorithms, GENDY, spectral freeze, waveguide reverb
  - cross-field assignments on existing cards: cellular automata and genetic algorithms also get `visual-art` and `games`; L-systems get `visual-art`; Markov chains get `writing`
  - new, visual-art: reaction-diffusion, Voronoi tessellation, flow fields, error-diffusion dithering
  - new, film: datamoshing, slit-scan, rotoscoping, Kuleshov montage
  - new, electronics: capacitive sensing, circuit bending, piezo contact sensing
  - new, writing: cut-up, N+7, erasure, procedural grammar
  - new, comics: gutter closure, infinite canvas, braiding (*tressage*)
  - new, games: wave function collapse, deckbuilding, roll-and-write
- **medium** (34)
  - existing: tape, LÖVE game, 500-series module, web artifact, VST/AU plugin, Max/MSP patch, MIDI file, ACE Studio vocal, Raspberry Pi box, installation, radio broadcast, zine, album side, nanoKONTROL2 mapping, Rails site
  - new, visual-art: risograph print, pen-plotter drawing, projection mapping
  - new, film: 16mm loop, VHS tape, vertical short
  - new, electronics: ESP32 board, LED matrix, e-ink display
  - new, writing: Twine story, chapbook, audio drama
  - new, comics: minicomic, webcomic, 24-hour comic
  - new, games: card deck, board game, PICO-8 cartridge, TTRPG zine
- **historical-artifact** (35)
  - existing: Oramics, Telharmonium, Votrax, Electronium, Trautonium, ANS, Mellotron, RCA Mark II, Fairlight CMI, Novachord, Rhythmicon, Sonovox, TMS5100, Dudley vocoder, player-piano roll
  - new, visual-art: camera obscura, AARON, Clavilux
  - new, film: zoetrope, Sensorama, Lumigraph
  - new, electronics: Jacquard loom, Nixie tube, Heathkit kits, Simon
  - new, writing: Llull's combinatorial wheels, *Cent mille milliards de poèmes*, Strachey's love-letter generator, Choose Your Own Adventure
  - new, comics: Ben-Day dots, Zip-A-Tone screentone, the Mad Fold-In
  - new, games: Kriegsspiel, Nimatron, The Landlord's Game
- **constraint** (33)
  - existing, given fields where they fit and left cross-cutting otherwise: no screen, 7-bit, real-time only, one knob, under 4 KB, no samples, mono, one take, runs in a browser, offline only, playable by a non-musician, eight voices max, no keyboard, fits on a 46-minute tape, must be explainable in a liner note
  - new, visual-art: one color, a single sheet of paper, made on a photocopier
  - new, film: one continuous shot, under 15 seconds, no dialogue
  - new, electronics: under $20 in parts, battery powered, a single sensor
  - new, writing: lipogram, second person only, must be read aloud
  - new, comics: wordless, nine-panel grid, one page
  - new, games: no randomness, solo only, 18 cards
- **domain** (15, unchanged): mycology, cartography, liturgy, tax law, ornithology, tide tables, utopian communes, dendrochronology, beekeeping, railroad timetables, heraldry, knitting patterns, cryptography, weather forecasting, local newspaper archives

### 8. Obsidian notes

The vault is Bracers (`…/Claude/Projects/Bracers/Projects`). Notes go under `Seeker/`, following the conventions in `CLAUDE.md`:

- `Seeker/Seeker.md`: the hub.
- `Seeker/Ontology/Card.md`, `Deck.md`, `DeckSet.md`, `CreativeField.md`: one concept note each, mirroring the schema. Each gives the definition and the slots with their ranges, with wikilinks between the classes, plus `[[Zwicky's morphological box]]` and `[[Literature-based discovery]]` as lineage notes.
- `Seeker/Decisions/2026-11-03 Ontology-first decks.md`: records decisions 1, 2 and 5 above, and the choice of field tags over a sixth axis.

The concept notes are updated in the same change as the schema, so the graph view stays a faithful picture of the ontology.

## Risks / Trade-offs

- [The seed decks reflect one person's taste] → They are a draft. Gabe reviews them before the test batch, and plan step 4 is where decks get adjusted.
- [Bigger cross-field decks dilute music-focused draws] → The draw change can weight or filter by `CreativeField`.
- [Hand-written models drift from the schema] → The conformance test fails on any drift, in either direction.
- [The LinkML toolchain is heavy] → Only `linkml-runtime` is a runtime dependency. `linkml` (lint, validate, generators) is a dev extra.
- [Global id uniqueness adds friction when editing YAML by hand] → The validator names both colliding files, so the fix is a one-line rename.
- [Reordering cards changes the digest] → This is intended. Reorders are rare and visible in git.

## Open Questions

- Should `historical-artifact` cards carry a year or era slot for later filtering? It can be added as an optional slot without breaking existing decks.
