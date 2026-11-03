# Proposal

## Why

Every stage of the engine starts from a card draw, and there are no decks yet. Step 2 of the plan in `docs/concept.md` is to seed them. The deck format has to be settled before the generator, draw logic or prior-art search can be built against it. Defining it now, with validation, also stops noun soup at the source: each axis is its own file, and malformed cards fail loudly instead of drifting into prompts.

## What Changes

- Define a deck file format: one YAML file per axis under `decks/`, holding axis metadata and a list of cards. Each card has a stable id, a display name, and optional synonyms, tags and a note.
- Seed the five starting axes with about 15 cards each, skewed toward Gabe's world:
  - `technique`
  - `medium`
  - `historical-artifact`
  - `constraint`
  - `domain`
- Add a loader and validator that read every deck, reject malformed or duplicate cards, and report a content digest per deck and for the whole set.
- Add a command-line check so decks can be validated by hand and in CI before any run.
- Scaffold the minimum Python package needed to host the loader (`pyproject.toml`, `seeker/` package, tests).

Out of scope:
- Drawing triples, weighting cards, or exclusion rules between cards. Those belong to a later draw change.
- Any agent prompts, the generator role, or prior-art search.
- The SQLite run store. This change only exposes the digests a run will later record.

## Capabilities

### New Capabilities
- `card-decks`: The deck file format, validation rules, loading, and deck-content digests that every draw and run depends on.

### Modified Capabilities
None. There are no existing specs.

## Impact

- **Engine stage touched:** the deck layer (the input to the generator's draw). It does not touch any agent role or prompt.
- **Reproducibility:** this change makes runs more reproducible. Each deck and the deck set as a whole get a deterministic digest of their normalized content. A run can then record exactly which cards it drew from, even with uncommitted edits, and the git commit stays the coarse anchor. Resumability is unaffected; nothing here holds run state.
- **New files:**
  - `decks/*.yaml`
  - `pyproject.toml`
  - `seeker/decks.py` (loader and validator)
  - `tests/`
- **New dependencies:** PyYAML and pydantic v2.
