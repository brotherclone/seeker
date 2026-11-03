# Tasks

## 1. Package scaffold

- [x] 1.1 Add `pyproject.toml`: Python ≥3.11; runtime dependencies pydantic v2, PyYAML and linkml-runtime; dev extra with linkml and pytest; a `seeker-decks` console script. Add the `seeker/` and `seeker/ontology/` packages and a `Makefile` with `schema` and `test` targets. Verify that `pip install -e '.[dev]'` succeeds and `python -c "import seeker.ontology"` runs.

## 2. Ontology schema

- [x] 2.1 Write `schema/seeker.yaml` per design decision 1, with every element described. Verify that `linkml-lint schema/seeker.yaml` reports no errors.
- [x] 2.2 Generate SHACL and OWL into `schema/generated/` with `make schema` and commit them. Add a test that regenerates the exports and compares them with the committed files. Verify the test passes.
- [x] 2.3 Create the Obsidian hub note `Seeker/Seeker.md` and the concept notes `Seeker/Ontology/Card.md`, `Deck.md`, `DeckSet.md` and `CreativeField.md`, mirroring the schema and wikilinked to each other and to the hub. Verify each note exists in the vault and that its slot list matches the schema.

## 3. Domain models

- [x] 3.1 Implement the named types in `seeker/ontology/types.py` and `CreativeField` in `fields.py`, with metadata matching the schema. Verify unit tests cover the valid and invalid patterns.
- [x] 3.2 Implement the `SeekerModel` base and the `Card`, `Deck` and `DeckSet` models with rich `Field` metadata and their methods (`matches`, `in_field`, `card`, `by_field`, `coverage`). Verify unit tests for the minimal-card, bad-id, unknown-slot, unknown-field, multi-field and repeated-synonym scenarios.
- [x] 3.3 Add `tests/test_conformance.py`, which compares the models with the schema through `SchemaView`: slots, required flags, multivaluedness, ranges, descriptions and enum values. Verify it passes, and that it fails when a test-only model drops a slot.
- [x] 3.4 Add a lint test that fails if `seeker/` uses dataclasses, `NamedTuple`, `TypedDict`, `Any`, `dict[` or `Generic`. Verify it passes on the package.

## 4. Loading, validation and digests

- [x] 4.1 Implement the YAML loader that rejects duplicate keys, and `DeckSet.load` with the two validation passes, collecting `DeckError`s into a `ValidationReport`. Verify fixture-directory tests for every loading and validation scenario in the spec, including two errors in two files reported in one run.
- [x] 4.2 Implement `DeckDigest` and the set digest over canonical JSON. Verify tests show that reformatting and key reordering leave the digests unchanged, that editing one card changes only that deck's digest and the set digest, and that reordering cards changes the digest.
- [x] 4.3 Implement `python -m seeker.decks validate [--dir]` and the console script. Verify a CLI test against the valid and invalid fixture directories checks the output lines and exit codes.

## 5. Seed decks

- [x] 5.1 Write `decks/technique.yaml` and `decks/medium.yaml` from design decision 7, with fields and synonyms. Verify that `seeker-decks validate` passes.
- [x] 5.2 Write `decks/historical-artifact.yaml`, `decks/constraint.yaml` and `decks/domain.yaml` the same way. Verify that `seeker-decks validate` passes with all five axes and that `linkml-validate -s schema/seeker.yaml -C Deck decks/*.yaml` passes.
- [x] 5.3 Add content tests for deck size (24–40 for the four core decks, 12–20 for `domain`) and field coverage (at least 3 cards per `CreativeField` in each core deck). Verify `pytest` passes.
- [x] 5.4 Document the deck format, the creative fields and the validate command in `decks/README.md`, with one fully annotated example card. Verify the documented command runs as written.
- [x] 5.5 Write the decision note `Seeker/Decisions/2026-11-03 Ontology-first decks.md`, and update the concept notes with anything learned during implementation. Verify the note links to the hub, the concept notes and `seed-decks`.

## Workflow follow-up

- Gabe reviews and edits the seed cards before the test batch (plan step 4 covers deck adjustments).
- Archive the change once reviewed, so `openspec/specs/card-decks/spec.md` becomes the living spec.
