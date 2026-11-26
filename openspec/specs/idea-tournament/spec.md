# idea-tournament Specification

## Purpose
Ranks the debated ideas of a `DebateRun` through blind pairwise `Comparison`s. Each comparison updates one Elo ladder per `ScoreAxis` (novelty, feasibility, promise), and the axes are never blended. The top survivors go into a report for Gabe's review.

## Requirements

### Requirement: Tournament ontology is published in the LinkML schema
The schema SHALL define the classes `AxisVerdict`, `Comparison`, `Rating` and `Tournament` and the enum `ScoreAxis`. Each SHALL have a description and a matching Python model or enum that passes the conformance test. `ScoreAxis` SHALL have exactly the values `novelty`, `feasibility` and `promise`. `Tournament` SHALL have a `both_orders` slot that defaults to false, so tournaments recorded before two-order judging still load.

#### Scenario: Ontology lints and conforms
- **WHEN** the schema is linted and the conformance test runs
- **THEN** both pass for every new class and enum

#### Scenario: Older tournaments still load
- **WHEN** `debates/2026-11-14-round-1-literal.yaml`, written without `both_orders`, is loaded
- **THEN** it loads, its tournament has `both_orders` false, and its ratings recompute exactly

### Requirement: Withdrawn ideas do not compete
Only ideas whose `Debate` ended `defended` or `revised` SHALL enter the tournament. A revised idea SHALL compete in its revised form. A tournament with fewer than two entrants SHALL be skipped and recorded as skipped.

#### Scenario: Withdrawn idea is left out
- **WHEN** 12 ideas were debated and 2 were withdrawn
- **THEN** the tournament has 10 entrants

### Requirement: Comparisons are blind
The judge SHALL see two debated ideas labelled only `A` and `B`. For each, it sees the final statement, its parts and card readings, the three objections and the replies to them. Objections SHALL be shown in a seeded shuffled order, with no role names, models or personas. Which idea is `A` SHALL be decided by the tournament seed.

#### Scenario: No role names reach the judge
- **WHEN** a comparison prompt is rendered
- **THEN** it contains none of the role names, `ModelId`s or persona texts of the debate roles

#### Scenario: Seeded order
- **WHEN** the same debate run's tournament is rendered twice with the same seed
- **THEN** every comparison has the same pairs, the same A/B order and the same objection order

### Requirement: The judge rules on each axis separately
Each `Comparison` SHALL hold exactly one `AxisVerdict` per `ScoreAxis`, naming the winning idea's position and giving a one-sentence reason. Ties SHALL NOT be allowed. An answer that skips an axis, names a position not in the pair, or offers a tie SHALL be retried once. It SHALL then be recorded as a failed comparison that leaves every rating unchanged.

#### Scenario: Missing axis
- **WHEN** the judge answers with verdicts for novelty and promise only
- **THEN** the answer is rejected and retried, naming `feasibility`

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

### Requirement: The report shows judge health
The survivors report SHALL include a judge-health section. It gives the share of comparisons that the idea shown as A won, per `ScoreAxis`, and for a two-order tournament the pairs per axis whose two judgments disagreed. It counts each critic's critiques by `Severity` and the debates by `DefenseOutcome`. It gives prior-art search health from the run's own debates.

#### Scenario: Position bias is visible
- **WHEN** the report is rendered for `debates/2026-11-14-round-1-literal.yaml`
- **THEN** its judge-health section shows A won 44 of 66 novelty comparisons, 29 of 66 on feasibility and 34 of 66 on promise

#### Scenario: Split pairs counted
- **WHEN** in a two-order tournament the judge picks A on novelty both times for the pair (3, 7), which means a different idea won each time
- **THEN** that pair counts as one novelty split

#### Scenario: Search health shown
- **WHEN** the report is rendered for a run whose 12 prosecutions include 11 with results, 1 with a `SearchError`, and 30 URL citations in all
- **THEN** its judge-health section shows 11 of 12 prosecutions with results, 1 with errors, and 30 citations

#### Scenario: Older runs say search was not recorded
- **WHEN** the report is rendered for `debates/2026-11-16-round-2-literal.yaml`, whose critiques have no `SearchReport`
- **THEN** the search-health line says search outcomes were not recorded for this run, instead of reporting zero results
