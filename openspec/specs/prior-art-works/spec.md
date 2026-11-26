# prior-art-works Specification

## Purpose

Keeps a catalog of works that already exist as Obsidian notes, each linked to Seeker's cards. The catalog is validated against the ontology, matched to cards locally, and queried as offline prior art for draws, so novelty can be judged against what Gabe has actually seen.

## Requirements

### Requirement: Work ontology is published in the LinkML schema
The schema SHALL define the class `Work`, the enums `WorkKind` and `CaptureSource`, and the type `WorkId`, each with descriptions, with a matching Python model, enums and type that pass the conformance test. A `Work` has:
- `id` (a `WorkId`), `title`, `creators`, `year`, `url`, `kind`, `summary`;
- `fields` (`CreativeField` values);
- `cards` (references to `Card` by `CardId`);
- `captured_by` (a `CaptureSource`) and `captured_on` (a date).

#### Scenario: Ontology lints and conforms
- **WHEN** the schema is linted and the conformance test runs
- **THEN** both pass for `Work`, `WorkKind`, `CaptureSource` and `WorkId`

### Requirement: Works are notes in the vault's works folder
Each `Work` SHALL be one Markdown note in the configured works folder of the Obsidian vault. The note's YAML frontmatter holds `type: work` and the `Work` slots, and its body is free text. The `WorkId` is the note's file name reduced to lowercase kebab-case. A `cards` entry MAY be written as a card id or as an Obsidian wikilink to it (`[[granular-synthesis]]`), and `creators` MAY be written as plain names or wikilinks.

#### Scenario: Wikilinked cards load
- **WHEN** a note `Oramics demo tape (1962).md` has `cards: ["[[oramics]]", "[[tape]]"]`
- **THEN** it loads as a `Work` with id `oramics-demo-tape-1962` and cards `oramics` and `tape`

#### Scenario: Notes that are not works are ignored
- **WHEN** a note in the works folder has no frontmatter, or a `type` other than `work`
- **THEN** it is skipped without error

### Requirement: Work notes are validated against the decks
Loading the works folder SHALL report every problem at once, each naming the note and the field:
- frontmatter that does not validate as a `Work`;
- a `cards` entry that is not a card in the current deck set;
- two notes that reduce to the same `WorkId`.

A folder with no problems SHALL produce a `WorkCatalog`.

#### Scenario: Unknown card
- **WHEN** a work note lists `[[granular-synth]]`
- **THEN** validation reports the note, `cards`, and `granular-synth` as an unknown card

#### Scenario: Problems in two notes
- **WHEN** one note has `year: soon` and another lists an unknown card
- **THEN** one validation run reports both problems

### Requirement: Vault location comes from the environment or config
The vault root SHALL come from `SEEKER_VAULT`, read from the environment or else from the git-ignored `.env` beside `seeker.yaml`. When neither is set, it SHALL fall back to `paths.vault` in `seeker.yaml`. The works and cards folders SHALL come from `vault_folders` in `seeker.yaml`, relative to the vault. Commands that read or write the vault SHALL fail with a clear message when no vault is set, without touching any files.

#### Scenario: Vault from .env
- **WHEN** `.env` contains `SEEKER_VAULT=~/vault` and `seeker.yaml` has `paths.vault: null`
- **THEN** the vault root resolves to the expanded `~/vault`

#### Scenario: Environment overrides config
- **WHEN** `SEEKER_VAULT` is set in the environment and `paths.vault` names a different folder
- **THEN** the environment value is used

#### Scenario: Vault not configured
- **WHEN** `seeker-works validate` runs with no `SEEKER_VAULT` and `paths.vault: null`
- **THEN** it exits non-zero with a message saying to set `SEEKER_VAULT` in `.env`

### Requirement: Card notes are synced into the vault
The system SHALL write one note per card in the deck set to the configured cards folder, named `<card-id>.md`. Each note's frontmatter holds `type: card`, the card's `axis`, `fields` and `tags`, and its name and synonyms as `aliases`. The body holds a managed block with the card's name, axis, note and synonyms.

#### Scenario: First sync
- **WHEN** card notes are synced into an empty cards folder
- **THEN** one note per card exists, and `microsound` is listed in the aliases of `granular-synthesis.md`

### Requirement: Card note resync preserves Gabe's edits
Re-syncing card notes SHALL rewrite only the frontmatter keys Seeker owns and the managed block. It SHALL preserve all other frontmatter keys and all text outside the block, and SHALL never delete a note.

#### Scenario: Personal notes survive a resync
- **WHEN** Gabe adds a paragraph below the managed block and a `rating` property, a card's synonyms change, and the cards are synced again
- **THEN** the note shows the new synonyms, and still contains his paragraph and his `rating` property

#### Scenario: Removed card keeps its note
- **WHEN** a card is removed from the decks and the cards are synced again
- **THEN** its note is left in place, unchanged

### Requirement: Card links can be suggested from a work's text
The system SHALL suggest card links for a work by finding each card's name or synonyms as whole words, case-insensitively, in the work's title, summary and body, excluding cards already linked. Applying suggestions SHALL add them to the note's `cards` property as wikilinks, preserving the rest of the note.

#### Scenario: Synonym found in the body
- **WHEN** a work's body mentions "drawn sound" and the work does not yet link `oramics`
- **THEN** `oramics` is suggested for that work

#### Scenario: Apply suggestions
- **WHEN** suggestions are applied to a work
- **THEN** its `cards` property gains the suggested wikilinks, and its other frontmatter and body are unchanged

### Requirement: Draws can be checked against the catalog
For a draw, the prior-art check SHALL list every work linking at least two of the draw's three cards, marking works that link all three, ordered by the number of shared cards and then by `WorkId`. A batch check SHALL report every draw, including draws with no prior art.

#### Scenario: Pair overlap
- **WHEN** a work links `lumigraph` and `webcomic`, and a draw has `no-keyboard`, `webcomic` and `lumigraph`
- **THEN** the check for that draw lists the work, sharing `webcomic` and `lumigraph`

#### Scenario: No prior art
- **WHEN** no work links two of a draw's cards
- **THEN** the check reports that draw with no works

### Requirement: Catalog digest
A `WorkCatalog` SHALL expose a deterministic digest over its normalized works, ordered by `WorkId`. Note formatting, frontmatter key order and body text outside the `Work` slots SHALL NOT change it.

#### Scenario: Body edits do not change the digest
- **WHEN** only the free-text body of a work note changes
- **THEN** the catalog digest is unchanged

### Requirement: Web Clipper capture template
The repository SHALL include an Obsidian Web Clipper template that creates a `Work` note in the works folder. The template's properties are limited to `type` and `Work` slots, it sets `type: work`, `captured_by: gabe` and `kind: other` (refined by hand), so a freshly clipped note passes work validation.

#### Scenario: Template matches the ontology
- **WHEN** the template's property names are compared with the `Work` slots
- **THEN** every property is `type` or a `Work` slot, and the note path is the configured works folder

### Requirement: Command-line works tools
The system SHALL provide a command with the subcommands:
- `validate`: reports problems, or prints the count and digest of the works;
- `sync-cards`: writes and updates the card notes;
- `suggest [--apply]`: lists or applies card suggestions;
- `check --batch PATH`: prints each draw's prior art.

#### Scenario: Batch check output
- **WHEN** `check` runs on a 12-draw batch file
- **THEN** it prints 12 draw entries, each followed by its overlapping works or "no prior art in the vault"
