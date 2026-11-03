# Design

## Context

The repo has no code yet. `docs/concept.md` fixes the stack (a Python orchestrator, YAML decks and prompts in git, SQLite run state) and the five starting axes. Requirements are in `specs/card-decks/spec.md`. This design covers how the loader is built and what the first seed content looks like.

## Goals / Non-Goals

**Goals:**
- A single loader every later stage imports: draw, generator prompts and prior-art query expansion.
- Errors a human can fix from the message alone: file, card id, field.
- Digests stable enough to compare runs across prompt and deck edits.

**Non-Goals:**
- Card weighting, rarity, or "never pair X with Y" rules. If those are needed later, add them in the draw change as new optional fields.
- Per-card metadata beyond synonyms, tags and note (eras, URLs, prior-art links). These can be added later without breaking existing files.
- Hot reloading or a deck editor UI.

## Decisions

**Package layout.**
- `seeker/` is a regular package; deck code lives in `seeker/decks.py`.
- The command is `python -m seeker.decks validate [--dir decks]`, plus a `seeker-decks` console script in `pyproject.toml`.
- Alternative considered: a click/typer CLI. It isn't needed yet, since argparse covers a single subcommand. Revisit when the orchestrator CLI exists.

**Validation with pydantic v2 models.**
- `Card` and `Deck` models use `extra="forbid"` and field validators for the kebab-case and synonym rules.
- Cross-file checks run as a second pass over the loaded set: global id uniqueness, axis-to-file match, required axes.
- Errors are collected into a list rather than raised one by one, so a single run reports everything.
- Alternative considered: a JSON Schema plus `jsonschema`. It gives editor autocompletion for free, but it can't express the cross-file rules and produces worse error messages. A JSON Schema can be exported later with `Deck.model_json_schema()` if editor support is wanted.

**PyYAML `safe_load`.**
- Round-trip preservation (ruamel) isn't needed, because nothing writes decks programmatically in this change.
- Duplicate YAML keys are a known `safe_load` blind spot: the last one wins silently. A small custom loader rejects them.

**Digest = SHA-256 over canonical JSON.**
- Serialize each deck's validated model with `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)` and hash the UTF-8 bytes.
- The set digest hashes the axis-ordered list of `(axis, deck_digest)` pairs.
- Defaults are materialized before hashing (empty synonyms, empty tags, null note), so writing `tags: []` and omitting tags hash the same.
- Card order is part of the digest on purpose. Order may later carry meaning, such as display order or tie-breaks in a seeded draw.
- The first 12 hex chars are shown in CLI output; the full hash is kept for run records.
- Alternative considered: hashing raw file bytes. It's simpler, but a comment edit would make two identical runs look different.

**Ids are global.**
- Run records will store card ids, not `(axis, id)` pairs, so ids must be unique across decks.
- Where a concept legitimately lives on two axes (tape as a medium versus a historical tape machine), the ids must differ, for example `tape` and `phonogene`. This also forces a choice about what the card actually means.

**Seed content is a first draft for Gabe to edit, not a final list.**
- Cards skew toward the home studio and stack: the 500-series rack, nanoKONTROL2, LÖVE2D, JUCE, Rails, ACE Studio.
- Constraint cards are phrased as hard limits an idea can fail, not as moods.
- Draft lists (about 15 each):
  - **technique:** granular synthesis, physical modeling, cellular automata, L-systems, FM synthesis, wavetable synthesis, Karplus-Strong, phase vocoder, concatenative synthesis, convolution, Markov chains, genetic algorithms, stochastic synthesis (GENDY), spectral freeze, waveguide reverb
  - **medium:** tape, LÖVE game, 500-series module, web artifact, VST/AU plugin, Max/MSP patch, MIDI file, ACE Studio vocal, Raspberry Pi box, installation, radio broadcast, zine, album side, nanoKONTROL2 mapping, Rails site
  - **historical-artifact:** Oramics, Telharmonium, Votrax speech chip, Raymond Scott's Electronium, Trautonium, ANS synthesizer, Mellotron, RCA Mark II, Fairlight CMI, Hammond Novachord, Rhythmicon, Sonovox, Speak & Spell (TMS5100), Dudley vocoder, player-piano roll
  - **constraint:** no screen, 7-bit, real-time only, one knob, under 4 KB, no samples, mono, one take, runs in a browser, offline only, playable by a non-musician, eight voices max, no keyboard, fits on a 46-minute tape, must be explainable in a liner note
  - **domain:** mycology, cartography, liturgy, tax law, ornithology, tide tables, utopian communes, dendrochronology, beekeeping, railroad timetables, heraldry, knitting patterns, cryptography, weather forecasting, local newspaper archives
- Synonyms are filled in where the specialist vocabulary differs, because that is what the prior-art search needs. For example, granular synthesis also goes by "microsound" and "grain cloud", and Oramics by "drawn sound". Synonyms are not padded where nothing differs.

## Risks / Trade-offs

- [Seed decks reflect one taste and become an echo chamber] → They are explicitly a draft. Gabe edits them before the test batch, and the review step in the plan is where decks get adjusted.
- [Global id uniqueness feels fussy when editing YAML by hand] → The validator names both colliding files, so the fix is a one-line rename.
- [Card order in the digest means reordering looks like a change] → This is intended. Reordering is rare and visible in git anyway.
- [pydantic is a heavyweight dependency for one loader] → The orchestrator will need it for prompt configs and agent I/O anyway, so it lands once here.

## Open Questions

- Should `historical-artifact` cards carry a year or era field for later filtering? It can be added as an optional field without breaking existing files, so it is deferrable.
