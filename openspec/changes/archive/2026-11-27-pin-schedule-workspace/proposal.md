# Proposal

## Why

The scheduled run finds the lineage head by reading round outputs from whatever the repository's working tree holds. On 2026-11-26 it re-ran round 4 for about $4.26. The 2026-11-24 round-4 outputs had been committed on another feature branch, and switching the checkout to `feature/round-viewer` removed them from disk. The head fell back to round 3, and the cadence check, which reads only the git-ignored `runs/` records, still let the trigger through. Each round costs $4–5 and forks the lineage. The same accident can repeat on any branch switch in the checkout launchd runs from, and agents switch branches there routinely.

## What Changes

- **Missing-output guard.** Before it does any work, a trigger checks the most recent `ScheduledRun` that wrote files (`advanced` or `budget`) and is not discarded. If any of its `written_paths` is missing from disk, the trigger records `failed`, names the missing files, makes no API call, writes the vault note and exits non-zero. A round whose outputs vanished is never silently redone.
- **Discarding a trigger's outputs.** `seeker-schedule discard <run-record> --note "..."` marks a `ScheduledRun` as discarded, for when Gabe deliberately drops a round, like the duplicate round 4. The guard and the cadence check both ignore discarded records. The command refuses while any of the record's files still exist, so it can't hide outputs that are merely on another branch.
- **A pinned schedule workspace.** The job runs from a dedicated git worktree of the repo, checked out detached at `develop`, that agents never switch branches in. Its location is config (`SEEKER_SCHEDULE_WORKSPACE` in the environment or `.env`, else `schedule.workspace` in `seeker.yaml`), never a hard-coded path.
  - `seeker-schedule workspace create` makes the worktree. It copies in `.env`, the `runs/` records and any round outputs that aren't committed yet, then runs `uv sync` there.
  - `seeker-schedule workspace update` moves the worktree to the latest `develop` under the run lock. It drops an uncommitted output only when `develop` now holds an identical committed copy, and refuses otherwise.
  - `install` points the LaunchAgent at the workspace when one is configured.
  - `run`, `status`, `approve` and `discard` act on the workspace's records wherever they're invoked, so a manual run from the main checkout can't write outputs into the wrong tree.
- **Docs.** `docs/scheduling.md` covers the workspace, the guard, discarding, and how round outputs get from the workspace onto a feature branch at review.

Engine stage touched: the scheduled run (`seeker-schedule`). No agent role, deck, prompt or debate behavior changes.

Reproducibility is unchanged: rounds use the same records, digests and seeds. Resumability improves. A round stopped at the cap stays resumable because its partial records live in a tree nobody switches, and a trigger that finds a round's records gone stops instead of guessing.

Ontology: `ScheduledRun` gains two optional slots, `discarded_at` (datetime) and `discard_note` (string). Records written before this change load unchanged. `ScheduleOutcome` is unchanged: the guard records `failed`.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `scheduled-run`:
  - it adds the missing-output guard, discarding a trigger, and the schedule workspace with its `create` and `update` commands;
  - the cadence check skips discarded records;
  - the LaunchAgent runs from the workspace when one is configured;
  - the scheduling ontology gains `ScheduledRun.discarded_at` and `ScheduledRun.discard_note`.

## Impact

- Code: `seeker/schedule/` (`trigger.py`, `log.py`, `cli.py`, `launchd.py`, plus a new `workspace.py`), `seeker/config.py` (workspace setting), `seeker/ontology/schedule.py`.
- Schema: `schema/seeker.yaml` (two slots on `ScheduledRun`), regenerated SHACL and OWL in `schema/generated/`.
- Tests: `tests/test_schedule_*.py` and the conformance test.
- Docs: `docs/scheduling.md`. In the vault: `Ontology/ScheduledRun.md`, a new Decision note, and a link from `Decisions/2026-11-23 Scheduled run every other day.md`.
- Gabe's Mac: a new worktree at the configured path, and a reinstalled LaunchAgent. The 2026-11-26 trigger record gets discarded.
- New dependency: none. It uses the `git` CLI, which is already present.
