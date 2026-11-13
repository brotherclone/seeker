# Spec Delta

## MODIFIED Requirements

### Requirement: Generation ontology is published in the LinkML schema
The schema SHALL define:
- the classes `Idea`, `CardReading`, `Generation`, `GenerationFailure`, `Role`, `ReadingGuidance` and `Usage`;
- the enums `Reading`, `Effort` and `RoleName`;
- the types `ModelId` and `GitCommit`.

`RoleName` SHALL have the values `generator`, `prosecutor`, `skeptic`, `taste_critic`, `advocate` and `judge`. `Usage` SHALL include `web_search_requests`, a non-negative count defaulting to 0, so records written before this slot existed still load.

Every element SHALL have a description, and each SHALL have a matching Python model or type that passes the conformance test.

#### Scenario: Ontology lints and conforms
- **WHEN** the schema is linted and the conformance test runs
- **THEN** both pass for every new class, enum and type

#### Scenario: Generation records are schema instances
- **WHEN** a `Generation` record written by the generate command is validated against the schema with `Generation` as the target class
- **THEN** validation passes

#### Scenario: Older records still load
- **WHEN** `generations/2026-11-04-round-1-literal.yaml`, written without `web_search_requests`, is loaded
- **THEN** it loads, and every `Usage` in it has `web_search_requests` 0

### Requirement: Roles are versioned YAML files
A role SHALL be defined by a YAML file in `prompts/` that validates as a `Role`. The file gives the `RoleName`, `ModelId`, persona, system prompt, a positive output-token limit, an `Effort` level, and exactly one `ReadingGuidance` per `Reading` value. It MAY give `max_searches`, a non-negative number of web searches allowed per call, which defaults to 0.

#### Scenario: Generator role loads
- **WHEN** `prompts/generator.yaml` is loaded
- **THEN** it yields a `Role` named `generator` with guidance for `literal`, `loose` and `metaphorical`, and `max_searches` 0

#### Scenario: Missing guidance
- **WHEN** a role file omits guidance for `metaphorical`
- **THEN** loading fails, naming the file and the missing reading

#### Scenario: Negative search limit
- **WHEN** a role file sets `max_searches: -1`
- **THEN** loading fails, naming the file and `max_searches`

### Requirement: Usage and estimated cost are recorded
Each `Idea` and `GenerationFailure` SHALL carry the `Usage` of every model call made for it: input, output, cache-read and cache-write tokens, and web-search requests. The `Generation` SHALL carry the total `Usage` and an estimated cost in US dollars, computed from the price table in config. Web-search requests SHALL be priced at the table's per-search rate. A generation whose model has no price in config SHALL be rejected before any call is made.

#### Scenario: Totals add up
- **WHEN** a generation finishes
- **THEN** its total usage equals the sum of the usage on all its ideas and failures, and its estimated cost equals the total usage priced at the configured rates

#### Scenario: Unpriced model
- **WHEN** the role names a model with no entry in the price table
- **THEN** the generation is rejected naming the model, and no API call is made

#### Scenario: Searches are priced
- **WHEN** a usage has 3 web-search requests and the table's per-search price is $0.01
- **THEN** its estimated cost includes $0.03 for searches on top of its tokens

### Requirement: Locations, prices and credentials come from config
Seeker SHALL read the following from `seeker.yaml` at the repository root, resolving relative paths against that file:
- the decks, batches, generations, debates, reports and vault locations;
- the model price table, including the per-search price;
- the run budget `budget_usd` (default 5.00).

The API key SHALL come from the `ANTHROPIC_API_KEY` environment variable or a git-ignored `.env` file, never from `seeker.yaml`. A missing key SHALL be reported before any call is made.

#### Scenario: Missing key
- **WHEN** a generation runs without an API key
- **THEN** it fails with an error explaining where the key is read from, and no call is made

#### Scenario: Key in seeker.yaml is refused
- **WHEN** `seeker.yaml` contains an `api_key` entry
- **THEN** loading the config fails, saying keys belong in the environment or `.env`

#### Scenario: Budget default
- **WHEN** `seeker.yaml` sets no `budget_usd`
- **THEN** the loaded config's budget is 5.00
