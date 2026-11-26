# Design

## Context

A round is currently three commands: `seeker-mutate`, then `seeker-debate`, then `seeker-debate report`. Each command loads `SeekerConfig` and builds its own model client. Records are YAML files in the configured `generations/`, `debates/` and `reports/` folders (committed). The SQLite `ideas.db` sketched in `docs/concept.md` was never built, so the YAML records are the run state.

Spend control is uneven:
- `seeker-debate` has a `CostMeter` (`seeker/debate/meter.py`). It compares a `DebateRun`'s total recorded spend with a budget before each debate and each comparison.
- `seeker-mutate` has no meter. It records `Generation.estimated_cost_usd` but never stops.

The API key comes from `ANTHROPIC_API_KEY` or `.env` (`SeekerConfig.api_key()`). Nothing reads the Keychain yet.

Round 3 was run by hand on 2026-11-23. It is the first review point under the new gate. See proposal.md for why.

## Goals / Non-Goals

**Goals:**
- One command runs one round from end to end, in process. A LaunchAgent can call it, and so can Gabe by hand.
- The $5 cap is a hard ceiling for one trigger, mutation included, with at most one call of overshoot, as the debate already has.
- Every trigger leaves evidence. A quiet failure at 2am is the main thing to avoid.

**Non-Goals:**
- Running in the cloud. Every path comes from config, so moving later is a config change.
- Running more than one lineage. Only the literal lineage exists. A second head is reported as an error, not scheduled.
- Fresh draws on a schedule. Gabe chose advancing one round.
- Committing or opening PRs from the job.
- Notifications beyond the vault note (push, email).

## Decisions

### 1. LinkML schema first

`schema/seeker.yaml` gains the following. Where a slot already exists, it is reused.

```yaml
enums:
  ScheduleOutcome:
    description: How one scheduled trigger ended.
    permissible_values:
      advanced:        {description: A round finished and its report was written.}
      budget:          {description: The trigger reached its spend cap; the round resumes at the next trigger.}
      too_soon:        {description: The last advanced round is more recent than the cadence allows; nothing ran.}
      awaiting_review: {description: The head is at a review point with no sign-off; nothing ran.}
      locked:          {description: Another scheduled run held the lock; nothing ran.}
      failed:          {description: The trigger stopped on an error, which it records.}

classes:
  ScheduledRun:
    description: One trigger of the scheduled job, what it found, what it did and what it cost.
    slots: [started_at, ended_at, schedule_outcome, head_run_path, head_round,
            written_paths, estimated_cost_usd, budget_usd, error_message]
  ReviewSignOff:
    description: Gabe's sign-off on a lineage head at a review point, pinned by digest.
    slots: [reviewed_run_path, reviewed_run_digest, signed_at, note]
  Generation:
    slots: [..., stop_reason]   # optional, range StopReason; unset for finished and older records
```

The new slots are `ended_at`, `schedule_outcome`, `head_run_path`, `head_round`, `written_paths`, `reviewed_run_path`, `reviewed_run_digest` and `signed_at`. Each carries a description and examples. SHACL and OWL are regenerated, and `linkml-lint` passes. Then the Pydantic models are written in `seeker/ontology/schedule.py`, following the existing per-file pattern, and the conformance test covers them.

The config sections (`ScheduleConfig` with `cadence_days`, `review_every`, `hour`, plus the new paths) stay config models in `seeker/config.py` and are not added to the ontology. This matches `TournamentConfig` and `MutationConfig`.

### 2. Run the round in process

`seeker/schedule/round.py` builds the mutator, debate runner and tournament runner from one `SeekerConfig` and one model client. It does not run the three CLIs as subprocesses. The CLIs' setup code (load config, decks, role, sinks) moves into small builder classes, and the CLIs and the scheduled run share them. Each CLI keeps its exact behavior.

- **Why in process:** one model client and one API key lookup per round. Costs come back as typed records rather than parsed stdout. A failure arrives as a typed exception that can be recorded as `failed` with its message.
- **Alternative: a shell script chaining the CLIs.** Simpler, but it can't share the cap without parsing output, and a failure is just an exit code. Rejected.

### 3. The cap is per trigger, over cumulative meters

Both meters compare a record's total recorded spend with a budget. To give each trigger a fresh $5 on resume, the run passes budgets offset by what the records had already spent when the trigger began:

- `mutation_budget = generation_spent_before + cap`
- `debate_budget = debate_spent_before + (cap − mutation_spent_this_trigger)`

Mutation gets a `GenerationCost` and a meter check before each child, mirroring `RunCost` and `CostMeter`. It stops with `Generation.stop_reason = budget`. `seeker-debate` refuses such a generation, so a half-mutated round can never be debated.

- **Alternative: one cap per round, not per trigger.** A round that ran out would then never resume without a manual override. Gabe set the cap per run (per night), so it is per trigger.

### 4. Head, in-progress round and gate come only from records

Each trigger rescans the folders. It does not trust a state file.

- **Head:** the finished `DebateRun` with the highest round. A generation without a `MutationOrigin` is round 1.
- **In progress:** a non-scratch `Generation` whose `MutationOrigin.parent_run_path` is the head. The trigger resumes it with the existing resume checks.
- **Gate:** the head's round is a multiple of `review_every`, and no `ReviewSignOff` in `reviews/` matches the head's path and current SHA-256.

This survives manual runs between triggers, because round 3 was made by hand and the scheduler picks it up unchanged. It also survives deleted run records and edits.

### 5. Record storage

