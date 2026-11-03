# Proposal

## Why

Every stage of the engine starts from a card draw, and there are no decks yet. Step 2 of the plan in `docs/concept.md` is to seed them.

What a card, an axis or a field *is* has to be pinned down before the generator, draw logic or prior-art search are built against it. The project is ontology-first, so this change also founds the LinkML schema that every later concept will extend.

The seed content needs to reach well past music: visual art, film and video, sensors and electronics, creative writing, comics, and board, card and electronic games. Cross-field collisions are where the engine is most likely to find something nobody has tried.

## What Changes

- Found the Seeker ontology as a LinkML schema (`schema/seeker.yaml`). It defines the classes `Card`, `Deck` and `DeckSet`, the enum `CreativeField`, and the named types `CardId`, `AxisId`, `Tag` and `Synonym`, each with descriptions. SHACL shapes and OWL are generated from it.
- Define the deck file format as instances of that schema:
  - one YAML file per axis under `decks/`;
  - each card has a stable id, a name, optional synonyms, one or more creative fields, optional free tags, and an optional note.
- Seed the five starting axes:
  - `technique`, `medium`, `historical-artifact` and `constraint` with 32–36 cards each, spanning seven creative fields (`music`, `visual-art`, `film`, `electronics`, `writing`, `comics`, `games`);
  - `domain` with 15 cards.
- Add object-oriented Pydantic v2 models that mirror the schema with matching metadata, plus a conformance test that keeps the two in sync.
- Add a loader and validator that read every deck, reject malformed or duplicate cards, and report a content digest per deck and for the whole set.
- Add a command-line check so decks can be validated by hand and in CI before any run.
- Start the Seeker notes in the Obsidian vault: a hub note, one concept note per ontology class and enum, and a decision note for this change.

Out of scope:
- Drawing triples, weighting cards, cross-field draw rules, or exclusions. These belong to a later draw change, which can use `CreativeField`.
- Agent prompts, the generator role, and prior-art search.
- The SQLite run store. This change only exposes the digests a run will later record.

## Capabilities

### New Capabilities
- `card-decks`: the deck ontology, the deck file format, validation rules, loading, and deck-content digests that every draw and run depends on.

### Modified Capabilities
None. There are no existing specs.

## Impact

- **Engine stage touched:** the deck layer, which is the input to the generator's draw. No agent role or prompt changes.
- **Ontology added:**
  - classes `Card`, `Deck`, `DeckSet`;
  - enum `CreativeField`;
  - types `CardId`, `AxisId`, `Tag`, `Synonym`;
  - slots `id`, `name`, `synonyms`, `fields`, `tags`, `note`, `axis`, `description`, `cards`, `decks`.
- **Reproducibility:** this change makes runs more reproducible.
  - Each deck, and the deck set as a whole, gets a deterministic digest of its normalized content.
  - A run can record exactly which cards it drew from, even with uncommitted edits. The git commit stays the coarse anchor.
  - Resumability is unaffected; nothing here holds run state.
- **New files:**
  - `schema/seeker.yaml` and `schema/generated/`
  - `decks/*.yaml`
  - `pyproject.toml`
  - the `seeker/` package
  - `tests/`
  - Obsidian notes under `Seeker/`
- **New dependencies:** pydantic v2, PyYAML, linkml-runtime; linkml as a dev dependency, for lint, validate and generators.
