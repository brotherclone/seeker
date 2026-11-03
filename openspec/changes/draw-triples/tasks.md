# Tasks

## 1. Ontology

- [x] 1.1 Add `Sha256Digest`, the draw slots (`seed`, `deck_set_digest`, `draws`, `position`, `axes`, `home_field`, `drawn_cards`) and the `Draw`/`DrawBatch` classes to `schema/seeker.yaml` per design decision 1, every element described. Run `make schema`. Verify `linkml-lint` passes and that `tests/test_schema.py` (exports and descriptions) passes.
- [x] 1.2 Extend `tests/test_conformance.py`: `integer` maps to `int`, a non-inlined class range maps to the target class's identifier type, and cardinality bounds are checked. Verify the existing conformance tests still pass and that a planted model with a wrong `drawn_cards` type fails.
- [x] 1.3 Add `Sha256Digest` to `seeker/ontology/types.py` and the `Draw`/`DrawBatch` models in `seeker/ontology/draw.py`, with rich `Field` metadata and helpers (`Draw.shape`, `DrawBatch.card_ids`, `DrawBatch.size`), exported from `seeker.ontology`. Switch `DeckDigest`/`DeckSetDigest` to `Sha256Digest`. Verify the conformance test passes for the new classes and type, and unit tests cover the cardinality and position bounds.
- [x] 1.4 Write the Obsidian concept notes `Seeker/Ontology/Draw.md` and `DrawBatch.md`, and update `Sha256Digest` mentions in `Deck.md`/`DeckSet.md`. Verify the notes link to `[[Card]]`, `[[DeckSet]]`, `[[CreativeField]]` and the hub, and that their slot tables match the schema.

## 2. Random stream

- [x] 2.1 Implement `DrawStream` in `seeker/draw/stream.py` (SHA-256 counter stream, `next64`, `below(n)` with rejection sampling, Fisher-Yates `shuffle`). Verify that known first outputs for a fixed seed are pinned in a test, that `below` stays in range across many draws, and that `shuffle` is a permutation and reproducible.

## 3. Batch drawing

- [x] 3.1 Implement `DrawShape` (the six canonical shapes from `DeckSet.REQUIRED_AXES`, constraint first) and `DrawCapacity` (worst-case usage per axis, `largest`) in `seeker/draw/`. Verify tests: exactly six shapes, the extra `tuning` axis never appears, the seeded-deck capacity is 30, and a small fixture's capacity is computed correctly.
- [x] 3.2 Implement the `DrawError` hierarchy and `BatchDrawer.draw(seed, size)` per design decision 3. Verify tests for every draw-shape, balance, no-repeat and home-field scenario in the spec, run against the seeded decks at sizes 1, 8, 12 and 30.
- [x] 3.3 Add the size-limit and unsatisfiable-home-field failures. Verify tests: size 0 and size capacity+1 are rejected with the capacity named, and a fixture with one `comics` card fails naming the position and `comics`.
- [x] 3.4 Add a golden-batch test: a small fixture deck set in `tests/fixtures/golden-decks/`, an expected batch committed as YAML, and an exact-match assertion. Also cover same-seed identity and different-seed difference. Verify it passes.
- [x] 3.5 Implement `BatchDrawer.replay(record)` with the digest check first (`DecksChanged`). Verify tests: replay on unchanged decks equals the record, and replay after editing one card fails naming both digests.

## 4. Command line and docs

- [x] 4.1 Implement `seeker-draw batch [--seed] [--size] [--dir] [--out PATH | --scratch]` and its console script. Add `batches/scratch/` to `.gitignore` and create `batches/` with a `.gitkeep`. Verify CLI tests:
  - a seeded run prints 12 lines plus the summary and exits 0;
  - an unseeded run prints a seed that reproduces the same batch;
  - `--out` writes YAML that validates against the schema as `DrawBatch` (`linkml-validate`) and replays cleanly;
  - `--scratch` writes `batches/scratch/<seed>.yaml`;
  - combining `--out` and `--scratch` is rejected;
  - `git check-ignore batches/scratch/x.yaml` reports the file as ignored.
- [x] 4.2 Add a "Drawing" section to `decks/README.md` covering shapes, balance, seeds, replay and capacity, plus which batches to commit (`batches/YYYY-MM-DD-<label>.yaml`) and which to leave in `batches/scratch/`. Verify the documented commands run as written against the seeded decks.

## 5. Record the decision

- [x] 5.1 Write `Seeker/Decisions/2026-11-03 Draw shape and balance.md` and update the hub (new classes, change status). Verify the note links to the hub, the concept notes and `draw-triples`.

## Workflow follow-up

- Open a PR from `feature/draw-triples` into `develop`. Archive the change after merge so `card-draws` becomes a living spec.
- Next changes: roles (agent prompts, `Idea`/`Role`, the generator's reading setting for round 2), then the test batch.
