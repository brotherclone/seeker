# Spec Delta

## Purpose

Puts every `Idea` of a `Generation` through one round of adversarial debate: three critics argue that it has been done, can't be built, or is boring, and an advocate answers them. Each `Debate` is recorded with its citations, usage and cost, so the tournament judges ideas that have already been attacked and defended.

## ADDED Requirements

### Requirement: Debate ontology is published in the LinkML schema
The schema SHALL define:
- the classes `Citation`, `Critique`, `Reply`, `Defense`, `IdeaRevision`, `Debate`, `DebateFailure`, `RoleDigest` and `DebateRun`;
- the enums `CritiqueTarget`, `Severity`, `DefenseMove` and `DefenseOutcome`.

Each element SHALL have a description and a matching Python model or enum that passes the conformance test.

#### Scenario: Ontology lints and conforms
- **WHEN** the schema is linted and the conformance test runs
- **THEN** both pass for every new class and enum

#### Scenario: Debate records are schema instances
- **WHEN** a `DebateRun` record written by the debate command is validated against the schema with `DebateRun` as the target class
- **THEN** validation passes

### Requirement: Critic roles are versioned YAML files
The roles `prosecutor`, `skeptic` and `taste_critic` SHALL each be defined by a YAML file in `prompts/` that validates as a `Role`. No two critic roles SHALL share both `model` and `persona`.

#### Scenario: Critic roles load
- **WHEN** the three critic role files are loaded
- **THEN** each yields a `Role` with its `role_name`, and the three differ in model or persona

#### Scenario: Identical critics are refused
- **WHEN** the skeptic and taste critic files name the same model and persona
- **THEN** the debate is rejected before any call, naming both files

### Requirement: Every idea faces three critiques
For each `Idea` in the `Generation`, the debate SHALL obtain exactly one `Critique` from each of `prosecutor`, `skeptic` and `taste_critic`. Each critic SHALL see the idea's statement, its parts, its card readings, the draw's cards and the `Reading`. It SHALL NOT see the other critiques.

#### Scenario: Three independent critiques
- **WHEN** a debate runs on an idea
- **THEN** its `Debate` holds one `Critique` per critic role, and no critic's prompt contains another critic's text

#### Scenario: One critic fails
- **WHEN** the skeptic's critique is recorded as a `DebateFailure`
- **THEN** the advocate still answers the two remaining critiques, and the idea still enters the tournament; the command output and the survivors report note that it faced only two critiques

#### Scenario: Advocate fails
- **WHEN** the advocate's defense is recorded as a `DebateFailure`
- **THEN** the idea has no `Debate` and does not enter the tournament, and the critiques it faced are kept on the advocate's `DebateFailure` as `discarded_critiques`, so their cost stays recorded

### Requirement: Critiques name a specific failure
Each `Critique` SHALL give:
- a `CritiqueTarget`, saying which part of the idea fails: `subject`, `behavior`, `rationale`, a card reading, or the constraint;
- a `Severity` (`fatal`, `serious` or `minor`);
- a one-sentence `failure`;
- an `argument`.

A critique whose `failure` is missing, longer than one sentence, or only restates the idea SHALL be rejected and retried once, then recorded as a `DebateFailure`.

#### Scenario: Vague critique is retried
- **WHEN** the skeptic answers with `failure` "This might be hard to build."
- **THEN** the answer is rejected as not naming a specific failure, and the skeptic is asked again with that feedback

#### Scenario: Retry also fails
- **WHEN** the retried answer is still invalid
- **THEN** the debate records a `DebateFailure` for that idea and role, with the reason and the usage spent

### Requirement: The prosecutor reads the catalog before searching
Before calling the model, the prosecutor SHALL run the offline prior-art check for the idea's draw against the vault's works catalog. It SHALL include every hit in its prompt: the `WorkId`, the title, the shared cards, and whether the hit is full.

