# Spec Delta

## Purpose

Defines the topic-card decks the idea engine draws from: one file per independent axis, validated on load, with content digests so every run can record exactly which cards it used.

## ADDED Requirements

### Requirement: One deck file per axis
The system SHALL load decks from YAML files in the `decks/` directory, one file per axis. Each file SHALL declare an axis id that matches its file name stem, a display name, a one-line description, and a non-empty list of cards.

#### Scenario: Deck loads from its file
- **WHEN** `decks/technique.yaml` declares `axis: technique` with a name, description and cards
- **THEN** the loader returns a deck with axis id `technique` containing those cards in file order

#### Scenario: Axis id does not match file name
- **WHEN** `decks/medium.yaml` declares `axis: media`
- **THEN** validation fails with an error naming the file and both ids

#### Scenario: Deck with no cards
- **WHEN** a deck file has an empty or missing `cards` list
- **THEN** validation fails with an error naming the file

### Requirement: Card fields
Each card SHALL have an `id` (lowercase kebab-case) and a non-empty `name`. A card MAY have `synonyms` (list of strings), `tags` (list of lowercase kebab-case strings) and `note` (string). Any other field SHALL be rejected.

#### Scenario: Minimal card
- **WHEN** a card has only `id: granular-synthesis` and `name: granular synthesis`
- **THEN** it loads with empty synonyms and tags and no note

#### Scenario: Card id not kebab-case
- **WHEN** a card has `id: Granular_Synthesis`
- **THEN** validation fails with an error naming the deck, the card and the field

#### Scenario: Unknown card field
- **WHEN** a card includes a field `weight`
- **THEN** validation fails with an error naming the unknown field

### Requirement: Card ids are unique across all decks
Card ids SHALL be unique within the full deck set, not only within a deck, so that a card id alone identifies a card in run records.

#### Scenario: Duplicate within a deck
- **WHEN** `technique.yaml` contains two cards with id `fm-synthesis`
- **THEN** validation fails naming the deck and the duplicate id

#### Scenario: Duplicate across decks
- **WHEN** `tape` appears as a card id in both `medium.yaml` and `historical-artifact.yaml`
- **THEN** validation fails naming both decks and the duplicate id

### Requirement: Synonyms are distinct from the name
A card's synonyms SHALL NOT repeat its name or each other, compared case-insensitively after trimming whitespace. Synonyms feed prior-art query expansion, so duplicates are errors.

#### Scenario: Synonym repeats the name
- **WHEN** card `granular-synthesis` has name `granular synthesis` and synonym `Granular Synthesis`
- **THEN** validation fails naming the card and the synonym

### Requirement: Required starting axes
The deck set SHALL contain at least the axes `technique`, `medium`, `historical-artifact`, `constraint` and `domain`. Additional axis files SHALL be allowed.

#### Scenario: Missing required axis
- **WHEN** `decks/` has no `constraint.yaml`
- **THEN** validation fails naming the missing axis

#### Scenario: Extra axis
- **WHEN** `decks/` also contains a valid `tuning.yaml`
- **THEN** the set loads with six decks and no error

### Requirement: Validation reports every error at once
Validation SHALL collect all errors across all deck files and report them together, each naming the file and, where applicable, the card id. It SHALL NOT stop at the first error.

#### Scenario: Errors in two files
- **WHEN** `technique.yaml` has a bad card id and `domain.yaml` is missing its description
- **THEN** one validation run reports both errors

### Requirement: Deterministic deck digests
The system SHALL compute a digest for each deck and one for the whole set from normalized content: parsed values, with keys sorted and decks ordered by axis id. Formatting, comments and key order in the YAML SHALL NOT change a digest. Any change to a card's fields or to the card order SHALL change it.

#### Scenario: Reformatting leaves digest unchanged
- **WHEN** a deck file's comments, indentation or key order are changed without changing values
- **THEN** that deck's digest and the set digest are unchanged

#### Scenario: Editing a card changes digests
- **WHEN** a synonym is added to one card
- **THEN** that deck's digest and the set digest change, and every other deck's digest is unchanged

### Requirement: Command-line validation
The system SHALL provide a command that validates the deck set. On success it prints each axis with its card count and digest, then the set digest, and exits 0. On failure it prints every error and exits non-zero.

#### Scenario: Valid decks
- **WHEN** the deck validation command runs against valid decks
- **THEN** it prints one line per axis with card count and digest, then the set digest, and exits 0

#### Scenario: Invalid decks
- **WHEN** the deck validation command runs against decks with errors
- **THEN** it prints all errors and exits with a non-zero status

### Requirement: Seed deck size
Each of the five required decks SHALL ship with between 12 and 20 cards. This is a content check on the seeded decks; the validator does not enforce it.

#### Scenario: Seeded decks are in range
- **WHEN** the seeded decks are validated
- **THEN** each required axis reports a card count between 12 and 20
