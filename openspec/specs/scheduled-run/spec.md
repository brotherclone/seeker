# scheduled-run Specification

## Purpose

Runs Seeker's mutate → debate → report loop unattended on Gabe's Mac. Each scheduled trigger advances a lineage by one round, within a spend cap and a cadence, and pauses at review points until Gabe signs off.

## Requirements

### Requirement: Scheduling ontology is published in the LinkML schema
The schema SHALL define the classes `ScheduledRun` and `ReviewSignOff` and the enum `ScheduleOutcome`. The enum's values SHALL be exactly `advanced`, `budget`, `too_soon`, `awaiting_review`, `locked` and `failed`. `Generation` SHALL gain an optional `stop_reason` slot with range `StopReason`. `ScheduledRun` SHALL have the optional slots `discarded_at` (datetime) and `discard_note` (string). Each SHALL have a description and a matching Python model or enum that passes the conformance test.

#### Scenario: Ontology lints and conforms
- **WHEN** the schema is linted and the conformance test runs
- **THEN** both pass for `ScheduledRun` (with `discarded_at` and `discard_note`), `ReviewSignOff`, `ScheduleOutcome` and `Generation.stop_reason`

#### Scenario: Older generations still load
- **WHEN** the round-1, round-2 and round-3 generation records are loaded
- **THEN** they validate, and `stop_reason` is unset

#### Scenario: Older trigger records still load
- **WHEN** the `ScheduledRun` records written before this change are loaded
- **THEN** they validate, and `discarded_at` and `discard_note` are unset

### Requirement: The lineage head is found from the records
A scheduled run SHALL take as its lineage head the finished `DebateRun` in the configured debates folder whose generation has the highest `MutationOrigin.round`. A round-1 generation has round 1. Records under `scratch/` SHALL be ignored. If more than one finished run shares the highest round, the run SHALL stop as `failed` and name every candidate.

#### Scenario: Head after round 3
- **WHEN** debates hold the finished round 1, 2 and 3 literal runs
- **THEN** the head is the round-3 literal run

#### Scenario: Two heads
- **WHEN** two finished runs share the highest round
- **THEN** the run records `failed`, names both files, and makes no API call

### Requirement: A scheduled run advances one round
When it is due, a scheduled run SHALL mutate the head's survivors into a new `Generation`, debate and rank it, and render its report, using the same records, seeds and resume checks as the `seeker-mutate` and `seeker-debate` commands. Its files SHALL be named `<date>-round-<n>-<reading>.yaml` (`.md` for the report) in the configured generations, debates and reports folders.

#### Scenario: Round 4 from round 3
- **WHEN** a due run starts on 2026-11-30 with the round-3 literal run as head and its review signed off
- **THEN** it writes `generations/2026-11-30-round-4-literal.yaml`, `debates/2026-11-30-round-4-literal.yaml` and `reports/2026-11-30-round-4-literal.md`, and records `advanced`

### Requirement: One spend cap covers the whole round
A scheduled run SHALL spend at most `budget_usd` (default $5) per trigger across mutation, debate and tournament together. The debate's budget SHALL be the cap less the mutation's recorded cost in this trigger. A run that reaches the cap SHALL stop cleanly and record `budget`, and no call shall start after the cap is reached.

#### Scenario: Mutation leaves less for the debate
- **WHEN** mutation in this trigger costs $0.62 against a $5.00 cap
- **THEN** the debate and tournament run with a $4.38 budget

#### Scenario: Cap reached mid-tournament
- **WHEN** the estimated spend reaches $5.00 during the tournament
- **THEN** no further comparison starts, the debate run records it stopped at the budget, and the `ScheduledRun` records `budget`

### Requirement: An unfinished round resumes before a new one
A round is in progress when a `Generation` in the generations folder names the head as its parent run. That holds when its mutation is incomplete or its debate run is missing or unfinished. A finished head with no report SHALL have its report rendered first, which needs no API call. A trigger SHALL resume an in-progress round from its saved records under a fresh cap, whatever the cadence, and SHALL NOT start a new round while one is in progress.

#### Scenario: Resume the next night
- **WHEN** Monday's round stopped at the cap with 40 comparisons left, and Tuesday's trigger fires
- **THEN** Tuesday resumes Monday's debate run with a $5 cap, makes only the remaining calls, and records `advanced` once the report is written

