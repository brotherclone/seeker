# Spec Delta

## MODIFIED Requirements

### Requirement: Tournament ontology is published in the LinkML schema
The schema SHALL define the classes `AxisVerdict`, `Comparison`, `Rating` and `Tournament` and the enum `ScoreAxis`. Each SHALL have a description and a matching Python model or enum that passes the conformance test. `ScoreAxis` SHALL have exactly the values `novelty`, `feasibility` and `promise`. `Tournament` SHALL have a `both_orders` slot that defaults to false, so tournaments recorded before two-order judging still load.

#### Scenario: Ontology lints and conforms
- **WHEN** the schema is linted and the conformance test runs
- **THEN** both pass for every new class and enum

#### Scenario: Older tournaments still load
- **WHEN** `debates/2026-11-14-round-1-literal.yaml`, written without `both_orders`, is loaded
- **THEN** it loads, its tournament has `both_orders` false, and its ratings recompute exactly

### Requirement: Pairings
Each comparison SHALL count as one judge call. With `both_orders` set, every scheduled pair SHALL be judged twice, back to back: first in the seeded A/B order, then reversed. Comparisons SHALL fit within `max_comparisons` (default 132: a round robin of 12 entrants in both orders). When not every pair fits, each entrant SHALL get an equal number of seeded opponents. No pair SHALL be scheduled more than once. Without `both_orders`, each pair SHALL be judged once.

#### Scenario: Round robin
- **WHEN** 12 ideas enter with `both_orders` set and the default `max_comparisons`
- **THEN** 132 comparisons are scheduled, each of the 66 pairs judged as A/B and then as B/A

#### Scenario: Reverse follows directly
- **WHEN** a two-order schedule is built
- **THEN** each pair's reversed comparison comes immediately after its first, so a run stopped at its budget leaves at most one pair judged in one order only

#### Scenario: Large batch
- **WHEN** 15 ideas enter with `both_orders` set and `max_comparisons` 132
- **THEN** at most 66 pairs are scheduled, each entrant meets the same number of opponents, and no pair repeats

#### Scenario: Older run replays its schedule
- **WHEN** a run recorded without `both_orders` is resumed
- **THEN** its schedule is rebuilt in one order, matching its recorded comparisons

### Requirement: Survivors report
A finished run SHALL render as a Markdown report in the configured reports folder, giving for each survivor:
- the final statement, and the original if revised;
- its three axis ratings and cards;
- each critique's failure and its reply;
- each citation and its link.

It SHALL also list non-survivors' ratings and the run's provenance and cost. For a mutated generation, each entrant SHALL show its `Lineage`, and each child whether it outrated its parent on promise. Rendering SHALL call no API.

#### Scenario: Report from a finished run
- **WHEN** `seeker-debate report debates/2026-11-12-round-1.yaml` runs
- **THEN** a report appears in `reports/` naming three survivors with their ratings, critiques, replies and citations, and no API call is made

#### Scenario: Report from a mutated round
- **WHEN** the report is rendered for a debate of a mutated generation
- **THEN** every child shows its parent's position, its kind (`reworking` or `card_swap`), and whether its promise rating is above its parent's, and every carried parent is marked `carried`

## ADDED Requirements

### Requirement: The report shows judge health
The survivors report SHALL include a judge-health section. It gives the share of comparisons won by the idea shown as A, per `ScoreAxis`. For a two-order tournament, it also gives the number of pairs on each axis whose two judgments named different winners. It also counts each critic's critiques by `Severity`, and the debates by `DefenseOutcome`.

#### Scenario: Position bias is visible
- **WHEN** the report is rendered for `debates/2026-11-14-round-1-literal.yaml`
- **THEN** its judge-health section shows A won 44 of 66 novelty comparisons, 29 of 66 on feasibility and 34 of 66 on promise

#### Scenario: Split pairs counted
- **WHEN** in a two-order tournament the judge picks A on novelty both times for the pair (3, 7), which means a different idea won each time
- **THEN** that pair counts as one novelty split
