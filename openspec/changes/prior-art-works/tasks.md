# Tasks

## 1. Ontology

- [ ] 1.1 Add the `WorkId` type, the `WorkKind` and `CaptureSource` enums, the new slots (`title`, `creators`, `year`, `url`, `kind`, `summary`, `captured_by`, `captured_on`), and the `Work` class with `slot_usage` for `id` and `cards` to `schema/seeker.yaml` per design decision 1, every element described. Run `make schema`. Verify that `linkml-lint` and `tests/test_schema.py` pass, or record the fallback to `linked_cards` if the toolchain rejects the `slot_usage`.
- [ ] 1.2 Extend the conformance test: `date` maps to `datetime.date`, `uri` maps to the `Url` named type, and induced `slot_usage` ranges are respected. Verify the existing tests still pass.
- [ ] 1.3 Implement `WorkId`, `Url`, `WorkKind`, `CaptureSource` and `Work` in `seeker/ontology/`, exported, with rich metadata. Verify that the conformance test passes, and that unit tests cover the bounds and the defaults (empty `cards`, `fields` and `creators`; optional `year`, `url` and `summary`).
- [ ] 1.4 Write the Obsidian concept note `Seeker/Ontology/Work.md`, linked to `[[Card]]`, `[[CreativeField]]`, `[[DeckSet]]` and the hub. Verify that its slot table matches the schema.

## 2. Notes and config

- [ ] 2.1 Add `vault_folders` to `SeekerConfig` (defaulting to `Seeker/Works` and `Seeker/Cards`), plus `VaultLayout` and `VaultNotConfigured`. Resolve the vault from `SEEKER_VAULT` (environment, then `.env`), falling back to `paths.vault`. Update the `seeker.yaml` comment to point at `.env`. Verify unit tests: the folder defaults and overrides; a `.env` value; the environment beating both `.env` and `paths.vault`; `~` expansion; relative-to-vault folders; and the not-configured message naming `SEEKER_VAULT`.
- [ ] 2.2 Implement `NoteFile`: parse frontmatter and body; atomic write only on change; preserve unknown keys and their order; a managed-block helper. Verify round-trip tests: unchanged notes are not rewritten, unknown keys and body text survive, a note with no frontmatter gets some, and Unicode survives.

## 3. Works catalog

- [ ] 3.1 Implement `WorkNotes` loading: skip non-work notes; convert wikilinks to ids; derive the id from the file name; treat empty values as absent; validate each note; then the set-level checks (unknown cards against the `DeckSet`, duplicate ids). Collect everything into a `WorksReport`. Verify fixture-vault tests for every loading and validation scenario in the spec, including two problems in two notes reported together.
- [ ] 3.2 Implement `WorkCatalog`, with lookup and a digest over the normalized works. Verify tests: the digest is stable, unchanged by body-only and key-order edits, and changed by editing `cards`.

## 4. Card notes

- [ ] 4.1 Implement `CardNotes.sync(deck_set, layout)`. It writes one note per card, with the owned frontmatter keys (`type`, `card_id`, `axis`, `fields`, `tags`, `aliases`) and the managed block, and never deletes. Verify tests:
  - a first sync creates 153 notes from the seeded decks;
  - `microsound` is in the aliases of `granular-synthesis`;
  - a resync preserves Gabe's paragraph and his `rating` key, while updating the synonyms;
  - a second sync with no deck change writes nothing.

## 5. Matching and prior-art check

- [ ] 5.1 Implement `CardMatcher` (whole-word, case-insensitive, with exact case for short single words) and the suggestion and apply flow. Verify tests: "drawn sound" suggests `oramics`; "Karplus-Strong" matches; "CA" doesn't match "ca." inside ordinary words; already-linked cards are skipped; applying adds wikilinks and keeps the rest of the note byte-identical.
- [ ] 5.2 Implement `PriorArtHit`, `DrawPriorArt` and `BatchCheck`. Verify tests: a pair overlap is found, a full (three-card) hit is marked, the sort order is right, and draws with no prior art are still reported. Run against `batches/2026-11-04-round-1.yaml` with a fixture vault.

## 6. Command line, capture template and docs

- [ ] 6.1 Implement `seeker-works` with `validate`, `sync-cards`, `suggest [--apply]` and `check --batch`, plus the console script. Verify CLI tests against a fixture vault for each subcommand, the exit codes, and the vault-not-configured message.
- [ ] 6.2 Add `capture/seeker-work.clipper.json` per design decision 7. Verify a test that its property names are `type` or `Work` slots, and that its `path` equals the default works folder.
- [ ] 6.3 Write `docs/works.md` covering: setup (`SEEKER_VAULT` in `.env`), importing the Web Clipper template, the capture-then-suggest flow, card notes and what Seeker owns in them, `check`, and the frontmatter-comment caveat. Verify that the documented commands run as written against a fixture vault.

## 7. Record the decision

- [ ] 7.1 Write `Seeker/Decisions/2026-11-05 Works in the vault.md` and update the hub. Verify that the note links to the hub, `[[Work]]` and `prior-art-works`.

## Workflow follow-up

- **Manual check by Gabe:** with `SEEKER_VAULT` already in `.env`, run `uv run seeker-works sync-cards`, import the template into the Web Clipper, clip one real page (a Bandcamp or itch.io page, say), then run `uv run seeker-works suggest --apply` and `uv run seeker-works validate`.
- Open a PR from `feature/prior-art-works` into `develop`, and archive after merge.
