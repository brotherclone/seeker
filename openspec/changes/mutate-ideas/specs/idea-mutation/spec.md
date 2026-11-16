# Spec Delta

## Purpose

Turns the survivors of a finished `DebateRun` into a new `Generation` of child ideas, each with recorded `Lineage`, so a later debate and tournament can test whether mutation improved on its parents.

## ADDED Requirements

### Requirement: Mutation ontology is published in the LinkML schema
The schema SHALL define the classes `Lineage` and `MutationOrigin` and the enum `MutationKind`, whose values are exactly `reworking`, `card_swap` and `carried`. Each SHALL have a description and a matching Python model or enum that passes the conformance test.

#### Scenario: Ontology lints and conforms
- **WHEN** the schema is linted and the conformance test runs
- **THEN** both pass for `Lineage`, `MutationOrigin` and `MutationKind`

#### Scenario: Mutated generations are schema instances
- **WHEN** a `Generation` written by the mutate command is validated against the schema with `Generation` as the target class
- **THEN** validation passes

### Requirement: Mutation starts from a finished debate run
Mutation SHALL read a `DebateRun` whose tournament finished, along with the `Generation` that run debated. The run's `survivors` are the parents, in survivor order. A run that stopped at its budget, stopped before its tournament, or whose tournament was skipped SHALL be refused before any call, naming the reason.

#### Scenario: Unfinished run refused
- **WHEN** mutation is asked to read a run whose `stop_reason` is `budget`
- **THEN** it fails, saying the run's tournament has not finished, and no call is made

#### Scenario: Fewer than three survivors
- **WHEN** the run's tournament names two survivors
- **THEN** mutation makes children for those two parents only

### Requirement: The mutator is a versioned role file
Mutation SHALL use a `mutator` role file in the configured prompts folder, validated like every other role file. `RoleName` SHALL include `mutator`. The mutated `Generation` SHALL record the mutator's `role_name`, `model` and `role_digest`, and the parent generation's `Reading`.

#### Scenario: Mutator is recorded
- **WHEN** a mutated generation is written
- **THEN** its `role_name` is `mutator`, its `role_digest` is the SHA-256 of `prompts/mutator.yaml`, and its `reading` equals the parent generation's

### Requirement: Each parent gets reworkings and card swaps
For each parent, mutation SHALL make, in this order, the configured number of reworkings (default 2) and then one card swap per non-constraint card (2). Children SHALL take positions in parent-survivor order, so with three parents, positions 1-4 are the first parent's children.

#### Scenario: Default children
- **WHEN** mutation runs on a run with three survivors and default settings
- **THEN** the mutated generation has 12 children: per parent, two `reworking` and then two `card_swap`

### Requirement: A reworking keeps the parent's cards and reads its debate
A reworking child SHALL use the parent's draw unchanged. Its prompt SHALL show the parent's final statement and parts, its card readings, each critique's failure and argument, and the advocate's reply to each. The second reworking's prompt SHALL also show the first reworking's statement and ask for a different subject or behavior.

#### Scenario: Reworking prompt
- **WHEN** a reworking prompt is rendered for a revised parent
- **THEN** it contains the parent's revised statement, its three critiques' failures and the advocate's replies, and the draw's three cards

#### Scenario: Second reworking sees the first
- **WHEN** the second reworking of a parent is prompted
- **THEN** its prompt contains the first reworking's statement

### Requirement: A card swap replaces one non-constraint card
A card swap SHALL replace one non-constraint card of the parent's draw with a card from the same deck, drawn from the mutation seed. The new draw SHALL keep the parent's axes and home field. At least one of its cards SHALL list the home field. The replacement SHALL NOT be a card already in any draw of the mutated generation.

#### Scenario: Swap keeps the shape
- **WHEN** a card swap replaces the technique card of a constraint-technique-domain draw
- **THEN** the child's draw has the same axes and home field, the same constraint and domain cards, and a different technique card

#### Scenario: Home field preserved
- **WHEN** the replaced card was the only card in the draw listing the home field
- **THEN** the replacement is chosen only from cards in that deck that list the home field

