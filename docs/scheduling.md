# Scheduling rounds

`seeker-schedule` runs the loop on Gabe's Mac without anyone watching. A launchd LaunchAgent fires `seeker-schedule run` every day at 2am. Each trigger either skips or advances the lineage by exactly one round:

1. mutate the head's survivors (`docs/mutating.md`);
2. debate and rank the new generation (`docs/debating.md`);
3. render its report.

The 2026-11-23 decision set these defaults: one round every other day, $5 per trigger, and a review after every 3 rounds.

```
uv run seeker-schedule status                 # where the lineage stands; no API call
uv run seeker-schedule run                    # one trigger, as launchd runs it
uv run seeker-schedule approve debates/2026-11-23-round-3-literal.yaml --note "keep the obscura line"
uv run seeker-schedule discard runs/2026-11-26T020005.yaml --note "duplicate round 4; kept 2026-11-24"
uv run seeker-schedule workspace create       # make the schedule workspace (once)
uv run seeker-schedule workspace update       # move it to the latest origin/develop
uv run seeker-schedule install                # write and load the LaunchAgent
uv run seeker-schedule uninstall              # unload and remove it
```

When a schedule workspace is configured, `run`, `status`, `approve`, `discard` and `install` all act on the workspace, whichever checkout you type them in. See [The schedule workspace](#the-schedule-workspace).

## One-time setup

1. Put the API key in the login Keychain. `security` prompts for it, so it never lands in shell history:

   ```
   security add-generic-password -s seeker -a anthropic -w
   ```

   Seeker reads the key from `ANTHROPIC_API_KEY` first, then this Keychain item, then `.env`. It never appears in the plist, the logs, any record or any note.
2. Run `uv run seeker-schedule status` and check the head and the gate.
3. Run `uv run seeker-schedule install`. Running it again after a config change rewrites and reloads the agent.

## What a trigger does

Each trigger works through these checks in order, and stops at the first that applies:

| Check | Outcome | API calls | Vault note |
|---|---|---|---|
| The last trigger that wrote round files (`advanced` or `budget`, not discarded) names a file that is no longer on disk | `failed`, naming the files | none | yes |
| Another trigger holds `runs/.lock` | `locked` | none | no |
| The head's report is missing | renders it, then goes on | none | — |
| A round is in progress (a generation already mutated from the head) | resumes it under a fresh cap, whatever the cadence | yes | yes |
| The head is at a review point with no sign-off | `awaiting_review` | none | yes |
| The last `advanced` round ended less than `cadence_days` ago, less 12 hours | `too_soon` | none | no |
| Otherwise | mutates, debates and reports: `advanced`, or `budget` if the cap stops it | yes | yes |

Any error is recorded as `failed` with its message, the vault note says why, and the command exits 1.

**The head** is the finished debate run with the highest round. Files under `scratch/` don't count. If two finished runs share the highest round, the trigger fails and names both. The scheduler advances one lineage at a time.

**The cadence.** With `cadence_days: 2`, a round is due 36 hours after the last advanced round ended. The 12 hours of slack keep a round that finished at 03:10 from pushing the next one back a day. launchd still fires every night, and half the nights end `too_soon`. If the Mac is asleep at 2am, launchd runs the missed trigger once on wake.

**The cap.** `budget_usd` ($5) covers the whole trigger: mutation, debate and tournament together. The debate gets whatever mutation left. A trigger that reaches the cap stops cleanly, at most one model call over. The next trigger resumes that round with a fresh $5. A full round costs about $4.70 (round 3: $0.80 mutation, $3.89 debate and tournament).

**The review gate.** Whenever the head's round is a multiple of `review_every` (3), the lineage waits for a sign-off. To give one:

1. Read the report.
2. Commit the round outputs on a feature branch.
3. Run `seeker-schedule approve <head run>`.

The sign-off in `reviews/` names the run's SHA-256, so editing the run afterwards closes the gate again. A sign-off clears only that review point.

## Where things go

All of these come from `seeker.yaml`, so moving a run is a config change.

| What | Config | Default | In git? |
|---|---|---|---|
| Round outputs | `paths.generations`, `paths.debates`, `paths.reports` | `generations/`, `debates/`, `reports/` | yes, committed by hand at review |
| One `ScheduledRun` record per trigger | `paths.runs` | `runs/` | no, ignored |
| Sign-offs | `paths.reviews` | `reviews/` | yes |
| launchd stdout and stderr | `paths.logs` | `logs/seeker-schedule.{out,err}.log` | no, ignored |
| Vault notes | `vault_folders.runs` | `<vault>/Runs/` | — |
| Cadence, gate, hour | `schedule.cadence_days`, `schedule.review_every`, `schedule.hour` | 2, 3, 2 | — |
| The schedule workspace | `SEEKER_SCHEDULE_WORKSPACE` in `.env`, else `schedule.workspace` | unset (the repo root) | — |

With a workspace configured, every folder above is the workspace's own.

The job never commits, branches or pushes. `status` lists the uncommitted round outputs, so they can go onto a `feature/` branch at review time, as gitflow requires (see [Committing a review's rounds](#committing-a-reviews-rounds)).

## The missing-output guard

The lineage head is read from the round files on disk, but the cadence is read from the git-ignored `runs/` records. If a `git switch` removes the latest round's files, the head falls back a round while `runs/` still says that round advanced. On 2026-11-26 that let the job re-run round 4 for about $4.26.

So before it does anything else, each trigger finds the latest `advanced` or `budget` record that isn't discarded, and checks that every file in its `written_paths` exists. If one doesn't, the trigger:
- records `failed`, with a message naming the missing files;
- makes no API call and writes nothing else;
- writes the vault note and exits 1.

`status` shows the same message the next morning. There are two ways forward:
- **The files are only elsewhere**, for example on another branch: restore them, by checking out that branch or copying them back. The next trigger goes on as usual.
- **They were dropped on purpose:** discard the record. Delete or move the files first, because `discard` refuses while any of them is still on disk:

  ```
  uv run seeker-schedule discard runs/<record>.yaml --note "why"
  ```

  This sets `discarded_at` and `discard_note` on the record and keeps everything else. The guard and the cadence then skip it, so a discarded round doesn't hold back the next.

## The schedule workspace

The job runs from its own git worktree of the repo, detached at `origin/develop`, where nobody switches branches. Agents and people work in the main checkout, or in worktrees of their own.

- **Where it is.** Set `SEEKER_SCHEDULE_WORKSPACE=~/Sites/seeker-schedule` in the main checkout's `.env`. It's git-ignored, so the machine's path stays out of git. `schedule.workspace` in `seeker.yaml` is the fallback. A relative path resolves against `seeker.yaml`'s folder.
- **`workspace create`** (once):
  1. `git worktree add --detach <path> origin/develop`;
  2. it copies in the `.env`, every `runs/` record, and every round output (`generations/`, `debates/`, `reports/`, `reviews/`, but not `scratch/`) that isn't committed;
  3. it runs `uv sync` there.

  It refuses if the path exists. Nothing is deleted from the main checkout. Once `status` shows the right head, the main checkout's untracked copies can go.
- **`workspace update`** moves it to the latest `origin/develop`, under the run lock:
  - An uncommitted file that develop now also holds is dropped first, but only if the two are byte-identical.
  - If any differs, or a trigger holds the lock, it refuses and changes nothing.
  - It never makes, switches to or commits on a branch.
- **Never `git switch` inside the workspace.** If it happens anyway, the guard stops the next trigger instead of letting it redo a round.
- `status` prints `workspace: <path>` first, along with how many commits it is behind `origin/develop`.

### Committing a review's rounds

The job never commits, so at a review point the rounds since the last review exist only in the workspace. From the main checkout:

```
git switch -c feature/<change-or-review-name> origin/develop
cp ~/Sites/seeker-schedule/{generations,debates,reports}/<date>-round-<n>-literal.* <matching folders>
cp ~/Sites/seeker-schedule/reviews/<run>.yaml reviews/     # after approve
git add generations debates reports reviews && git commit
git push -u origin HEAD                                    # PR into develop
```

Once the PR is merged, run `uv run seeker-schedule workspace update`. The workspace's untracked copies become the committed ones, and the head stays where it was.

### Moving to a workspace

These are the steps taken once on Gabe's Mac:

1. Discard the duplicate round 4. Its files were deleted on 2026-11-26:

   ```
   uv run seeker-schedule discard runs/2026-11-26T020005.yaml --note "duplicate round 4; kept 2026-11-24"
   ```
2. Add `SEEKER_SCHEDULE_WORKSPACE=~/Sites/seeker-schedule` to the main checkout's `.env`.
3. Run `uv run seeker-schedule workspace create`.
4. Run `uv run seeker-schedule status`, and check that the head is the latest round.
5. Run `uv run seeker-schedule install`, and check the plist with `plutil -p ~/Library/LaunchAgents/com.seeker.scheduled-run.plist`.
6. Delete the main checkout's untracked round outputs, which are now stale copies.

To go back, remove `SEEKER_SCHEDULE_WORKSPACE` and run `install` again. The guard stays either way.

## The LaunchAgent

`install` writes `~/Library/LaunchAgents/com.seeker.scheduled-run.plist`:
- it runs `<uv> run --project <repo> seeker-schedule run` from `<repo>`, daily at `schedule.hour`;
- `<uv>` is the `uv` found on `PATH` at install time;
- `<repo>` is the schedule workspace when one is configured, else the folder holding `seeker.yaml`;
- its logs go to that tree's `paths.logs`.

With a workspace configured, `install` refuses a folder that isn't a git worktree of this repository, and leaves any loaded agent alone.

`install` loads the agent with `launchctl bootstrap gui/<uid>`. To check it or fire it once by hand:

```
launchctl print gui/$(id -u)/com.seeker.scheduled-run
launchctl kickstart gui/$(id -u)/com.seeker.scheduled-run
```

Rollback is `uv run seeker-schedule uninstall`. Every record and output stays on disk as an ordinary file.