### Requirement: Rounds run no more often than the cadence
A trigger SHALL make no API call and record `too_soon` unless the last `ScheduledRun` recorded as `advanced` and not discarded ended at least `schedule.cadence_days` days ago, less 12 hours. With no such record, the run is due. `cadence_days` SHALL be at least 1, and its default is 2.

#### Scenario: Every other day
- **WHEN** the last round advanced at 03:10 on Monday, and triggers fire at 02:00 on Tuesday and Wednesday with `cadence_days` 2
- **THEN** Tuesday records `too_soon` (22h 50m since then), and Wednesday runs (46h 50m since then)

#### Scenario: First scheduled run
- **WHEN** no `ScheduledRun` record exists
- **THEN** the cadence check passes

#### Scenario: A discarded round does not hold back the next
- **WHEN** the 2026-11-24 trigger advanced round 4, the 2026-11-26 trigger advanced a duplicate round 4 that was then discarded, and a trigger fires at 02:00 on 2026-11-27
- **THEN** the cadence is measured from the 2026-11-24 record, and the trigger is due

### Requirement: The lineage pauses at review points
When the head's round is a multiple of `schedule.review_every` (default 3) and no `ReviewSignOff` names the head, a trigger SHALL make no API call and record `awaiting_review`. A sign-off SHALL clear only that review point. The next pause comes `review_every` rounds later.

#### Scenario: Round 3 waits for Gabe
- **WHEN** the head is the round-3 literal run and no sign-off names it
- **THEN** the trigger records `awaiting_review` and spends nothing

#### Scenario: After sign-off
- **WHEN** Gabe has signed off the round-3 run
- **THEN** rounds 4 and 5 run on the cadence, and the lineage pauses again at round 6

### Requirement: Sign-off is a recorded review
`seeker-schedule approve <debate-run>` SHALL write a `ReviewSignOff` recording the run's path and SHA-256, the time, and an optional `--note`, in the configured reviews folder. It SHALL refuse a run that is not finished, or not the current head.

#### Scenario: Approve the head
- **WHEN** Gabe runs `seeker-schedule approve debates/2026-11-23-round-3-literal.yaml --note "keep the obscura line"`
- **THEN** a sign-off naming that run's digest is written, and the next due trigger advances to round 4

#### Scenario: Approve a run that changed
- **WHEN** the approved run's file is edited after sign-off
- **THEN** the sign-off no longer matches its digest, and the lineage stays at `awaiting_review`

### Requirement: Every trigger is recorded
Every trigger SHALL write a `ScheduledRun` record to the configured runs folder before it exits. The record holds its start and end times, its `ScheduleOutcome`, the head it started from, the files it wrote or resumed, its estimated cost and, for `failed`, the error message. A failure SHALL be recorded, not lost, and the command SHALL exit non-zero.

#### Scenario: Failure is recorded
- **WHEN** the API key is missing at 02:00
- **THEN** a `ScheduledRun` with outcome `failed` and the missing-key message is written, and the command exits non-zero

### Requirement: Runs do not overlap
A scheduled run SHALL hold an exclusive lock in the runs folder for as long as it runs. A second run that starts while the lock is held SHALL record `locked` and exit without an API call. A lock left by a process that is no longer running SHALL be taken over.

#### Scenario: Manual run during the scheduled one
- **WHEN** Gabe starts `seeker-schedule run` while the 02:00 run is still debating
- **THEN** his run records `locked` and makes no call

### Requirement: A run that does work leaves a vault note
Each trigger that ends `advanced`, `budget`, `awaiting_review` or `failed` SHALL write a Markdown note to the vault's configured runs folder, named by its date and outcome, with frontmatter `type: note` and the outcome. A trigger recorded as `too_soon` or `locked` SHALL write no note.

#### Scenario: Skipped night
- **WHEN** a trigger records `too_soon`
- **THEN** no vault note is written

### Requirement: The run note summarises the round
A run note's body SHALL give the round, the cost against the cap, the survivors with their promise ratings, the prosecutor's search health, a link to the report, and `[[Seeker]]`.

