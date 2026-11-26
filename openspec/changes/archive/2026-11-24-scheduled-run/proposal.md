# Proposal

## Why

Each round of the loop is still run by hand: `seeker-mutate`, then `seeker-debate`, then `seeker-debate report`. Round 3 (2026-11-23) was run that way. Seeker is meant to evolve ideas unattended and bring them to Gabe only at review points, so the last unchecked step in `docs/concept.md` is the scheduled run on Gabe's Mac.

On 2026-11-23 Gabe settled the open scheduling questions:
- each run advances one round;
- runs happen every other day at 2am;
- each run is capped at $5;
- the lineage pauses for review after round 3.

## What Changes

- **A scheduled round.** A new `seeker-schedule run` command advances the lineage by one round. It finds the head of the lineage, the latest finished `DebateRun` that no generation has mutated yet. It then mutates the head's survivors, debates and ranks the new generation, and writes the report. The output names follow the existing pattern (`<date>-round-<n>-<reading>.yaml`) in the configured `generations/`, `debates/` and `reports/` folders.
- **Cadence.** launchd fires the job daily at 2am. The run exits without any API call unless the last round that advanced was at least `schedule.cadence_days` (default 2) days ago, less 12 hours of slack, which makes 36 hours for 2. The slack keeps a run that started late or ran long from pushing the next one back a day. A round that stopped at its cap is unfinished: it resumes at the next trigger whatever the cadence, rather than starting a new round.
- **One cap across the round.** `budget_usd` ($5) covers the mutation, the debate and the tournament together. `seeker-mutate` gains a cost meter and `--budget`, and stops cleanly at the cap like `seeker-debate` does. The scheduled run gives the debate only what mutation left.
- **Review gate.** After every `schedule.review_every` rounds (default 3), counted by `MutationOrigin.round`, the lineage pauses. It stays paused until Gabe signs off with `seeker-schedule approve <debate-run>`, which writes a `ReviewSignOff` record. Round 3 is the first gate.
- **Scheduled run record.** Every trigger writes a `ScheduledRun` record: when it started and ended, its `ScheduleOutcome` (`advanced`, `budget`, `too_soon`, `awaiting_review`, `failed`, `locked`), the parent run, the files written and the estimated cost. The cadence check reads these records. A lock file stops two runs from overlapping.
- **Nightly note.** Each run that does work writes a note to the vault's `Runs/` folder (configured, like `Works/`). It gives the outcome, the cost, the survivors, the prosecutor's search health and a link back to the report, and it links to [[Seeker]]. A run skipped as `too_soon` writes no note.
- **API key from the Keychain.** `SeekerConfig.api_key()` reads the key from `ANTHROPIC_API_KEY`, then the macOS Keychain (generic password, service `seeker`), then `.env`. The key never appears in the plist or the logs.
- **LaunchAgent install.** `seeker-schedule install` writes the LaunchAgent plist to `~/Library/LaunchAgents` and loads it, and `uninstall` unloads and removes it. The plist's paths (repo root, `uv`, the logs folder) are worked out from the config location when it is installed, never written into code. `seeker-schedule status` shows the head, its round, the gate state, the last outcome and when the next run is due.
- **The job never commits.** It writes files but makes no git change. Gabe commits a lineage's outputs on a feature branch when he reviews it, as gitflow requires.

Reproducibility is unchanged: each round is the same mutate and debate run, with the same digests, seeds and resume checks. Resumability improves, because a round stopped at the cap resumes from its saved records at the next trigger.

## Capabilities

### New Capabilities

- `scheduled-run`: the unattended round. It covers the lineage head, cadence, the cap shared across a round, the review gate and sign-off, the `ScheduledRun` record, the lock, the nightly vault note, the LaunchAgent install, and the `seeker-schedule` command.

### Modified Capabilities

- `idea-mutation`: mutation gains a spend cap. It checks its estimated cost before each child, stops cleanly once the cost reaches the budget (`budget_usd` or `--budget`), saves the reason it stopped, and resumes with more budget. `seeker-debate` refuses a generation whose mutation stopped at its budget.

The `idea-debate` budget requirement already covers what the scheduled run needs, so it is unchanged. The run passes the remaining cap as the debate's budget.

## Impact

- **Engine stage:** a new orchestration stage over mutate → debate → report. No agent role, prompt or deck changes, so role digests are unchanged.
- **Ontology:** new classes `ScheduledRun` and `ReviewSignOff`, and a new enum `ScheduleOutcome`. `Generation` gains `stop_reason`, reusing `StopReason` with `budget`.
- **Code:** `seeker/schedule/` (new), `seeker/mutate/` (meter and `--budget`), `seeker/config.py` (the `schedule` section, `paths.runs`, `paths.logs`, `vault_folders.runs`, and the Keychain lookup), and `pyproject.toml` (`seeker-schedule` script).
- **Config:** a new `schedule` section in `seeker.yaml` (`cadence_days`, `review_every`, `hour`) and new paths. All of them default, so existing configs still load.
- **System:** one LaunchAgent in `~/Library/LaunchAgents`, plus logs in the configured logs folder.
- **Docs and vault:** `docs/scheduling.md` (new), `docs/mutating.md` and `docs/concept.md` (the roadmap item and the answered open questions). In the vault, new Ontology notes and a Decisions note dated 2026-11-23.
