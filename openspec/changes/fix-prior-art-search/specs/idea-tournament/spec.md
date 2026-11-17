# Spec Delta

## MODIFIED Requirements

### Requirement: The report shows judge health
The survivors report SHALL include a judge-health section. It gives the share of comparisons the idea shown as A won, per `ScoreAxis`, and for a two-order tournament the pairs per axis whose two judgments disagreed. It counts each critic's critiques by `Severity` and the debates by `DefenseOutcome`. It gives prior-art search health from the run's own debates.

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