#### Scenario: Night with a new round
- **WHEN** round 4 finishes at $3.80
- **THEN** a note in the vault's `Runs/` gives round 4, $3.80 of $5.00, the three survivors, the search health, the report path, and links to `[[Seeker]]`

### Requirement: The API key can come from the Keychain
The API key SHALL be read from `ANTHROPIC_API_KEY`, else the macOS Keychain generic password with service `seeker` and account `anthropic`, else `.env`. The key SHALL never be written to the plist, the logs, any record or any note.

#### Scenario: Key only in the Keychain
- **WHEN** the environment and `.env` have no key and the Keychain holds one
- **THEN** the run uses the Keychain key

### Requirement: The LaunchAgent is installed from config
`seeker-schedule install` SHALL write and load a per-user LaunchAgent that runs `seeker-schedule run` through `uv run` daily at `schedule.hour` (default 2). It runs from the configured schedule workspace when one is set, else from the repository root. Its stdout and stderr SHALL go to the configured logs folder. Every path in the plist SHALL be worked out at install time from config and the `uv` on `PATH`. `uninstall` SHALL unload and remove it.

#### Scenario: Install
- **WHEN** Gabe runs `uv run seeker-schedule install` with no workspace configured
- **THEN** a LaunchAgent firing daily at 02:00 is loaded, and its plist names the repo root, `uv` and the logs folder, and holds no API key

#### Scenario: Install with a workspace
- **WHEN** a schedule workspace is configured and exists, and Gabe runs `uv run seeker-schedule install` from the main checkout
- **THEN** the plist's working directory, `--project` and `SEEKER_CONFIG` name the workspace, and its logs go to the workspace's logs folder

#### Scenario: Workspace configured but missing
- **WHEN** a schedule workspace is configured but the folder is not a git worktree of this repository
- **THEN** `install` refuses, names the path, suggests `seeker-schedule workspace create`, and leaves any loaded agent unchanged

#### Scenario: Moved config
- **WHEN** `seeker.yaml` sets a different logs folder and `install` runs again
- **THEN** the reinstalled plist uses the new folder, with no code change

### Requirement: The scheduled run never commits
A scheduled run SHALL make no git commit, branch or push. Its files stay in the working tree for Gabe to commit on a feature branch.

#### Scenario: After a round
- **WHEN** a round finishes
- **THEN** `git log` is unchanged, and the new generation, debate, report and run record show as untracked or modified

### Requirement: Status shows where the lineage stands
`seeker-schedule status` SHALL print the head, its round and reading, the gate state, the last `ScheduledRun` outcome and cost, when the next round is due, and whether the LaunchAgent is loaded. It SHALL make no API call and need no API key.

#### Scenario: Paused at round 3
- **WHEN** status runs with the round-3 run as head and no sign-off
- **THEN** it reports round 3, awaiting review, and the command to approve it
### Requirement: A trigger refuses to redo a round whose outputs vanished
Before resuming, checking the cadence or calling the API, a trigger SHALL find the latest `ScheduledRun` with outcome `advanced` or `budget` that is not discarded. If any of its `written_paths` is missing from disk, the trigger SHALL record `failed` with a message naming every missing path, make no API call, and exit non-zero.

#### Scenario: Outputs removed by a branch switch
- **WHEN** the latest advanced record names `debates/2026-11-24-round-4-literal.yaml`, that file is no longer on disk, and a due trigger fires
- **THEN** the trigger records `failed`, names the missing file, makes no API call, and writes no generation, debate or report

#### Scenario: Outputs present
- **WHEN** every file the latest advanced record names is on disk
- **THEN** the guard passes and the trigger goes on to its usual checks

#### Scenario: No earlier work
- **WHEN** no `advanced` or `budget` record exists
- **THEN** the guard passes

### Requirement: The guard's failure is visible
A guard failure SHALL write the vault note that every `failed` trigger writes. Its message SHALL say the two ways forward: restore the files, or discard the record with `seeker-schedule discard`.

#### Scenario: Morning after a missing-output failure
- **WHEN** a trigger failed because round-4 outputs were missing
- **THEN** the vault `Runs/` note and `seeker-schedule status` both show the missing paths and the `discard` command for that record

