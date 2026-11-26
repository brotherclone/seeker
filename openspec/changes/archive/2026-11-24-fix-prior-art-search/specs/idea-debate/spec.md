# Spec Delta

## MODIFIED Requirements

### Requirement: Debate ontology is published in the LinkML schema
The schema SHALL define:
- the classes `Citation`, `Critique`, `Reply`, `Defense`, `IdeaRevision`, `Debate`, `DebateFailure`, `RoleDigest`, `DebateRun`, `SearchReport` and `SearchError`;
- the enums `CritiqueTarget`, `Severity`, `DefenseMove` and `DefenseOutcome`.

`Debate.carried_from` and `Critique.search` SHALL be optional. Each element SHALL have a description and a matching Python model or enum that passes the conformance test.

#### Scenario: Ontology lints and conforms
- **WHEN** the schema is linted and the conformance test runs
- **THEN** both pass for every new class and enum

#### Scenario: Debate records are schema instances
- **WHEN** a `DebateRun` record written by the debate command is validated against the schema with `DebateRun` as the target class
- **THEN** validation passes

#### Scenario: Records without search reports still load
- **WHEN** `debates/2026-11-14-round-1-literal.yaml` and `debates/2026-11-16-round-2-literal.yaml` are loaded
- **THEN** both load, and no critique in them has a `search`

### Requirement: The prosecutor's web search is capped and metered
The prosecutor SHALL use web search, with the tool version its role file names in `search_tool`, at most `max_searches` times per idea. The searches made SHALL be recorded in the critique's `Usage` as `web_search_requests`. A role with `max_searches` 0 SHALL NOT be offered the tool. The prosecutor role file SHALL set `search_tool: basic`.

#### Scenario: Searches are counted
- **WHEN** the prosecutor runs two web searches for an idea
- **THEN** its critique's usage shows `web_search_requests: 2`

#### Scenario: Cap is enforced
- **WHEN** the prosecutor role sets `max_searches: 3`
- **THEN** no prosecutor call is sent with a search limit above 3

#### Scenario: Tool version follows the role file
- **WHEN** the prosecutor role sets `search_tool: basic`
- **THEN** every prosecutor call offers the basic web search tool, with no code-execution filtering

### Requirement: Prior-art critiques cite their evidence
A prosecutor `Critique` SHALL carry at least one `Citation` (a URL from its searches, or a `WorkId` from the catalog), or SHALL declare that no prior art was found. A critique that declares none SHALL have severity `minor`. Every cited URL SHALL be one the searches returned in that prosecution's calls, the retry included, and every cited `WorkId` SHALL exist in the catalog.

#### Scenario: Uncited claim of prior art
- **WHEN** the prosecutor claims severity `fatal` with no citations
- **THEN** the answer is rejected and retried, with feedback that prior-art claims need evidence

#### Scenario: Invented URL
- **WHEN** a citation's URL was not among the search results of any of that prosecution's calls
- **THEN** the answer is rejected and retried, naming the URL

#### Scenario: Nothing found
- **WHEN** the prosecutor finds no prior art
- **THEN** its critique declares none, carries no citations, and has severity `minor`

#### Scenario: Retry cites the first call's results
- **WHEN** the prosecutor's first answer is rejected, and its retry, which runs no new search, cites a URL that the first call's searches returned
- **THEN** the citation is accepted

## ADDED Requirements

### Requirement: Search outcomes are recorded
Every critique from a role that searches SHALL carry a `SearchReport`. It gives the number of search results the call returned (`results_returned`), and a `SearchError` for each search that failed. Each `SearchError` gives an `error_code` and an `error_message`. A failure SHALL be recorded, never dropped, whether the search tool returned an error or code running the searches stopped with an error. Critiques from roles that do not search SHALL have no `SearchReport`. When a role that searches produces no valid answer, its `DebateFailure` SHALL carry the `SearchReport` of every call it made, the failed call excepted.

#### Scenario: Results counted
- **WHEN** the prosecutor's two searches return 9 results each
- **THEN** its critique's `SearchReport` shows 18 results returned and no errors

#### Scenario: Search limit exceeded
- **WHEN** a search in the prosecutor's call returns an error with code `max_uses_exceeded`
- **THEN** the critique's `SearchReport` holds a `SearchError` with `error_code` `max_uses_exceeded`

#### Scenario: Search code failed
- **WHEN** code running the prosecutor's searches stops with "Server tool use limit exceeded during code execution."
- **THEN** the critique's `SearchReport` holds a `SearchError` with `error_code` `search_code_failed` whose `error_message` is that text

#### Scenario: Retry call fails
- **WHEN** the prosecutor's first answer, whose searches returned 9 results and one `max_uses_exceeded` error, is rejected, and the retry's model call fails
- **THEN** the prosecutor's `DebateFailure` has a `SearchReport` showing 9 results returned and that `SearchError`

#### Scenario: Non-searching critic
- **WHEN** the skeptic's critique is recorded
- **THEN** it has no `SearchReport`

### Requirement: Search health is printed after a run
The `seeker-debate` run summary SHALL give the number of prosecutions whose searches returned at least one result, out of all prosecutions in the run, and the number that recorded a `SearchError`.

#### Scenario: Summary line
- **WHEN** a run of 12 debates ends in which 11 prosecutions returned results and 1 recorded an error
- **THEN** the summary includes "prior-art search: 11 of 12 with results, 1 with errors"
