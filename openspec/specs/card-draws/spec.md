# card-draws Specification

## Purpose

Draws balanced, reproducible batches of card triples from a `DeckSet`, and records each `DrawBatch` so it can be replayed exactly and checked against the decks it came from.

## Requirements

### Requirement: Draw ontology is published in the LinkML schema
The schema SHALL define the classes `Draw` and `DrawBatch` and the type `Sha256Digest`, each with descriptions. A `DrawBatch` has `seed`, `deck_set_digest` and `draws`. A `Draw` has `position`, `axes`, `home_field` and `drawn_cards`, which are references to `Card` by `CardId`.

#### Scenario: Draw classes lint and conform
- **WHEN** the schema is linted and the conformance test runs
- **THEN** both pass, and `Draw`, `DrawBatch` and `Sha256Digest` have matching Python models and types

#### Scenario: Batch records are schema instances
- **WHEN** a `DrawBatch` record written by the draw command is validated against the schema with `DrawBatch` as the target class
- **THEN** validation passes

### Requirement: Draw shape
Every `Draw` SHALL contain exactly three cards from three different axes. One is from `constraint`, and the other two are from two of `technique`, `medium`, `historical-artifact` and `domain`. A draw's `axes` lists its three axes with `constraint` first, then the other two in canonical order: technique, medium, historical-artifact, domain.

#### Scenario: Every draw has a constraint
- **WHEN** a batch of any size is drawn from the seeded decks
- **THEN** every draw has exactly three cards, one from each of its three `axes`, and the first axis is `constraint`

#### Scenario: Only the six shapes occur
- **WHEN** a batch is drawn
- **THEN** every draw's `axes` is one of the six shapes formed by `constraint` plus two of the four other required axes

#### Scenario: Extra axes are not drawn
- **WHEN** the `DeckSet` also contains a `tuning` deck
- **THEN** no draw includes a `tuning` card

### Requirement: Shapes are balanced within a batch
Within a `DrawBatch`, the number of draws of each shape SHALL differ by at most one.

#### Scenario: Twelve draws
- **WHEN** a batch of 12 is drawn
- **THEN** each of the six shapes occurs exactly twice

#### Scenario: Uneven size
- **WHEN** a batch of 8 is drawn
- **THEN** two shapes occur twice and four occur once

### Requirement: No card repeats within a batch
A card SHALL appear at most once in a `DrawBatch`.

#### Scenario: Distinct cards
- **WHEN** a batch of 12 is drawn
- **THEN** all 36 drawn card ids are distinct

### Requirement: Home field rotates through the creative fields
Each `Draw` SHALL have a `home_field`, and across a `DrawBatch` the number of draws per `CreativeField` value SHALL differ by at most one. At least one card in each draw SHALL explicitly list its `home_field`. A cross-cutting card does not satisfy this.

#### Scenario: Balanced home fields
- **WHEN** a batch of 12 is drawn
- **THEN** five fields are home to two draws and two fields are home to one draw

#### Scenario: Home field is honored
- **WHEN** a draw has home field `comics`
- **THEN** at least one of its cards lists `comics` in `fields`

### Requirement: Batches are reproducible from seed, decks and size
Drawing with the same `seed`, the same deck content (the same deck-set digest) and the same size SHALL produce an identical `DrawBatch`, independent of the Python version or platform. The randomness SHALL derive only from the seed.

#### Scenario: Same inputs, same batch
- **WHEN** a batch is drawn twice with seed 7 and size 12 from unchanged decks
- **THEN** the two batches are identical

#### Scenario: Golden batch
- **WHEN** a batch is drawn with a fixed seed from the fixed test deck set
- **THEN** it matches the expected batch committed in the tests, card for card

#### Scenario: Different seed
- **WHEN** batches are drawn with seeds 7 and 8 from the same decks
- **THEN** they differ

### Requirement: Batches record their provenance
A `DrawBatch` SHALL record its `seed` and the `deck_set_digest` of the decks it was drawn from. Replaying a batch SHALL fail with an error naming both digests when the current decks' digest differs from the recorded one.

#### Scenario: Replay on unchanged decks
- **WHEN** a recorded batch is replayed against the same decks
- **THEN** the replayed batch equals the record

#### Scenario: Replay after decks changed
- **WHEN** a card is edited after a batch was recorded and the batch is replayed
- **THEN** replay fails with an error naming the recorded and current deck-set digests

### Requirement: Batch size limits
A batch size SHALL be at least 1 and at most the deck capacity. The capacity is the largest size for which every axis has enough distinct cards under shape balance, however the extra draws fall. A size outside these bounds SHALL be rejected with an error naming the capacity.

#### Scenario: Zero
- **WHEN** a batch of size 0 is requested
- **THEN** it is rejected with an error

#### Scenario: Too large
- **WHEN** a batch is requested that would need more `domain` cards than the deck holds
- **THEN** it is rejected with an error naming the capacity

#### Scenario: Seeded decks capacity
- **WHEN** the capacity of the seeded decks is computed
- **THEN** it is 30, limited by the 15-card `domain` deck

### Requirement: Unsatisfiable home field fails loudly
When no unused card on any of a draw's axes lists its `home_field`, drawing SHALL fail with an error naming the position and the field. It SHALL NOT drop the home-field rule or reuse a card.

#### Scenario: Field exhausted
- **WHEN** the decks hold only one card listing `comics` and a batch needs two `comics` home draws
- **THEN** drawing fails with an error naming the position and `comics`

### Requirement: Command-line drawing
The system SHALL provide a command that draws a batch for a given seed and size, prints one line per draw (position, home field and the three card names by axis), and optionally writes the `DrawBatch` record as YAML. When no seed is given, it SHALL choose one and print it so the batch can be reproduced.

#### Scenario: Seeded draw
- **WHEN** the draw command runs with seed 7 and size 12
- **THEN** it prints 12 draw lines followed by the seed and the short deck-set digest, and exits 0

#### Scenario: Unseeded draw
- **WHEN** the draw command runs without a seed
- **THEN** it prints the seed it chose, and rerunning with that seed prints the same batch

#### Scenario: Writing the record
- **WHEN** the draw command runs with an output path
- **THEN** it writes the `DrawBatch` as YAML that validates against the schema and replays to the same batch
