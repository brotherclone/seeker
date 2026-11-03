# Tasks

## 1. Package scaffold

- [ ] 1.1 Add `pyproject.toml` (Python ≥3.11, PyYAML, pydantic v2, pytest as a dev extra, `seeker-decks` console script) and an empty `seeker/__init__.py`; verify `pip install -e '.[dev]'` succeeds and `python -c "import seeker"` runs.

## 2. Loader and validation

- [ ] 2.1 Implement `Card` and `Deck` models in `seeker/decks.py` with `extra="forbid"`, kebab-case id and tag checks, and synonym-vs-name and synonym-vs-synonym checks; verify with unit tests for the minimal card, bad id, unknown field and repeated synonym scenarios.
- [ ] 2.2 Implement a YAML loader that rejects duplicate keys, plus a set loader for `decks/` that checks axis-to-file match, non-empty cards, required axes and global id uniqueness, collecting every error with file and card context; verify with fixture-directory tests covering each spec scenario, including two errors in two files reported in one run.
- [ ] 2.3 Implement per-deck and set digests over canonical JSON with defaults materialized; verify tests show that reformatting or reordering keys leaves digests unchanged, that editing one card changes only that deck's digest and the set digest, and that card reordering changes the digest.
- [ ] 2.4 Implement `python -m seeker.decks validate [--dir]` and the console script, printing axis, card count and short digest per deck plus the set digest, and exiting non-zero with all errors on failure; verify with a CLI test on valid and invalid fixture dirs.

## 3. Seed decks

- [ ] 3.1 Write `decks/technique.yaml` and `decks/medium.yaml` from the drafts in design.md, adding synonyms where the specialist vocabulary differs; verify `seeker-decks validate` passes.
- [ ] 3.2 Write `decks/historical-artifact.yaml`, `decks/constraint.yaml` and `decks/domain.yaml` the same way; verify `seeker-decks validate` passes with all five axes.
- [ ] 3.3 Add a test asserting that each required seeded deck has 12–20 cards and that `decks/` validates cleanly; verify `pytest` passes.
- [ ] 3.4 Document the deck format and the validate command in `decks/README.md`, with one fully annotated example card; verify the documented command runs as written.

## Workflow follow-up

- Gabe reviews and edits the seed cards before the test batch (plan step 4 covers deck adjustments).
- Archive the change once reviewed, so `openspec/specs/card-decks/spec.md` becomes the living spec.
