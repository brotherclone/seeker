# Seeker

An idea engine for creative tech. The concept of record is `docs/concept.md`; every change goes through OpenSpec (`openspec/`, `/opsx:*`).

## Ontology first

- Every domain concept is defined in the LinkML schema under `schema/` before any code uses it. The schema is the source of truth.
- Classes, slots, types and enums all carry a `description`. Use `aliases`, `examples` and `see_also` where they clarify meaning.
- SHACL shapes and OWL are generated from the schema into `schema/generated/`, never edited by hand.
- `linkml-lint` must pass.

## Python style

- Use object-oriented Pydantic v2. Every domain concept is a `BaseModel` subclass, or a `StrEnum` for LinkML enums.
- Each model mirrors its LinkML class:
  - the class `title` and docstring come from the class description;
  - each `Field(...)` carries `title`, `description`, `examples` and `json_schema_extra={"slot_uri": ...}` matching its slot.
- Put behavior on the models as methods and properties, not in free functions that take bare data.
- Don't use dataclasses, `NamedTuple` or `TypedDict`.
- No generic typing above the primitive level:
  - no `Any`, no `dict`-shaped payloads, no `TypeVar`/`Generic` classes;
  - containers hold named domain models (`tuple[Card, ...]`);
  - domain scalars use named constrained types that mirror LinkML types (`CardId`, not bare `str`).
- Errors and reports are models too, for example a validation report made of typed errors, not lists of strings.
- A conformance test keeps the Pydantic models and the LinkML schema in sync. Change the schema first.

## Obsidian

- Design thinking and decisions go in Gabe's Obsidian vault under `Seeker/`, currently `/Users/gabrielwalsh/Documents/Claude/Projects/Bracers/Projects/Seeker/`. That path tells agents where to write notes. Code never hard-codes it and reads the vault location from config (see Running locally). Use the obsidian-vault MCP when it's connected; otherwise write the markdown files directly.
- `Seeker/Seeker.md` is the hub. Every other note links back to it.
- `Seeker/Ontology/<Class>.md` holds one note per LinkML class or enum. Each note gives the definition, its slots (with each slot's range), and `[[wikilinks]]` to the related classes. Update these notes in the same change as the schema.
- `Seeker/Decisions/YYYY-MM-DD <title>.md` records each decision: context, the decision, the alternatives considered, and links to the concepts it touches and to the OpenSpec change.
- `Seeker/Notes/` holds loose thinking.
- Use frontmatter with `type` (`hub`, `concept`, `decision`, `note`), `tags` and `openspec` (a change name, when there is one).

## Git workflow (gitflow)

- `main` holds releases only. `develop` is the integration branch.
- Do all work on `feature/<openspec-change-name>` branches cut from `develop`, one per OpenSpec change. Merge them back into `develop` through a pull request.
- Releases go `release/<version>` from `develop` → `main`, tagged `v<version>`, then merged back into `develop`. Urgent fixes go `hotfix/<name>` from `main` → `main` and `develop`.
- Never commit directly to `develop` or `main`. The only exception was the initial OpenSpec setup.

## Running locally

- While Seeker is experimental it runs on Gabe's Mac. The nightly job is a launchd LaunchAgent, and the API key lives in the macOS Keychain or a git-ignored `.env`. A run moves to the cloud only once it proves out.
- Read every location from config (vault, `decks/`, `batches/`, outputs). Never hard-code a path, so moving a run is a config change.
- The Obsidian vault is the store for captured works and prior art: one note per work, with frontmatter matching the LinkML `Work` class.
- Each nightly run has a hard spend cap, $5 per night by default. The run's cost meter stops the run cleanly when it reaches the cap.