#### Scenario: Catalog hit is offered
- **WHEN** a captured work links two of the draw's cards
- **THEN** the prosecutor's prompt names that work and its shared cards

#### Scenario: Empty catalog
- **WHEN** the catalog has no works sharing two of the draw's cards
- **THEN** the prompt says the catalog has no prior art for this draw, and the prosecutor still runs

### Requirement: The prosecutor's web search is capped and metered
The prosecutor SHALL use the model's web search tool, at most `max_searches` times per idea as set in its role file. The searches made SHALL be recorded in the critique's `Usage` as `web_search_requests`. A role with `max_searches` 0 SHALL NOT be offered the tool.

#### Scenario: Searches are counted
- **WHEN** the prosecutor runs two web searches for an idea
- **THEN** its critique's usage shows `web_search_requests: 2`

#### Scenario: Cap is enforced
- **WHEN** the prosecutor role sets `max_searches: 3`
- **THEN** no prosecutor call is sent with a search limit above 3

### Requirement: Prior-art critiques cite their evidence
A prosecutor `Critique` SHALL carry at least one `Citation` (a URL from its searches, or a `WorkId` from the catalog), or SHALL declare that no prior art was found. A critique that declares none SHALL have severity `minor`. Every cited URL SHALL be one the searches returned in that call, and every cited `WorkId` SHALL exist in the catalog.

#### Scenario: Uncited claim of prior art
- **WHEN** the prosecutor claims severity `fatal` with no citations
- **THEN** the answer is rejected and retried, with feedback that prior-art claims need evidence

#### Scenario: Invented URL
- **WHEN** a citation's URL was not among that call's search results
- **THEN** the answer is rejected and retried, naming the URL

#### Scenario: Nothing found
- **WHEN** the prosecutor finds no prior art
- **THEN** its critique declares none, carries no citations, and has severity `minor`

### Requirement: Prosecutor findings are cached as works
For each cited URL with no matching `url` in the catalog, the debate SHALL write a new `Work` note to the vault's works folder with:
- `captured_by: prosecutor` and today's `captured_on`;
- the citation's title, its URL, and `kind: other`;
- `cards` limited to the cards of the idea's draw that the citation says the work embodies.

The debate SHALL NOT modify an existing note. A note whose file name is taken SHALL get a numeric suffix.

#### Scenario: New finding is captured
- **WHEN** the prosecutor cites a NIME paper whose URL is not in the catalog
- **THEN** a new note appears in `Works/` that loads as a valid `Work` with `captured_by: prosecutor`, and later catalog checks find it

#### Scenario: Known work is not duplicated
- **WHEN** the cited URL already belongs to a captured work
- **THEN** no note is written and the citation names that work's `WorkId`

#### Scenario: Card links stay inside the draw
- **WHEN** a citation says the work embodies a card that is not in the idea's draw
- **THEN** that card is left out of the note's `cards`

### Requirement: The advocate answers every critique
After the three critiques, the `advocate` role SHALL produce one `Defense` holding exactly one `Reply` per critique. Each `Reply` SHALL give a `DefenseMove` (`concede` or `rebut`) and an argument. The `Defense` SHALL end with one `DefenseOutcome`:
- `defended`: the idea is kept as stated;
- `revised`: an `IdeaRevision` is given;
- `withdrawn`: the advocate gives up the idea.

#### Scenario: Every critique gets a reply
- **WHEN** a defense answers only two of three critiques
- **THEN** it is rejected and retried, naming the critique left unanswered

#### Scenario: Conceding a fatal critique
- **WHEN** the advocate concedes a `fatal` critique and gives no revision
- **THEN** the outcome must be `withdrawn`, and any other outcome is rejected

### Requirement: Revisions keep the idea form and the draw
An `IdeaRevision` SHALL restate the idea in the same "a/an X that does Y because Z" form, with `subject`, `behavior` and `rationale`. It SHALL be validated by the same rules as a generated `Idea`. The revision SHALL still use the same three cards and satisfy the constraint card.

