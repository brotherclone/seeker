# Design

## Context

- `seeker.ontology` already models `Card`, `Deck` and `DeckSet` as a mirror of `schema/seeker.yaml`, and a two-way conformance test keeps the two in sync.
- `seeker.decks` loads and validates decks and computes `DeckDigest` and `DeckSetDigest`. Card order is part of a deck's digest on purpose, so draws can rely on deck order.
- The seeded decks hold 36, 34, 35, 33 and 15 cards. Every core deck lists each `CreativeField` on at least three cards. All `domain` cards are cross-cutting.
- See proposal.md for why, and `specs/card-draws/spec.md` for the requirements.

## Goals / Non-Goals

**Goals:**
- A batch builder that is a pure function of (deck set, seed, size), so the same inputs give the same output on any Python version.
- Balanced batches that still allow any combination: balance spreads the batch across the box without filtering any cards out.
- A record format that validates against the schema and can be replayed and checked.

**Non-Goals:**
- Field distance, pinning, exclusion, weighting, and axes beyond the five required ones (see the proposal).
- Persisting batches. The Run change will store them; here a batch is only a value, optionally written to a file.
- Choosing a "good" draw. Judging quality is the job of the agents downstream.

## Decisions

### 1. Ontology first: `Draw`, `DrawBatch`, `Sha256Digest`

Added to `schema/seeker.yaml`, with the concept notes updated in the same change:

```yaml
types:
  Sha256Digest:   # typeof string, pattern ^[0-9a-f]{64}$, uri seeker:Sha256Digest

slots:
  seed:            {range: integer, minimum_value: 0, required: true}
  deck_set_digest: {range: Sha256Digest, required: true}
  draws:           {range: Draw, multivalued: true, inlined_as_list: true, required: true, minimum_cardinality: 1}
  position:        {range: integer, minimum_value: 1, required: true}   # 1-based within the batch
  axes:            {range: AxisId, multivalued: true, required: true, minimum_cardinality: 3, maximum_cardinality: 3}
  home_field:      {range: CreativeField, required: true}
  drawn_cards:     {range: Card, inlined: false, multivalued: true, required: true,
                    minimum_cardinality: 3, maximum_cardinality: 3}    # CardId references

classes:
  Draw:      {slots: [position, axes, home_field, drawn_cards]}
  DrawBatch: {slots: [seed, deck_set_digest, draws]}
```

- **Card references:** `drawn_cards` refers to `Card` by `CardId` rather than inlining whole cards. A batch record stays small, and the deck files remain the single source of card content. The deck-set digest is what ties the ids to a specific deck version.
- **No shape enum:** a draw's shape is its `axes`. The six shapes are derived from `DeckSet.REQUIRED_AXES` rather than listed again in the schema.
- **No `size` slot:** a batch's size is `len(draws)`, so it can't disagree with the draws.
- **Python side:**
  - `Draw` and `DrawBatch` go in `seeker/ontology/draw.py`.
  - `Sha256Digest` becomes a `LinkMLString` subclass in `types.py`.
  - The existing `DeckDigest` and `DeckSetDigest` adopt it in place of a pattern-checked `str`.
- **Conformance test changes:**
  - `integer` maps to `int`.
  - A non-inlined class range maps to that class's identifier type, so `drawn_cards: Card` maps to `tuple[CardId, ...]`.
  - Cardinality bounds are checked against `min_length`/`max_length`.

### 2. Randomness: a SHA-256 counter stream, not `random`

`DrawStream(seed)` produces 64-bit integers as `sha256(f"seeker/draw/v1:{seed}:{counter}")[:8]`. On top of that:
- `below(n)` uses rejection sampling, so there is no modulo bias.
- `shuffle(items)` is a Fisher-Yates shuffle built only on `below`.

*Why not `random.Random(seed)`:*
- Python only guarantees that `random()` itself is reproducible across versions.
- `choice`, `sample`, `shuffle` and `randrange` have changed between releases, and `randrange` changed in 3.12.
- A golden test would break on an interpreter upgrade, and old batches would silently stop replaying.

*Why not numpy's `Generator`:* it adds a heavy dependency for about 20 lines of code, and its stream promises are no stronger.

The `v1` in the domain string lets a future algorithm change bump the version rather than silently alter old batches.

### 3. The batch algorithm

The algorithm makes a fixed number of stream calls in a fixed order, so it is deterministic.

```
capacity check  ->  shape schedule  ->  home-field rotation  ->  per-draw card picks
```