### Requirement: Child draws are reproducible
A mutated generation's draws SHALL be a pure function of the parent run, the mutation seed and the deck set. The mutation seed SHALL default to the parent run's tournament seed. Rebuilding the draws against a changed parent run or a changed deck set SHALL be refused, naming which changed.

#### Scenario: Same inputs, same draws
- **WHEN** the draws are planned twice from the same parent run, seed and decks
- **THEN** both plans have identical draws in identical positions

#### Scenario: Decks changed
- **WHEN** a deck is edited after a mutated generation was written, and the generation is resumed
- **THEN** the resume is refused, naming the deck set digest

### Requirement: Children are validated as ideas
Each child SHALL be an `Idea` in the "a/an X that does Y because Z" form, with one card reading per card of its draw, checked and retried exactly as the generator's output is. A child that is still invalid after one retry SHALL be recorded as a `GenerationFailure` at its position.

#### Scenario: Wrong cards in the readings
- **WHEN** a card-swap child's readings name the replaced card instead of its replacement
- **THEN** the answer is retried once, and recorded as a failure if it is still wrong

### Requirement: Every child records its lineage
Each child `Idea` SHALL carry a `Lineage` naming its parent's position in the parent run and its `MutationKind`. A `card_swap` child's lineage SHALL also name the swapped axis and the replaced card. The mutated `Generation` SHALL carry a `MutationOrigin` with the parent run's path and SHA-256, the mutation seed, and its round. Its round is the parent generation's round plus one, and a generation with no `MutationOrigin` counts as round 1.

#### Scenario: Swap lineage
- **WHEN** a card-swap child of parent 10 replaced `camera-obscura` on the medium axis
- **THEN** its lineage names parent position 10, kind `card_swap`, axis `medium` and replaced card `camera-obscura`

#### Scenario: Round numbers
- **WHEN** mutation runs on a debate of round-1 generation `generations/2026-11-04-round-1-literal.yaml`
- **THEN** the mutated generation's `MutationOrigin` has round 2

### Requirement: Parents are carried into the mutated generation
After the children, the mutated generation SHALL hold each parent as an `Idea` identical to its parent-generation `Idea`, except for its new position and a `Lineage` of kind `carried`. Parents take the positions after the children, in survivor order, and their draws are copied unchanged. Carrying a parent SHALL make no model call.

#### Scenario: Carried parents
- **WHEN** a mutated generation is made from three survivors
- **THEN** positions 13 to 15 hold the three parents in survivor order, each with lineage kind `carried`, and no model call was made for them

### Requirement: Mutated generations are written incrementally and can be resumed
When writing to a file, mutation SHALL save the `Generation` after each child. Rerunning with the same output path, parent run digest, seed, mutator digest, model and deck set SHALL skip covered positions. Any mismatch SHALL be refused, naming the field.

#### Scenario: Resume after interruption
- **WHEN** mutation is interrupted after 5 children and rerun with the same output path
- **THEN** only positions 6 to 12 are sent to the model

#### Scenario: Changed parent run
- **WHEN** the parent run's file changes between the first run and the resume
- **THEN** the resume is refused, naming the parent run digest

### Requirement: Command-line mutation
The system SHALL provide a `seeker-mutate` command. It takes a finished `DebateRun` file, writes to `--out PATH` or `--scratch` (under the generations folder's git-ignored `scratch/`), and accepts `--seed`. It SHALL print one line per child (position, kind, parent, statement) and a summary of tokens and estimated cost. `--dry-run` SHALL print every planned draw and prompt, make no API call, and need no API key.

#### Scenario: Dry run
- **WHEN** `seeker-mutate debates/2026-11-14-round-1-literal.yaml --dry-run` runs
- **THEN** it prints 12 child prompts and the 3 carried parents, and makes no API call

#### Scenario: Debate picks it up
- **WHEN** `seeker-debate` is run on the mutated generation the command wrote
- **THEN** it debates the 12 children and ranks all 15 entrants
