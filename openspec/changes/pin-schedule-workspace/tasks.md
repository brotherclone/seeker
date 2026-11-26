# Tasks

## 1. Ontology

- [ ] 1.1 In `schema/seeker.yaml`, add the optional slots `discarded_at` (datetime) and `discard_note` (string) to `ScheduledRun`, with descriptions, slot URIs and examples (design decision 1). Run `make schema`. Verify that `make lint` and `tests/test_schema.py` pass.
- [ ] 1.2 Add `discarded_at` and `discard_note` to `ScheduledRun` in `seeker/ontology/schedule.py`, with full `Field` metadata, plus a `discarded` property. Verify:
  - `tests/test_conformance.py` passes;
  - every record in `runs/`, and a fixture copy of `runs/2026-11-26T020005.yaml`, loads with both slots unset.
- [ ] 1.3 Update the vault note `Ontology/ScheduledRun.md` with the two slots, their ranges, and how discarded records are treated. Verify that it links to `[[ScheduleOutcome]]` and `[[Seeker]]`.

## 2. Run records: paths, discard, last-with-outputs

- [ ] 2.1 In `seeker/schedule/log.py`, add a `RunRecord` model (record file path plus `ScheduledRun`). Make `RunLog.all()` return them, add `RunLog.rewrite(record)` using the same atomic temp-and-replace write, and add `RunLog.last_with_outputs()`, which is the latest `advanced` or `budget` record that isn't discarded and has `written_paths`. Make `last_advanced()` skip discarded records. Verify with `tests/test_schedule_trigger.py` (or a new `test_schedule_log.py`) on temp folders:
  - ordering;
  - discarded records skipped by both lookups;
  - a corrupt file still skipped;
  - `rewrite` keeps the file name.
- [ ] 2.2 Check that the cadence skips discarded rounds. Verify with a cadence test that reproduces the scenario "A discarded round does not hold back the next": 11-24 advanced, 11-26 advanced and discarded, and a trigger at 2026-11-27 02:00 is due.

## 3. The missing-output guard

- [ ] 3.1 Add `OutputGuard` and the `OutputsMissing` error (in `seeker/schedule/guard.py` or `trigger.py`). Call it first in `Scheduler._locked_trigger`, before `LineageRecords.state()`. The message names each missing path and the exact `seeker-schedule discard <record> --note "..."` command. Verify with trigger tests on a scripted model:
  - a missing debate run leads to `failed`, the message names it, zero model calls, and no new generation;
  - all files present lets the trigger proceed as before;
  - with no prior outputs the guard passes;
  - a discarded record is ignored.
- [ ] 3.2 Make sure a guard failure writes the vault note, and that `seeker-schedule status` prints the last trigger's failure message, including the discard command. Verify with a note test and a status CLI test on the "outputs removed by a branch switch" fixture.

## 4. The discard command

- [ ] 4.1 Add `seeker-schedule discard <record> --note <text>` to `seeker/schedule/cli.py`, with a required note. It refuses when the record has no outputs, is already discarded, or any written path still exists. It sets `discarded_at` and `discard_note` through `RunLog.rewrite`. Verify with CLI tests for:
  - success, where the other fields are unchanged;
  - each of the three refusals, where the record is unchanged and the command exits 1;
  - after a successful discard, the guard passes.

## 5. Workspace config and command redirection

- [ ] 5.1 Add an optional `ScheduleConfig.workspace` field and `SeekerConfig.schedule_workspace()`. It reads env, then `.env`, then `seeker.yaml`, expands `~` and resolves relative paths against the config root, mirroring `vault()`. Add `workspace: null` with a comment to `seeker.yaml`. Verify with config tests for:
  - each source winning in order;
  - `~` expansion;
  - a relative path;
  - unset meaning `None`.
