# idea-generation Specification

## Purpose

Turns each `Draw` of a `DrawBatch` into one structured, validated `Idea` at a chosen `Reading`. Each pass is recorded as a `Generation` with its inputs pinned and its token usage and estimated cost measured, so ideas can be traced and compared across readings, prompts and models.

## Requirements

### Requirement: Generation ontology is published in the LinkML schema
The schema SHALL define:
- the classes `Idea`, `CardReading`, `Generation`, `GenerationFailure`, `Role`, `ReadingGuidance` and `Usage`;
- the enums `Reading`, `Effort` and `RoleName`;
- the types `ModelId` and `GitCommit`.

`RoleName` SHALL name every role, and `Usage` SHALL count `web_search_requests` (default 0). Every element SHALL have a description and a matching Python model or type that passes the conformance test.

#### Scenario: Ontology lints and conforms
- **WHEN** the schema is linted and the conformance test runs
- **THEN** both pass for every new class, enum and type

#### Scenario: Role names cover every debate role
- **WHEN** `RoleName` is read from the schema
- **THEN** its values are `generator`, `prosecutor`, `skeptic`, `taste_critic`, `advocate` and `judge`

#### Scenario: Generation records are schema instances
- **WHEN** a `Generation` record written by the generate command is validated against the schema with `Generation` as the target class
- **THEN** validation passes

#### Scenario: Older records still load
- **WHEN** `generations/2026-11-04-round-1-literal.yaml`, written without `web_search_requests`, is loaded
- **THEN** it loads, and every `Usage` in it has `web_search_requests` 0

### Requirement: Reading vocabulary
`Reading` SHALL have exactly the values `literal`, `loose` and `metaphorical`, each with a description:
- `literal`: cards mean what they name;
- `loose`: cards may be taken by their spirit;
- `metaphorical`: cards may stand for something they evoke.

#### Scenario: Unknown reading
- **WHEN** a generation is requested with reading `surreal`
- **THEN** it is rejected, naming the three valid readings

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

### Requirement: One idea per draw in the X/Y/Z form
For each `Draw`, the generator SHALL produce one `Idea` whose `statement` is a single sentence of at most 60 words. The idea also carries:
- its `subject` (X), `behavior` (Y) and `rationale` (Z);
- the draw's `position`;
- exactly one `CardReading` per drawn card, in the draw's order, each naming the card's `CardId` and giving a non-empty `interpretation`.

#### Scenario: Valid idea
- **WHEN** the model returns a one-sentence statement, the three parts, and a reading for each of the draw's three cards
- **THEN** an `Idea` is recorded at that draw's position

#### Scenario: Two sentences
- **WHEN** the model returns a statement containing two sentences
- **THEN** the response is invalid

#### Scenario: Wrong or missing card
- **WHEN** the card readings omit a drawn card or name a card that isn't in the draw
- **THEN** the response is invalid

### Requirement: The reading shapes the prompt and is recorded
A generation SHALL use one `Reading`, `literal` by default. The prompt SHALL include the role's guidance for that reading and no other reading's guidance, and the `Generation` SHALL record the reading.

#### Scenario: Metaphorical prompt
- **WHEN** prompts are rendered with reading `metaphorical`
- **THEN** each prompt contains the metaphorical guidance text and neither the literal nor the loose guidance text

#### Scenario: Default reading
- **WHEN** no reading is given
- **THEN** the generation records `literal`

### Requirement: The prompt presents each card fully
Each draw's prompt SHALL present every drawn card with its axis, name, synonyms, creative fields and note when present, plus the draw's home field. This way the generator sees the same meaning a person reading the deck sees.

#### Scenario: Card note reaches the prompt
- **WHEN** a drawn card has a note
- **THEN** the rendered prompt for that draw contains the note text

### Requirement: Invalid output is retried once, then recorded as a failure
When a model response is invalid, the generator SHALL retry once, sending back the validation errors. If the retry is also invalid, or the call fails, the generator SHALL record a `GenerationFailure` (the position and the reason) and continue with the next draw.

#### Scenario: Recovered on retry
- **WHEN** the first response has two sentences and the retry is valid
- **THEN** an `Idea` is recorded, and the usage of both calls is counted

#### Scenario: Failed twice
- **WHEN** both responses for draw 4 are invalid
- **THEN** a `GenerationFailure` for position 4 is recorded, and draws 5 onward are still generated

### Requirement: Generations record their provenance
A `Generation` SHALL record:
- the full `DrawBatch` it was generated from;
- the `Reading`, the `RoleName` and the role's `ModelId`;
- the SHA-256 digest of the role file's content;
- the git commit when the working tree is a git checkout;
- the time it was generated.

#### Scenario: Pinned inputs
- **WHEN** a generation is written
- **THEN** its record contains the batch's seed and deck-set digest, the reading, the model id and the role-file digest

#### Scenario: Prompt change is visible
- **WHEN** `prompts/generator.yaml` is edited and another generation is run
- **THEN** the two records carry different role-file digests

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

### Requirement: Generations are written incrementally and can be resumed
When writing to a file, the generator SHALL rewrite the `Generation` record after each draw completes. Re-running against an existing record with the same batch, reading and role-file digest SHALL skip the positions that already have an idea and generate only the rest. A mismatch SHALL be rejected rather than mixing inputs.

#### Scenario: Resume after interruption
- **WHEN** a 12-draw generation is interrupted after 5 ideas and rerun with the same output path
- **THEN** only draws 6 to 12 are sent to the model, and the record ends with 12 positions covered

#### Scenario: Mismatched resume
- **WHEN** the same output path is reused with a different reading
- **THEN** the run is rejected, naming the recorded and requested readings

### Requirement: Command-line generation
The system SHALL provide a command that generates ideas for:
- a recorded `DrawBatch` file, or a fresh batch from a seed and size;
- a `--reading`;
- writing with `--out PATH` or `--scratch` (to `generations/scratch/`, which is git-ignored).

It SHALL print one line per idea and a summary of positions, failures, tokens and estimated cost. `--dry-run` SHALL render every prompt and make no API call.

#### Scenario: Dry run
- **WHEN** the generate command runs with `--dry-run` for a 12-draw batch
- **THEN** it prints the 12 rendered prompts, makes no API call, and needs no API key

#### Scenario: Scratch output is ignored by git
- **WHEN** a generation is written with `--scratch`
- **THEN** the file lands in `generations/scratch/` and `git check-ignore` reports it ignored