### Requirement: A trigger's outputs can be discarded
`seeker-schedule discard <run-record> --note "<reason>"` SHALL set `discarded_at` and `discard_note` on that `ScheduledRun` record and keep every other field. It SHALL refuse a record that has no `written_paths`, that is already discarded, or any of whose `written_paths` still exist on disk. The note is required.

#### Scenario: Discard the duplicate round 4
- **WHEN** the duplicate round-4 files have been deleted and Gabe runs `seeker-schedule discard runs/2026-11-26T020005.yaml --note "duplicate round 4; kept 2026-11-24"`
- **THEN** that record gains `discarded_at` and the note, and the guard and the cadence check now skip it

#### Scenario: Files still on disk
- **WHEN** Gabe discards a record whose debate run is still in the debates folder
- **THEN** the command refuses, names the file, and leaves the record unchanged

### Requirement: The schedule workspace is configured
The schedule workspace SHALL be read from `SEEKER_SCHEDULE_WORKSPACE` in the environment, else in `.env`, else from `schedule.workspace` in `seeker.yaml`. It is unset by default. A relative path SHALL resolve against the config file's folder, and `~` SHALL be expanded. No code SHALL hard-code its location.

#### Scenario: Workspace from .env
- **WHEN** `.env` sets `SEEKER_SCHEDULE_WORKSPACE=~/Sites/seeker-schedule`
- **THEN** the schedule workspace is the expanded path, whatever `schedule.workspace` says

#### Scenario: Nothing configured
- **WHEN** no source sets a workspace
- **THEN** the schedule behaves as before this change and runs from the repository root

### Requirement: Schedule commands act on the workspace
When a schedule workspace is configured, `seeker-schedule run`, `status`, `approve` and `discard` SHALL load the workspace's `seeker.yaml` and read and write the workspace's records, whichever checkout they are invoked from. If the workspace does not exist, they SHALL fail with a message naming it and make no API call.

#### Scenario: Manual run from the main checkout
- **WHEN** a workspace is configured and Gabe runs `uv run seeker-schedule run` in the main checkout
- **THEN** the trigger reads the lineage from the workspace, and any outputs and the `ScheduledRun` record are written there

#### Scenario: Status from the main checkout
- **WHEN** a workspace is configured and an agent runs `uv run seeker-schedule status` in the main checkout
- **THEN** it reports the workspace's head, gate and last trigger, and names the workspace path

### Requirement: The workspace can be created
`seeker-schedule workspace create` SHALL make the configured workspace a git worktree of this repository, detached at `develop`. It SHALL copy in the `.env`, the `ScheduledRun` records, and every round output under the configured generations, debates, reports and reviews folders that is not committed on `develop`. It SHALL then install the workspace's locked dependencies. It SHALL refuse if the path already exists.

#### Scenario: Create with an uncommitted round 5
- **WHEN** `develop` holds rounds 1–4, the main checkout has untracked round-5 outputs and `runs/` records, and Gabe runs `seeker-schedule workspace create`
- **THEN** the workspace is detached at `develop`, holds the round-5 outputs, the `runs/` records and the `.env`, and `seeker-schedule status` there reports round 5 as head

#### Scenario: Path taken
- **WHEN** the configured workspace path already exists
- **THEN** create refuses and changes nothing

### Requirement: The workspace moves only to develop and loses nothing
`seeker-schedule workspace update` SHALL hold the run lock, fetch, and move the workspace's detached checkout to the latest `develop`. An uncommitted file that the new commit also adds SHALL be removed first only when the two are byte-identical. If any differs, or the lock is held, update SHALL refuse and change nothing. It SHALL never create, switch to or commit on a branch.

#### Scenario: Round outputs merged after review
- **WHEN** rounds 5 and 6 were copied to a feature branch, merged into `develop` unchanged, and Gabe runs `workspace update`
- **THEN** the workspace moves to the new `develop`, its round 5–6 files are now the committed copies, and the head is still round 6

#### Scenario: A committed copy differs
- **WHEN** `develop` holds a round-5 debate run that differs from the workspace's uncommitted one
- **THEN** update refuses, names the file, and the workspace stays where it was

#### Scenario: Update during a round
- **WHEN** the 02:00 trigger holds the lock and Gabe runs `workspace update`
- **THEN** update refuses and changes nothing
