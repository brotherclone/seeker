# Design

## Context

See proposal.md (Why) for the 2026-11-26 duplicate round 4.

How the scheduler reads state today:
- `LineageRecords` scans `paths.debates`, `paths.generations` and `paths.reviews` on disk. The head is whatever those folders hold, so it moves with every `git switch`.
- `RunLog` reads `paths.runs` (git-ignored), and `Cadence` uses only `RunLog.last_advanced()`. These records survive branch switches, but nothing compares them with the outputs on disk. That's the gap the 11-26 trigger slipped through: `runs/` said round 4 had advanced on 11-24, the folders said round 3 was the head, and nothing cross-checked them.
- `LaunchAgent.plist()` uses `config.root` for `WorkingDirectory`, `--project` and `SEEKER_CONFIG`. `SeekerConfig.find()` honours `SEEKER_CONFIG`, else walks up from the working directory.
- The vault location already follows the "env, then `.env`, then `seeker.yaml`" pattern (`SEEKER_VAULT`, `SeekerConfig.vault()`). The workspace setting copies it.

Round outputs are committed by hand at review points on a feature branch. Between reviews they're untracked, so whatever tree the job writes to holds the only copy.

## Goals / Non-Goals

**Goals:**
- No trigger can redo a round because its outputs left the disk. The guard is the safety net and works whatever the workspace.
- In normal operation, the job's tree is one that no agent or person switches branches in, so the guard never has to fire.
- Moving the workspace is a config change plus `workspace create` and `install`.

**Non-Goals:**
- Making the job commit, branch or push. That rule stays. `workspace update` only moves a detached HEAD.
- Stopping people or agents from running `git switch` inside the workspace. Seeker can't enforce that. The guard catches the consequence, and the docs say not to.
- Running more than one lineage or workspace.
- Copying outputs back for review automatically. The docs give the copy commands, and an export helper can come later.

## Decisions

### 1. Schema first: two slots on `ScheduledRun`

```yaml
slots:
  discarded_at:
    range: datetime
    slot_uri: seeker:discardedAt
    description: >-
      When Gabe discarded this trigger's outputs. A discarded record is
      skipped by the missing-output guard and by the cadence check.
    examples:
      - value: "2026-11-27T09:30:00-05:00"
  discard_note:
    range: string
    slot_uri: seeker:discardNote
    description: Why this trigger's outputs were discarded.
    examples:
      - value: "duplicate round 4; kept 2026-11-24"

classes:
  ScheduledRun:
    slots: [..., failure_message, discarded_at, discard_note]
```

Both are optional, so older records load unchanged. Then `seeker/ontology/schedule.py` gains `discarded_at: datetime | None` and `discard_note: str | None` with full `Field` metadata, plus a `discarded` property. `make schema` regenerates SHACL and OWL, and the conformance test covers the slots.

*Alternatives:*
- **A separate `DiscardedRun` record type.** It adds a class and a lookup for one boolean fact about an existing record.
- **Deleting the record.** It loses the history that a round was paid for and thrown away, and the round viewer will want to show that.

### 2. The guard is a check in the trigger, recorded as `failed`

`Scheduler._locked_trigger` runs a new `OutputGuard(config, log).missing()` first, before `LineageRecords.state()`, the report render, the resume, the gate or the cadence check. It takes `RunLog.last_with_outputs()`: the latest record with outcome `advanced` or `budget`, not discarded, and a non-empty `written_paths`. It resolves each path against `config.root` and returns the missing ones. If any are missing, it raises `OutputsMissing(record_path, missing)`. That subclasses the existing exception path, so the record is `failed`, the vault note is written, and the CLI exits 1. The message names each file and gives both remedies, including the exact `seeker-schedule discard runs/<record>.yaml --note "..."` command.

The guard runs before the lineage scan. A tree missing its outputs can also give a misleading `TwoHeads` or `NoHead` error, and "your outputs are gone" is the cause worth reporting.

`RunLog.write` keeps the record's file name. `discard` rewrites the record in place with the same atomic temp-and-replace write, so the guard can name the record file. That needs `RunLog.all()` to return paths with records. It gets a small `RunRecord` model (path plus `ScheduledRun`), not a tuple.

*Alternatives:*
- **A new `ScheduleOutcome` value (`outputs_missing`).** It's more legible, but it means another enum value, note template and status branch, for something that should almost never happen once the workspace exists. `failed` plus a specific message is enough, and the round viewer can match on the message later if needed.
- **Re-deriving the head from `runs/` instead of the folders.** It inverts the design's "records on disk are the truth" rule and breaks hand-made rounds.

### 3. Discarding

The `seeker-schedule discard <record> --note <text>` command:
1. Loads the record.
2. Refuses if it has no outputs, is already discarded, or any of its `written_paths` still exists.
3. Writes `discarded_at` (now) and `discard_note`.

The "files must be gone" rule is what makes discard safe. Discard can't be used to silence the guard while the outputs sit on another branch. Gabe deletes or moves them first, which is a deliberate act.

`Cadence` keeps its interface. `RunLog.last_advanced()` skips discarded records, so the cadence and `status` both stop counting a discarded round.

### 4. The workspace: a detached worktree, located by config

