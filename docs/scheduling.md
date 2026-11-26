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
uv run seeker-schedule install                # write and load the LaunchAgent
uv run seeker-schedule uninstall              # unload and remove it
```

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

The job never commits, branches or pushes. `status` lists the uncommitted round outputs, so they can go onto a `feature/` branch at review time, as gitflow requires.

## The LaunchAgent

`install` writes `~/Library/LaunchAgents/com.seeker.scheduled-run.plist`:
- it runs `<uv> run --project <repo> seeker-schedule run` from the repo, daily at `schedule.hour`;
- `<uv>` is the `uv` found on `PATH` at install time;
- `<repo>` is the folder holding `seeker.yaml`.

`install` loads the agent with `launchctl bootstrap gui/<uid>`. To check it or fire it once by hand:

```
launchctl print gui/$(id -u)/com.seeker.scheduled-run
launchctl kickstart gui/$(id -u)/com.seeker.scheduled-run
```

Rollback is `uv run seeker-schedule uninstall`. Every record and output stays on disk as an ordinary file.
