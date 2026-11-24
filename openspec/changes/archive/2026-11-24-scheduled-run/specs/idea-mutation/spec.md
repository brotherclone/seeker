# Spec Delta

## ADDED Requirements

### Requirement: Mutation stops at its budget
Mutation SHALL check its estimated cost before each child's model call, and SHALL stop without starting it once the cost has reached its budget. The budget is `budget_usd` from config, or `--budget` on the `seeker-mutate` command line. A stopped `Generation` SHALL be saved with `stop_reason` `budget`, and the command SHALL exit with the same distinct status as a debate run stopped at its budget. A finished mutation SHALL leave `stop_reason` unset.

#### Scenario: Budget reached during mutation
- **WHEN** mutation with a $0.30 budget has spent $0.31 after its sixth child
- **THEN** no seventh call is made, the generation is saved with `stop_reason` `budget`, and the command exits with the budget status

#### Scenario: Resume with more budget
- **WHEN** that generation is resumed with `--budget 2`
- **THEN** only the positions without children are sent to the model, and the finished generation has no `stop_reason`

### Requirement: A debate refuses an unfinished mutation
`seeker-debate` SHALL refuse a `Generation` whose `stop_reason` is `budget`, naming the stop reason and the command to resume mutation.

#### Scenario: Debating a stopped mutation
- **WHEN** `seeker-debate` is given a generation that stopped at its budget
- **THEN** it exits non-zero, says mutation stopped at its budget, and makes no API call