`SeekerConfig.schedule_workspace() -> Path | None` reads `SEEKER_SCHEDULE_WORKSPACE` from the environment, then `.env`, then `schedule.workspace` (new optional `ScheduleConfig` field). It expands `~` and resolves relative paths against `config.root`, exactly like `vault()`. In `.env` on Gabe's Mac: `SEEKER_SCHEDULE_WORKSPACE=~/Sites/seeker-schedule`.

**Detached, not a branch.** A branch can be checked out in only one worktree. Putting `develop` in the workspace would stop the main checkout from ever checking out `develop`. A dedicated branch such as `schedule/literal` invites commits that break gitflow. A detached HEAD at `origin/develop` holds no branch and moves only through `workspace update`.

*Alternatives:*
- **A separate `git clone`.** It works, but it duplicates the object store and has its own remotes to keep fetched. A worktree shares both.
- **Pointing `paths.*` at absolute folders outside git.** The outputs would then never be in a tree that can be committed, and every review would mean copying in anyway. It also changes `seeker.yaml` for every checkout. It's rejected because the trigger would still read the lineage from wherever those paths point, so it fixes nothing the worktree doesn't.

### 5. `workspace create` and `workspace update` (new `seeker/schedule/workspace.py`)

`ScheduleWorkspace(config, git: Git)` wraps a thin, injectable `Git` runner (like `Launchctl`), so tests use a fake or a temporary repo.

**`create`:**
1. Refuse if the path exists.
2. `git fetch origin develop`, then `git worktree add --detach <path> origin/develop`.
3. Copy `.env` if present.
4. Copy `paths.runs/*.yaml`.
5. Copy every file under the configured generations, debates, reports and reviews folders that `git ls-files --others --modified` reports in the source checkout, excluding `scratch/`.
6. `uv sync --project <path>`.

It prints what it copied and the next step, `seeker-schedule install`.

**`update`:**
1. Take `RunLock` in the workspace's runs folder, and refuse if it's held.
2. `git fetch origin develop`.
3. List the files the target commit adds relative to the workspace's HEAD (`git diff --name-only --diff-filter=A HEAD origin/develop`).
4. For each one that exists untracked in the workspace, compare its bytes with `git show origin/develop:<path>`.
5. If all are equal, delete those untracked copies and `git checkout --detach origin/develop`. If any differ, refuse and name them.

Because nothing is lost, the head can't move backwards. The guard runs at the next trigger as usual.

### 6. Commands resolve to the workspace

The CLI loads config as today. If `schedule_workspace()` is set and differs from `config.root`, `run`, `status`, `approve` and `discard` reload config from `<workspace>/seeker.yaml`. If that file doesn't exist, they fail with a `ConfigError` naming the workspace and suggesting `workspace create`. `status` prints `workspace: <path>` first. `install` writes the plist from the workspace's config, so `--project`, `WorkingDirectory`, `SEEKER_CONFIG` and the logs folder all name the workspace. It refuses if the path isn't a worktree of this repository, checked with `git -C <path> rev-parse --git-common-dir` against the main checkout's.

The workspace's own `.env` sets the same `SEEKER_SCHEDULE_WORKSPACE`, so inside it the comparison is equal and nothing is redirected.

### 7. Obsidian notes

- Update `Ontology/ScheduledRun.md` with the two new slots and their ranges, and how a discarded record is treated.
- New `Decisions/2026-11-26 Pin the schedule workspace.md` (`type: decision`, `openspec: pin-schedule-workspace`). It covers the incident, the guard, discard and the detached worktree, the alternatives above, and links to `[[ScheduledRun]]`, `[[ScheduleOutcome]]` and `[[Seeker]]`.
- Add a "superseded in part by" link to it from `Decisions/2026-11-23 Scheduled run every other day.md`.

No prompts or roles change, so there are no model or persona changes to name.

## Risks / Trade-offs

- [Someone runs `git switch` in the workspace anyway] → The guard fails the next trigger loudly instead of re-running a round. `status` shows the missing files and the fix.
- [The workspace drifts behind `develop`, so it runs old code] → Rounds still work, just on older code. `status` prints how many commits the workspace is behind `origin/develop`, and the review procedure ends with `workspace update`.
- [Untracked outputs exist in two trees after `create`] → The docs say the workspace copy is the live one. The main checkout's copies can be deleted once `status` in the workspace shows the right head. `create` doesn't delete from the source.
- [The guard blocks a legitimate manual clean-up] → `discard` exists for that, and requires the files to be gone first.
- [`uv sync` in the workspace needs network at create time] → It's a one-off and done by hand, not at 02:00.

## Migration Plan

1. Land the change on `develop` through a PR.
2. In the main checkout, discard the duplicate: `uv run seeker-schedule discard runs/2026-11-26T020005.yaml --note "duplicate round 4; kept 2026-11-24"`. It qualifies because its three outputs were deleted on 2026-11-26.
3. Set `SEEKER_SCHEDULE_WORKSPACE=~/Sites/seeker-schedule` in the main checkout's `.env`.
4. Run `uv run seeker-schedule workspace create`. It copies `runs/` and any round 5 outputs if they ran before the change lands.
5. Run `uv run seeker-schedule status` and check that the head matches.
6. Run `uv run seeker-schedule install`, and check that the plist names the workspace.
7. Delete the main checkout's now-stale untracked round outputs.

**Rollback:** unset `SEEKER_SCHEDULE_WORKSPACE` and run `install` again, and the agent runs from the repo root as before. The guard stays, since it only adds a check. `git worktree remove` deletes the workspace once its outputs are committed.
