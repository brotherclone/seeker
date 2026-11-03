# Proposal

## Why

The decks exist, but nothing draws from them yet. The test batch in plan step 3 needs about 12 card triples to feed the generator. Before any agent runs, the draw has to be pinned down: what a triple is made of, how a batch spreads across the box, and how to replay it exactly. The draw is the engine's only random step, so if it can't be reproduced, no later comparison between runs means anything.

## What Changes

- **Draw shape:** every draw is a triple made of one `constraint` card plus cards from two of the other four required axes (`technique`, `medium`, `historical-artifact`, `domain`). That gives six possible shapes.
- **Balanced batches:**
  - the six shapes appear equally often, give or take one, so 12 draws use each shape twice;
  - no card repeats within a batch;
  - each draw gets a **home field** that rotates through the seven creative fields, and at least one of its cards must list that field.
- **Seeded and replayable:** the same seed, deck set and batch size always produce the same batch, on any Python version. A batch records its seed and the deck-set digest. Replaying it against decks that have since changed is an error, not a silent drift.
- **Unfiltered otherwise:** a balanced batch may still contain very odd combinations. There is no field-distance filter.
- **New ontology:** the `Draw` and `DrawBatch` classes, the `Sha256Digest` type, and the slots for them, with matching Pydantic models and Obsidian concept notes.
- **New command:** `seeker-draw batch --seed N --size 12 [--out PATH]` prints the batch and optionally writes its record as YAML that validates against the schema.

Out of scope (decided while exploring):
- **Field-distance setting** (coherent / bridge / alien): left out until a round shows the draws need it.
- **Generator-side ambiguity** (literal / loose / metaphorical reading): this is the round-2 setting and belongs to the roles change.
- **Pinning or excluding cards, and card weighting.**
- **Axes beyond the five required ones.** Extra axis files still load, but draws ignore them.
- **The run store and timestamps.** A batch is a pure function of its inputs; the Run change will store batches.

## Capabilities

### New Capabilities
- `card-draws`: drawing balanced, reproducible batches of card triples from a deck set, and the draw records that let a batch be replayed and checked.

### Modified Capabilities
None. `card-decks` requirements are unchanged; draws only read deck sets.

## Impact

- **Engine stage touched:** the draw, the step between the decks and the generator role. No agent role or prompt changes.
- **Reproducibility:** this is the change that makes runs replayable.
  - A batch is fully determined by its seed, the deck-set digest and its size.
  - The random stream is derived from SHA-256 rather than Python's `random`, so it doesn't change across interpreter versions.
  - A replay against changed decks fails loudly.
  - Resumability is unaffected for now. Batches are cheap to regenerate, and the Run change will persist them.
- **Ontology:**
  - new classes `Draw` and `DrawBatch`;
  - new type `Sha256Digest`;
  - new slots `seed`, `deck_set_digest`, `draws`, `position`, `axes`, `home_field` and `drawn_cards` (references to `Card` by `CardId`).
  - The existing digest models in `seeker.decks` adopt `Sha256Digest`.
- **Code:**
  - new package `seeker/draw/` for the batch builder, the random stream and the CLI;
  - the conformance test learns `integer` ranges and non-inlined class references;
  - new tests.
- **Docs:** `docs/` or `decks/README.md` gain a short section on drawing. The Obsidian vault gains `Draw` and `DrawBatch` concept notes and a decision note.
- **Dependencies:** none new.
