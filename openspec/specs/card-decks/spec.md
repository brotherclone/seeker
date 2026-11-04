# card-decks Specification

## Purpose

Defines the ontology and files for the topic-card decks the idea engine draws from: one deck per independent axis, cards classified by creative field, validated on load, with content digests so every run can record exactly which cards it used.

## Requirements

### Requirement: Deck ontology is published as a LinkML schema
The system SHALL publish a LinkML schema at `schema/seeker.yaml` defining the classes `Card`, `Deck` and `DeckSet`, the enum `CreativeField`, and the types `CardId`, `AxisId`, `Tag` and `Synonym`. Every class, slot, type, enum and permissible value SHALL have a description.

#### Scenario: Schema lints clean
- **WHEN** the schema is linted with the LinkML linter
- **THEN** it reports no errors, and no class, slot, type, enum or permissible value lacks a description

#### Scenario: Deck files are schema instances
- **WHEN** a seeded deck file is validated against the schema with `Deck` as the target class
- **THEN** validation passes

### Requirement: Ontology exports are generated
The system SHALL generate SHACL shapes and an OWL ontology from the schema into `schema/generated/`. Generated files SHALL NOT be edited by hand, and SHALL be regenerated whenever the schema changes.

#### Scenario: Exports match the schema
- **WHEN** the exports are regenerated from the committed schema
- **THEN** the output is identical to the committed files in `schema/generated/`

### Requirement: One deck file per axis
The system SHALL load decks from YAML files in the `decks/` directory, one file per axis. Each file SHALL declare an `axis` that matches its file name stem, a `name`, a one-line `description`, and a non-empty list of `cards`.

#### Scenario: Deck loads from its file
- **WHEN** `decks/technique.yaml` declares `axis: technique` with a name, description and cards
- **THEN** the loader returns a `Deck` with axis `technique` containing those cards in file order

#### Scenario: Axis does not match file name
- **WHEN** `decks/medium.yaml` declares `axis: media`
- **THEN** validation fails with an error naming the file and both values

#### Scenario: Deck with no cards
- **WHEN** a deck file has an empty or missing `cards` list
- **THEN** validation fails with an error naming the file

### Requirement: Card slots
Each `Card` SHALL have an `id` (a `CardId`: lowercase kebab-case) and a non-empty `name`. A `Card` MAY have `synonyms` (`Synonym` values), `fields` (`CreativeField` values), `tags` (`Tag` values: lowercase kebab-case) and a `note`. Any other slot SHALL be rejected.

#### Scenario: Minimal card
- **WHEN** a card has only `id: granular-synthesis` and `name: granular synthesis`
- **THEN** it loads with no synonyms, fields or tags and no note

#### Scenario: Card id not kebab-case
- **WHEN** a card has `id: Granular_Synthesis`
- **THEN** validation fails with an error naming the deck, the card and the slot

#### Scenario: Unknown card slot
- **WHEN** a card includes a slot `weight`
- **THEN** validation fails with an error naming the unknown slot

### Requirement: Creative field vocabulary
`CreativeField` SHALL have exactly these permissible values: `music`, `visual-art`, `film`, `electronics`, `writing`, `comics` and `games`. A card MAY list several fields. A card with no fields is cross-cutting and applies to every field.

#### Scenario: Card in several fields
- **WHEN** card `cellular-automata` lists fields `music`, `visual-art` and `games`
- **THEN** it loads with all three fields

#### Scenario: Unknown field
- **WHEN** a card lists the field `dance`
- **THEN** validation fails with an error naming the card and the unknown value

### Requirement: Card ids are unique across all decks
Card ids SHALL be unique within the full `DeckSet`, not only within a deck, so that a card id alone identifies a card in run records.

#### Scenario: Duplicate within a deck
- **WHEN** `decks/technique.yaml` contains two cards with id `fm-synthesis`
- **THEN** validation fails naming the deck and the duplicate id

#### Scenario: Duplicate across decks
- **WHEN** `tape` appears as a card id in both `decks/medium.yaml` and `decks/historical-artifact.yaml`
- **THEN** validation fails naming both decks and the duplicate id

### Requirement: Synonyms are distinct from the name
A card's synonyms SHALL NOT repeat its name or each other, compared case-insensitively after trimming whitespace. Synonyms feed prior-art query expansion, so duplicates are errors.

#### Scenario: Synonym repeats the name
- **WHEN** card `granular-synthesis` has name `granular synthesis` and synonym `Granular Synthesis`
- **THEN** validation fails naming the card and the synonym

### Requirement: Required starting axes
The `DeckSet` SHALL contain at least the axes `technique`, `medium`, `historical-artifact`, `constraint` and `domain`. Additional axis files SHALL be allowed.

#### Scenario: Missing required axis
- **WHEN** `decks/constraint.yaml` does not exist
- **THEN** validation fails naming the missing axis

#### Scenario: Extra axis
- **WHEN** a valid `decks/tuning.yaml` is added
- **THEN** the set loads with six decks and no error

### Requirement: Validation reports every error at once
Validation SHALL collect all errors across all deck files and report them together, each naming the file and, where applicable, the card id and slot. It SHALL NOT stop at the first error.

#### Scenario: Errors in two files
- **WHEN** `decks/technique.yaml` has a bad card id and `decks/domain.yaml` is missing its description
- **THEN** one validation run reports both errors

### Requirement: Deterministic deck digests
The system SHALL compute a digest for each deck and one for the whole set from normalized content: parsed values with defaults filled in, keys sorted, and decks ordered by axis. Formatting, comments and key order in the YAML SHALL NOT change a digest. Any change to a card's slots or to the card order SHALL change it.

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
The seeded `technique`, `medium`, `historical-artifact` and `constraint` decks SHALL each ship with between 24 and 40 cards. The seeded `domain` deck SHALL ship with between 12 and 20. This is a content check on the seeded decks; the validator does not enforce it.

#### Scenario: Seeded decks are in range
- **WHEN** the seeded decks are validated
- **THEN** each of the four core axes reports 24–40 cards and `domain` reports 12–20

### Requirement: Seed decks cover every creative field
The seeded `technique`, `medium`, `historical-artifact` and `constraint` decks SHALL each contain at least three cards listing each `CreativeField` value. This is a content check on the seeded decks; the validator does not enforce it.

#### Scenario: Field coverage
- **WHEN** field coverage is counted for the four core seeded decks
- **THEN** every deck has at least three cards for each of `music`, `visual-art`, `film`, `electronics`, `writing`, `comics` and `games`