- `ScheduledRun` records go to `paths.runs` (default `runs/`), one YAML per trigger, named by start time (`2026-11-25T020000.yaml`). The folder is git-ignored: these are operational logs, and with `too_soon` every other night they are numerous. The cadence check reads the newest `advanced` record.
- `ReviewSignOff` records go to `paths.reviews` (default `reviews/`, committed). They are review decisions, and they belong in git next to the runs they approve.
- launchd stdout and stderr go to `paths.logs` (default `logs/`, git-ignored).

### 6. Lock with `fcntl.flock`

`runs/.lock` is held with an exclusive non-blocking `flock` for the life of the process. The kernel releases it when the process dies, so a stale lock clears itself and no PID checks are needed. Another run that can't take the lock records `locked`.

### 7. Keychain lookup

`SeekerConfig.api_key()` checks, in order: the environment, then `security find-generic-password -s seeker -a anthropic -w` (on macOS only, with a short timeout, and any failure counts as no key), then `.env`. A LaunchAgent runs in Gabe's login session, so the login keychain is unlocked. The one-time setup, `security add-generic-password -s seeker -a anthropic -w`, goes in `docs/scheduling.md`. The `MissingApiKey` message names all three sources.

### 8. LaunchAgent

`seeker-schedule install` renders the plist from a template:

- `Label`: `com.seeker.scheduled-run`.
- `ProgramArguments`: `[<uv>, run, --project, <root>, seeker-schedule, run]`.
- `WorkingDirectory`: `<root>`.
- `StartCalendarInterval`: `{Hour: schedule.hour, Minute: 0}`.
- `StandardOutPath` and `StandardErrorPath`: under `paths.logs`.
- `EnvironmentVariables.PATH`: includes `uv`'s folder.

`<uv>` is `shutil.which("uv")` at install time, and `<root>` is the folder holding `seeker.yaml`. The plist is written to `~/Library/LaunchAgents/com.seeker.scheduled-run.plist` and loaded with `launchctl bootstrap gui/<uid>`. If the Mac is asleep at 2am, launchd runs the missed trigger once on wake. The cadence check makes that harmless.

- **Alternative: `StartInterval` 172800.** It drifts with sleep and restarts, and gives no fixed hour. Rejected, and the cadence moved into code (see the 2026-11-23 decision).

### 9. Cadence slack

Due means `now − last_advanced.ended_at ≥ cadence_days × 24h − 12h`. Rounds take 20–60 minutes and may end at 2:50 or 3:30. Without slack, a 3:10 finish would make the 2am trigger two days later 50 minutes too early, and the round would slip a day.

### 10. The vault note reuses the report's numbers

The note is rendered from the finished `DebateRun` with the same calculations the report uses: survivors and ratings, search health, and spend. It goes to `<vault>/<vault_folders.runs>/YYYY-MM-DD round-N <outcome>.md` with frontmatter `type: note`, `tags: [seeker, scheduled-run]` and `outcome`. A missing vault does not fail the round. The trigger still records its outcome, notes the vault error in `error_message`, and prints it to the log.

### 11. Exit statuses

`advanced`, `too_soon`, `awaiting_review` and `locked` exit 0. `budget` exits with the existing budget status, and `failed` exits 1. launchd ignores exit status, but a manual run shows it.

### Obsidian notes

- **New:** `Ontology/ScheduledRun.md`, `Ontology/ReviewSignOff.md`, `Ontology/ScheduleOutcome.md`, and `Decisions/2026-11-23 Scheduled run every other day.md`. The decision note covers advancing one round, every other day through a daily trigger plus skip, the 2am start, the $5 cap per trigger, and the review gate every 3 rounds. It lists the alternatives Gabe was offered and links to `openspec: scheduled-run`.
- **Updated:** `Ontology/Generation.md` (`stop_reason`), `Ontology/StopReason.md` (now used by `Generation`), and the `Seeker.md` hub links.

## Risks / Trade-offs

- **[The Mac is off or logged out at 2am]** → launchd runs the missed trigger on wake or login. If the keychain is locked, the trigger records `failed` with the missing-key message, and `status` shows it.
- **[Cost is estimated from the price table]** → The overshoot is at most one call, as for the debate today. If prices go stale, spend is misreported. `prices.as_of` is already dated, and the note shows the cost each run.
- **[Unattended drift: prompts or decks change between rounds]** → The existing resume checks refuse a resume whose digests changed. A new round simply pins the new digests, and the review gate caps unattended drift at 3 rounds.
- **[Untracked files pile up in the working tree]** → This is intended, because the job never commits. `status` lists the uncommitted round outputs so a review can commit them on a feature branch.
- **[A round runs while Gabe has a feature branch checked out]** → Files land in the working tree whatever the branch. The run records `git_commit` as today, and the review commits the outputs where they belong.
- **[Two heads appear (for example, the metaphorical lineage gets debated)]** → The run records `failed`, naming both. Scheduling several lineages is a later change.

## Migration Plan

1. Merge the change. Configs without a `schedule` section use the defaults.
2. Gabe stores the key: `security add-generic-password -s seeker -a anthropic -w`.
3. Run `uv run seeker-schedule status`. It should report the round-3 literal head, awaiting review.
4. Run `uv run seeker-schedule install`.
5. Review round 3, then run `seeker-schedule approve debates/2026-11-23-round-3-literal.yaml`. Round 4 runs at the next due 2am.

**Rollback:** `uv run seeker-schedule uninstall` removes the LaunchAgent. Records and outputs stay as ordinary files.
