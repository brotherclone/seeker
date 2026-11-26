# Spec Delta

## MODIFIED Requirements

### Requirement: Generation ontology is published in the LinkML schema
The schema SHALL define:
- the classes `Idea`, `CardReading`, `Generation`, `GenerationFailure`, `Role`, `ReadingGuidance` and `Usage`;
- the enums `Reading`, `Effort` and `RoleName`;
- the types `ModelId` and `GitCommit`.

`RoleName` SHALL name every role, and `Usage` SHALL count `web_search_requests` (default 0). `Idea.lineage` and `Generation.mutation` SHALL be optional slots. Each element SHALL have a description and a matching Python model or type that passes the conformance test.

#### Scenario: Ontology lints and conforms
- **WHEN** the schema is linted and the conformance test runs
- **THEN** both pass for every new class, enum and type

#### Scenario: Role names cover every debate role
- **WHEN** `RoleName` is read from the schema
- **THEN** its values are `generator`, `prosecutor`, `skeptic`, `taste_critic`, `advocate`, `judge` and `mutator`

#### Scenario: Generation records are schema instances
- **WHEN** a `Generation` record written by the generate command is validated against the schema with `Generation` as the target class
- **THEN** validation passes

#### Scenario: Older records still load
- **WHEN** `generations/2026-11-04-round-1-literal.yaml`, written without `web_search_requests`, `lineage` or `mutation`, is loaded
- **THEN** it loads, every `Usage` in it has `web_search_requests` 0, and no idea has a lineage

### Requirement: Locations, prices and credentials come from config
Seeker SHALL read from the repository's `seeker.yaml`, resolving relative paths against it:
- the decks, batches, generations, debates, reports and vault locations;
- the model price table, including the per-search price;
- the run budget `budget_usd` (default 5.00);
- `mutation.reworkings` (default 2).

The API key SHALL come from `ANTHROPIC_API_KEY` in the environment or the git-ignored `.env`, never from `seeker.yaml`. A missing key SHALL be reported before any call is made.

#### Scenario: Missing key
- **WHEN** a generation runs without an API key
- **THEN** it fails with an error explaining where the key is read from, and no call is made

#### Scenario: Key in seeker.yaml is refused
- **WHEN** `seeker.yaml` contains an `api_key` entry
- **THEN** loading the config fails, saying keys belong in the environment or `.env`

#### Scenario: Budget default
- **WHEN** `seeker.yaml` sets no `budget_usd`
- **THEN** the loaded config's budget is 5.00

#### Scenario: Mutation default
- **WHEN** `seeker.yaml` has no `mutation` section
- **THEN** the loaded config asks for 2 reworkings per parent