#### Scenario: Revision breaks the form
- **WHEN** a revision's statement is two sentences
- **THEN** the defense is rejected and retried with the form rule as feedback

#### Scenario: Revised idea is what gets judged
- **WHEN** a defense has outcome `revised`
- **THEN** the debated idea's final statement is the revision's, and the original is kept in the record

### Requirement: Debate runs record their provenance
A `DebateRun` SHALL record:
- the path and SHA-256 of the `Generation` file it debated;
- a `RoleDigest` for every role file it used;
- the catalog digest at start;
- the git commit, the start time and the tournament seed;
- every `Debate` and `DebateFailure`, in position order.

Ideas the `Generation` recorded as failures SHALL NOT be debated.

#### Scenario: Provenance is complete
- **WHEN** a debate run finishes
- **THEN** its record names the generation file digest and a `RoleDigest` for each of the five debate roles, and the generator's digest stays readable from the pinned `Generation`

### Requirement: Debate runs are written incrementally and can be resumed
When writing to a file, the run SHALL save the `DebateRun` after each `Debate` and after each `Comparison`. Rerunning with the same output path and the same generation digest, role digests and seed SHALL skip finished work and continue. Any mismatch SHALL be rejected, naming the field. The catalog digest MAY differ on resume, because the run's own captured works change it.

#### Scenario: Resume after interruption
- **WHEN** a run is interrupted after 5 of 12 debates and rerun with the same output path
- **THEN** only ideas 6 to 12 are debated before the tournament starts

#### Scenario: Changed role file
- **WHEN** the skeptic role file is edited between the first run and the resume
- **THEN** the resume is rejected, naming the `skeptic` role digest

### Requirement: Runs stop at their budget
A run SHALL check its estimated cost before starting each debate and each comparison, and SHALL stop without starting it once the cost has reached its budget. The overshoot is therefore at most one debate or comparison, and every call made stays recorded. The budget is `budget_usd` from config, or `--budget` on the command line. A stopped run SHALL be saved with its stop reason and SHALL be resumable with a higher budget.

#### Scenario: Budget reached
- **WHEN** a run with a $1.00 budget has spent $1.02 after its seventh debate
- **THEN** no further call is made, the record says it stopped at the budget, and the command exits with a distinct status

#### Scenario: Resume with more budget
- **WHEN** that run is resumed with `--budget 3`
- **THEN** it continues from debate 8

### Requirement: Debate usage and cost are recorded per model
Each `Critique`, `Defense` and `DebateFailure` SHALL record the `model` it ran on and its `Usage`. The `DebateRun` SHALL carry the total `Usage` and an estimated cost. That cost SHALL be the sum of each record's usage priced at its own model's rates, plus its web searches at the per-search price. Any role whose model is unpriced SHALL be rejected before any call.

#### Scenario: Mixed-model totals
- **WHEN** a run uses Haiku for the skeptic and Opus for the advocate
- **THEN** each call's cost uses its own model's prices, and the run total equals their sum plus searches

### Requirement: Command-line debate
The system SHALL provide a `seeker-debate` command. It takes a recorded `Generation` file, writes to `--out PATH` or `--scratch` (`debates/scratch/`, git-ignored), and accepts `--seed` and `--budget`. It SHALL print one line per debate (outcome and the three severities) and a summary of tokens, searches and estimated cost. `--dry-run` SHALL render every debate prompt, report how many calls and comparisons the run would make, make no API call, and need no API key.

#### Scenario: Dry run
- **WHEN** `seeker-debate generations/2026-11-04-round-1-literal.yaml --dry-run` runs
- **THEN** it prints the critic prompts for all 12 ideas and the planned comparison count, and makes no API call

#### Scenario: Debate only
- **WHEN** it runs with `--no-tournament`
- **THEN** it debates every idea and stops before any comparison, leaving a record that a later run can resume into the tournament
