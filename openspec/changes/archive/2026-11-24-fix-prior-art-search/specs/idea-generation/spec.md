# Spec Delta

## MODIFIED Requirements

### Requirement: Generation ontology is published in the LinkML schema
The schema SHALL define:
- the classes `Idea`, `CardReading`, `Generation`, `GenerationFailure`, `Role`, `ReadingGuidance` and `Usage`;
- the enums `Reading`, `Effort`, `RoleName` and `SearchTool`;
- the types `ModelId` and `GitCommit`.

`RoleName` SHALL name every role. `Usage` counts `web_search_requests` (default 0). `Idea.lineage`, `Generation.mutation` and `Role.search_tool` are optional. Each element SHALL have a description and a matching Python model or type passing the conformance test.

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

#### Scenario: Search tool values
- **WHEN** `SearchTool` is read from the schema
- **THEN** its values are exactly `basic` (results go straight to the model) and `filtered` (results are filtered by model-written code before the model sees them)

### Requirement: Roles are versioned YAML files
A role SHALL be defined by a YAML file in `prompts/` that validates as a `Role`. The file gives the `RoleName`, `ModelId`, persona, system prompt, a positive output-token limit, an `Effort` level, and one `ReadingGuidance` per `Reading` value. It MAY give `max_searches` (default 0). A role with `max_searches` above 0 SHALL give a `search_tool`; a role with 0 SHALL NOT.

#### Scenario: Generator role loads
- **WHEN** `prompts/generator.yaml` is loaded
- **THEN** it yields a `Role` named `generator` with guidance for `literal`, `loose` and `metaphorical`, and `max_searches` 0

#### Scenario: Missing guidance
- **WHEN** a role file omits guidance for `metaphorical`
- **THEN** loading fails, naming the file and the missing reading

#### Scenario: Negative search limit
- **WHEN** a role file sets `max_searches: -1`
- **THEN** loading fails, naming the file and `max_searches`

#### Scenario: Searching role without a tool
- **WHEN** a role file sets `max_searches: 3` and no `search_tool`
- **THEN** loading fails, naming the file and `search_tool`

#### Scenario: Tool without searches
- **WHEN** a role file sets `search_tool: basic` and `max_searches: 0`
- **THEN** loading fails, naming the file and `search_tool`