1. **Capacity.**
   - Each non-constraint axis appears in 3 of the 6 shapes. With N = 6q + r draws, an axis is used at most 3q + min(r, 3) times; `constraint` is used N times.
   - The capacity is the largest N for which every axis's worst-case usage fits its deck.
   - For the seeded decks that's 30: at N = 31 `domain` could need 16 cards. At N = 12 every axis is used exactly 6 times.
   - A requested size outside 1..capacity is rejected before any randomness is used.
2. **Shape schedule.**
   - Each of the six canonical shapes gets q draws.
   - The six shapes are shuffled, and the first r get one extra draw.
   - The resulting list of N shapes is shuffled again to set the draw order.
3. **Home fields.**
   - `offset = below(7)`. Draw i gets `FIELDS[(offset + i) % 7]`, in `CreativeField` declaration order.
   - Counts per field differ by at most one, and the offset varies which fields get the extra draw.
4. **Picks, in position order.**
   - Each axis keeps a list of unused cards in deck order.
   - Choose the supplier axis uniformly from the draw's axes that still have an unused card explicitly listing the home field. Cross-cutting cards don't count, so `domain` never supplies.
   - Pick that card uniformly from the matching unused cards.
   - Fill each remaining axis uniformly from its unused cards, matching the field or not.
   - Mark all three cards used. If no axis can supply the home field, raise `UnsatisfiableHomeField(position, field)`.
   - `drawn_cards` follows `axes` order: constraint first, then canonical order.

Greedy picking is enough here. The seeded decks have at least 3 field cards per core axis, and a batch at capacity (30) asks for at most 5 draws per field. Failure is only realistic with small custom decks, and those fail loudly.

### 4. Replay and provenance

`BatchDrawer(deck_set).draw(seed, size)` returns a `DrawBatch` carrying `DeckSetDigest.of(deck_set).sha256`.

`BatchDrawer.replay(record)`:
- checks the current digest first, and raises `DecksChanged(recorded, current)` if they differ;
- otherwise redraws with `record.seed` and `len(record.draws)` and asserts equality.

The digest check comes first, so the error explains why the batch changed rather than just reporting that it differs.

### 5. Code layout

`seeker/draw/`:
- `stream.py`: `DrawStream`
- `shapes.py`: `DrawShape`, a small model of the six canonical shapes and their axes
- `drawer.py`: `BatchDrawer`, plus a `DrawCapacity` model with a `largest` property
- `errors.py`: `DrawError`, with subclasses `SizeOutOfRange`, `UnsatisfiableHomeField` and `DecksChanged`
- `cli.py`

`DrawShape` and `DrawCapacity` are tooling models, so they have no `class_uri`, the same pattern as `DeckDigest`. The house-style test already covers the new package.

### 6. Command line

A separate `seeker-draw` command, because drawing isn't deck maintenance:

```
seeker-draw batch [--seed N] [--size 12] [--dir decks] [--out batch.yaml]

  1  writing     constraint: one page | technique: cut-up technique | domain: liturgy
  2  comics      constraint: wordless | medium: risograph print | historical-artifact: Zip-A-Tone screentone
  ...
seed 7  decks 41909d46fec8  12 draws
```

- With no `--seed`, the seed comes from `secrets.randbelow(2**31)`. That's short enough to type and big enough not to collide in practice.
- `--out` writes `DrawBatch.model_dump(mode="json")` as YAML.
- The default size is 12, matching plan step 3.

### 7. Obsidian

- Concept notes `Seeker/Ontology/Draw.md` and `DrawBatch.md`, linked to `[[Card]]`, `[[DeckSet]]`, `[[CreativeField]]` and forward to `[[Idea]]`/`[[Run]]`.
- Decision note `Seeker/Decisions/2026-11-03 Draw shape and balance.md`, covering:
  - shape B and its alternatives;
  - balance versus filtering;
  - the SHA-256 stream;
  - field distance deferred, and generator-side ambiguity assigned to the roles change.
- The hub lists the new classes and the change.

## Risks / Trade-offs

- [Greedy home-field picks can fail on small or skewed custom decks] → The failure is loud and names the position and field. The seeded decks have ample margin.
- [Balance plus no-repeat makes a batch feel "curated"] → Only the spread is controlled. Which cards land together is uniform, so odd combinations are as likely as tame ones.
- [Changing the algorithm breaks old replays] → The version string in the stream and the golden test make any change deliberate. A `v2` stream can coexist later.
- [Card references go stale when a card is renamed] → The digest check catches it on replay, and the error names both digests.
- [The capacity bound is conservative, since it assumes the extra draws land on the worst axes] → At most this costs a few draws near capacity. Batches are expected to be about 12, well under 30.

## Open Questions

- Should batch records go in a conventional folder (`runs/` or `batches/`) before the Run change exists? This can be decided at the CLI without affecting the specs. For now `--out` takes any path.
