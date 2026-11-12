# Spec Delta

## Purpose

Ranks the debated ideas of a `DebateRun` through blind pairwise `Comparison`s. Each comparison updates one Elo ladder per `ScoreAxis` (novelty, feasibility, promise), and the axes are never blended. The top survivors go into a report for Gabe's review.

## ADDED Requirements

### Requirement: Tournament ontology is published in the LinkML schema
The schema SHALL define the classes `AxisVerdict`, `Comparison`, `Rating` and `Tournament` and the enum `ScoreAxis`. Each SHALL have a description and a matching Python model or enum that passes the conformance test. `ScoreAxis` SHALL have exactly the values `novelty`, `feasibility` and `promise`.

#### Scenario: Ontology lints and conforms
- **WHEN** the schema is linted and the conformance test runs
- **THEN** both pass for every new class and enum

### Requirement: Withdrawn ideas do not compete
Only ideas whose `Debate` ended `defended` or `revised` SHALL enter the tournament. A revised idea SHALL compete in its revised form. A tournament with fewer than two entrants SHALL be skipped and recorded as skipped.

#### Scenario: Withdrawn idea is left out
- **WHEN** 12 ideas were debated and 2 were withdrawn
- **THEN** the tournament has 10 entrants

### Requirement: Comparisons are blind
The judge SHALL see two debated ideas labelled only `A` and `B`. For each, it sees the final statement, its parts and card readings, the three objections and the replies to them. Objections SHALL be shown in a seeded shuffled order, with no role names, models or personas. Which idea is `A` SHALL be decided by the tournament seed.

#### Scenario: No role names reach the judge
- **WHEN** a comparison prompt is rendered
- **THEN** it contains none of the role names, model ids or persona texts of the debate roles

#### Scenario: Seeded order
- **WHEN** the same debate run's tournament is rendered twice with the same seed
- **THEN** every comparison has the same pairs, the same A/B order and the same objection order

### Requirement: The judge rules on each axis separately
Each `Comparison` SHALL hold exactly one `AxisVerdict` per `ScoreAxis`, naming the winning idea's position and giving a one-sentence reason. Ties SHALL NOT be allowed. An answer that skips an axis, names a position not in the pair, or offers a tie SHALL be retried once. It SHALL then be recorded as a failed comparison that leaves every rating unchanged.

#### Scenario: Missing axis
- **WHEN** the judge answers with verdicts for novelty and promise only
- **THEN** the answer is rejected and retried, naming `feasibility`

### Requirement: Pairings
With at most `max_comparisons` possible pairs, every pair of entrants SHALL meet once (round robin). The default `max_comparisons` is 66, which is round robin for 12 entrants. With more possible pairs, each entrant SHALL get an equal number of seeded opponents, as many as fit in `max_comparisons`. No pair SHALL meet twice.

#### Scenario: Round robin
- **WHEN** 12 ideas enter
- **THEN** 66 comparisons are scheduled, one per pair

#### Scenario: Large batch
- **WHEN** 30 ideas enter with `max_comparisons` 66
- **THEN** each idea is scheduled for the same number of comparisons, at most 66 are scheduled in total, and no pair repeats

### Requirement: Elo ratings per axis
Every entrant SHALL start at rating 1500 on each `ScoreAxis`. Comparisons SHALL update each axis's ratings with the standard Elo formula, with K = 32, in the tournament's seeded schedule order. Ratings SHALL be recomputable exactly from the stored comparisons. Each `Rating` SHALL record position, axis, rating, wins and losses. No combined score SHALL be computed or stored.

#### Scenario: Recompute matches
- **WHEN** a finished tournament's ratings are recomputed from its stored comparisons
- **THEN** every rating, win and loss matches the record

#### Scenario: Axes stay separate
- **WHEN** idea 3 wins on novelty and loses on feasibility against idea 7
- **THEN** idea 3's novelty rating rises and its feasibility rating falls, and no other axis changes

### Requirement: Survivors are the top three by promise
The tournament SHALL name as survivors the three entrants with the highest `promise` rating. Ties SHALL be broken by promise wins, then by position. A tournament with fewer than three entrants SHALL name them all. Each survivor SHALL be reported with all three axis ratings.

#### Scenario: Survivors chosen
- **WHEN** a 10-entrant tournament finishes
- **THEN** the run records exactly three survivor positions, ordered by promise rating

### Requirement: Survivors report
The system SHALL render a Markdown report to the configured reports folder for a finished run. For each survivor, the report gives:
- the final statement, plus the original if it was revised;
- the three axis ratings and the cards;
- each critique's failure and the reply to it;
- every citation, with its link.

The report SHALL also list the non-survivors with their ratings, and the run's provenance and cost. Rendering SHALL make no API call.

#### Scenario: Report from a finished run
- **WHEN** `seeker-debate report debates/2026-11-12-round-1.yaml` runs
- **THEN** a report appears in `reports/` naming three survivors with their ratings, critiques, replies and citations, and no API call is made