- [ ] 5.2 In `seeker/schedule/cli.py`, when a workspace is set and differs from the loaded root, reload config from `<workspace>/seeker.yaml` for `run`, `status`, `approve` and `discard`. Fail with a `ConfigError` naming the workspace and `workspace create` when it's missing. Make `status` print `workspace: <path>` and how many commits it is behind `origin/develop`. Verify with CLI tests using two temp checkouts: a manual `run` from the main checkout writes its record and outputs in the workspace, `status` reports the workspace head, and a missing workspace makes no model call.

## 6. Workspace create and update

- [ ] 6.1 Add `seeker/schedule/workspace.py` with an injectable `Git` runner and `ScheduleWorkspace.create()` (design decision 5). It refuses on an existing path, then:
  - fetches;
  - runs `git worktree add --detach <path> origin/develop`;
  - copies `.env`, the `runs/*.yaml` records, and the untracked or modified round outputs (excluding `scratch/`);
  - runs `uv sync --project`.
  Wire up `seeker-schedule workspace create`. Verify with a test against a temp git repo and bare remote. It should cover the scenario "Create with an uncommitted round 5": the head in the workspace is round 5, the records are copied, and nothing in the source is deleted. Also check that an existing path is refused.
- [ ] 6.2 Add `ScheduleWorkspace.update()`. It holds `RunLock`, fetches, removes untracked files that the target adds only if they're byte-identical, then runs `git checkout --detach origin/develop`. It never creates or switches a branch. Wire up `seeker-schedule workspace update`. Verify with temp-repo tests for:
  - identical merged outputs: the workspace moves and the head is unchanged;
  - a differing file: refused, with the HEAD and files unchanged;
  - the lock held: refused;
  - `git branch --show-current` stays empty afterwards.

## 7. LaunchAgent from the workspace

- [ ] 7.1 Make `LaunchAgent` build its plist from the workspace's config when one is configured. Make `install` refuse when the path isn't a worktree of this repository, checking `git rev-parse --git-common-dir`, and leave a loaded agent alone. Verify with launchd tests using a fake `Launchctl`:
  - the plist's `WorkingDirectory`, `--project`, `SEEKER_CONFIG` and log paths name the workspace;
  - a missing or foreign workspace is refused with no bootout;
  - with no workspace configured, the plist is unchanged from today's.

## 8. Docs and decision

- [ ] 8.1 Update `docs/scheduling.md`. Cover:
  - the workspace (config, `create`, `update`, and never switching branches in it);
  - the guard and what its failure looks like;
  - `discard`;
  - the review procedure, which copies the workspace's round outputs onto a `feature/` branch in the main checkout, merges, and then runs `workspace update`;
  - the migration steps from design.md.
  Verify that every command in the doc appears in `seeker-schedule --help` and runs against a temp workspace in tests or by hand.
- [ ] 8.2 Write the vault Decision `Decisions/2026-11-26 Pin the schedule workspace.md` (`type: decision`, `openspec: pin-schedule-workspace`). Give the context (the duplicate round 4 and its cost), the decision, the alternatives from design.md, and links to `[[ScheduledRun]]`, `[[ScheduleOutcome]]` and `[[Seeker]]`. Link to it from `Decisions/2026-11-23 Scheduled run every other day.md`. Verify that both links resolve in the vault.
- [ ] 8.3 Update `docs/NEXT_STEPS.html` step 1 (on `feature/round-viewer`, or after it merges) to point at this change. Verify that the page names the change and the migration steps.

## 9. Integration

- [ ] 9.1 Run `make lint`, `make schema` (no diff) and `make test`, and check that all pass. Then, on Gabe's Mac with his go-ahead, follow design.md's migration plan:
  - discard the 2026-11-26 record;
  - set `SEEKER_SCHEDULE_WORKSPACE`;
  - run `workspace create`;
  - check that `status` shows the expected head;
  - run `install`, and check the plist with `plutil -p ~/Library/LaunchAgents/com.seeker.scheduled-run.plist`.

## Workflow follow-up

- Open a PR from `feature/pin-schedule-workspace` into `develop`, and merge it after Gabe reviews.
- Archive the change with `/opsx:archive` on a `feature/archive-pin-schedule-workspace` branch.
