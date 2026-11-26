# Spec Delta

## MODIFIED Requirements

### Requirement: Debate ontology is published in the LinkML schema
The schema SHALL define:
- the classes `Citation`, `Critique`, `Reply`, `Defense`, `IdeaRevision`, `Debate`, `DebateFailure`, `RoleDigest` and `DebateRun`;
- the enums `CritiqueTarget`, `Severity`, `DefenseMove` and `DefenseOutcome`.

`Debate` SHALL have an optional `carried_from` slot. Each element SHALL have a description and a matching Python model or enum that passes the conformance test.

#### Scenario: Ontology lints and conforms
- **WHEN** the schema is linted and the conformance test runs
- **THEN** both pass for every new class and enum

#### Scenario: Debate records are schema instances
- **WHEN** a `DebateRun` record written by the debate command is validated against the schema with `DebateRun` as the target class
- **THEN** validation passes

### Requirement: Every idea faces three critiques
For each `Idea` in the `Generation` that is not carried from a parent run, the debate SHALL obtain exactly one `Critique` from each of `prosecutor`, `skeptic` and `taste_critic`. Each critic SHALL see the idea's statement, its parts, its card readings, the draw's cards and the `Reading`. It SHALL NOT see the other critiques.

#### Scenario: Three independent critiques
- **WHEN** a debate runs on an idea
- **THEN** its `Debate` holds one `Critique` per critic role, and no critic's prompt contains another critic's text

#### Scenario: One critic fails
- **WHEN** the skeptic's critique is recorded as a `DebateFailure`
- **THEN** the advocate still answers the two remaining critiques, and the idea still enters the tournament; the command output and the survivors report note that it faced only two critiques

#### Scenario: Advocate fails
- **WHEN** the advocate's defense is recorded as a `DebateFailure`
- **THEN** the idea has no `Debate` and does not enter the tournament, and the critiques it faced are kept on the advocate's `DebateFailure` as `discarded_critiques`, so their cost stays recorded

## ADDED Requirements

### Requirement: Carried ideas keep their parent's debate
When a mutated `Generation` holds an `Idea` with `Lineage` of kind `carried`, the debate run SHALL copy that parent's `Debate` from the parent run named in the generation's `MutationOrigin`. The copy is identical except for its position and a `carried_from` slot holding the parent position. Copying SHALL make no model call and add no usage. The parent run's file SHALL match the pinned SHA-256, or the run SHALL be refused before any call.

#### Scenario: Parent debate copied
- **WHEN** `seeker-debate` runs on a mutated generation whose position 13 carries parent 10
- **THEN** the run's debate at position 13 has parent 10's critiques, defense and final statement, `carried_from` 10, and no call is made for it

#### Scenario: Parent run changed
- **WHEN** the parent run's file no longer matches the digest in the generation's `MutationOrigin`
- **THEN** the debate run is refused, naming the parent run digest, and no call is made

#### Scenario: Dry run counts only children
- **WHEN** `seeker-debate --dry-run` runs on a mutated generation of 12 children and 3 carried parents
- **THEN** it renders critic prompts for the 12 children only, and plans the tournament for 15 entrants
