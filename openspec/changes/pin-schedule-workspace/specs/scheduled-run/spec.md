# Spec Delta

## MODIFIED Requirements

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

## ADDED Requirements

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
