# Tasks

## 1. Ontology

- [x] 1.1 In `schema/seeker.yaml`, add the following, all with descriptions and examples (design decision 1):
  - the enum `ScheduleOutcome` (`advanced`, `budget`, `too_soon`, `awaiting_review`, `locked`, `failed`);
  - the classes `ScheduledRun` and `ReviewSignOff`, with their new slots;
  - the optional slot `stop_reason` on `Generation`.

  Run `make schema`. Verify that `linkml-lint` and `tests/test_schema.py` pass.
- [x] 1.2 Add `ScheduleOutcome`, `ScheduledRun` and `ReviewSignOff` to `seeker/ontology/schedule.py`, and `stop_reason` to `Generation`, all with full `Field` metadata. Export them from `seeker.ontology`. Verify:
  - the conformance test passes;
  - the round-1, round-2 and round-3 generation records load with `stop_reason` unset.
- [x] 1.3 Write the vault notes `Ontology/ScheduledRun.md`, `Ontology/ReviewSignOff.md` and `Ontology/ScheduleOutcome.md`. Update `Ontology/Generation.md` and `Ontology/StopReason.md`. Each note gives the definition, its slots with ranges, wikilinks to related classes, and links to `[[Seeker]]`. Verify that every new class or enum has a note and the hub links to it.

## 2. Mutation budget

- [x] 2.1 Add `GenerationCost` and a meter check before each child in `IdeaMutator.mutate`. Stop with `stop_reason: budget` and save. Clear `stop_reason` when a resume finishes. Verify with mutator tests on a stub model:
  - a $0.30 budget stops after the call that crosses it;
  - the saved generation has `stop_reason: budget`;
  - a resume with a higher budget calls only the missing positions and ends unset.
- [x] 2.2 Add `--budget` to `seeker-mutate` (default `budget_usd`), and exit with the debate's budget status when stopped. Make `seeker-debate` refuse a generation stopped at its budget. Verify with CLI tests for both, and that `--dry-run` is unchanged.
- [x] 2.3 Document the mutation budget and resume in `docs/mutating.md`. Verify that the documented commands run as written against a scratch generation with a stub model.

## 3. Config and API key

- [x] 3.1 Add `ScheduleConfig` (`cadence_days` ≥ 1 default 2, `review_every` ≥ 1 default 3, `hour` 0–23 default 2), `paths.runs`, `paths.reviews`, `paths.logs` and `vault_folders.runs` to `seeker/config.py` and `seeker.yaml`. Git-ignore `runs/` and `logs/`. Verify with config tests that defaults apply when the section is absent and out-of-range values are rejected.
- [x] 3.2 Add the Keychain lookup to `SeekerConfig.api_key()`, in the order environment, Keychain, `.env` (design decision 7), behind an injectable lookup. Verify with tests that:
  - each source wins in order;
  - a failing or missing `security` command falls through;
  - `MissingApiKey` names all three sources.

## 4. Scheduling core

- [x] 4.1 Extract the setup code from the mutate and debate CLIs into shared builders, with no behavior change. Verify that the existing CLI tests and `test_round_two_pipeline.py` pass unchanged.
- [x] 4.2 Implement `Lineage`, which finds the head, any in-progress round, and the review gate from the records (design decision 4). Verify with fixture-folder tests for:
  - the round-3 head;
  - two heads giving `failed`;
  - scratch files being ignored;
  - an in-progress generation being found;
  - the gate closed with no sign-off, open with a matching one, and closed again after the run file changes.
- [x] 4.3 Implement the cadence check with 12 hours of slack (design decision 9). Verify with the spec's Monday-to-Wednesday scenario, a first run with no records, and `cadence_days` 1.
- [x] 4.4 Implement `RoundRunner`, which mutates, debates, ranks and renders the report in process under one per-trigger cap (design decision 3). It resumes an in-progress round and renders a missing report first. Verify with stub-model tests that:
  - a full round writes the three files under the expected names;
  - mutation spend reduces the debate budget;
  - a cap reached mid-tournament stops cleanly;
  - the next trigger resumes with a fresh cap and makes only the remaining calls.
- [x] 4.5 Implement `ScheduledRun` recording and the `flock` lock. Every path, an exception included, writes a record. Verify with tests that a second runner records `locked`, a raised error records `failed` with its message, and a killed process's lock is free again.
- [x] 4.6 Implement the vault run note (design decision 10). Verify that:
  - a rendered note for a finished stub run has the frontmatter, round, cost, survivors, search health, report link and `[[Seeker]]`;
  - `too_soon` and `locked` write no note;
  - a missing vault doesn't fail the round.

## 5. Command and LaunchAgent

- [x] 5.1 Add the `seeker-schedule` command (`run`, `status`, `approve`, `install`, `uninstall`) and its `pyproject.toml` script, with the exit statuses from design decision 11. Verify with CLI tests that:
  - `status` needs no API key and reports the gate;
  - `approve` refuses an unfinished run or one that isn't the head;
  - `run` exits 0 on `too_soon`.
- [x] 5.2 Render and install the LaunchAgent plist from config (design decision 8), with `launchctl` behind an injectable runner. Verify with tests that:
  - the plist holds the configured hour, the repo root, `uv` and the logs paths, and no API key;
  - changing `paths.logs` changes the plist;
  - `uninstall` unloads and removes it.
- [x] 5.3 Write `docs/scheduling.md`: Keychain setup, install, status, approve and uninstall, the cadence and the gate, and where the records and logs go. In `docs/concept.md`, tick the roadmap item and answer the "rounds before survivors" and "budget per overnight run" open questions. Verify that the documented commands match `seeker-schedule --help`.
- [x] 5.4 Write `Decisions/2026-11-23 Scheduled run every other day.md` in the vault, with context, the decision, the alternatives and links to the concepts. Link it from `Seeker.md`. Verify that the note's frontmatter has `type: decision` and `openspec: scheduled-run`.

## 6. Live check

- [x] 6.1 Run `seeker-schedule status` and `seeker-schedule run` against the real records. Verify that both report the round-3 literal head as `awaiting_review`, that no API call is made, and that a `ScheduledRun` record and a vault note are written.
- [x] 6.2 Run `seeker-schedule install`, then `launchctl print gui/$(id -u)/com.seeker.scheduled-run`. Verify that the job is loaded and its next fire is 02:00, then trigger it once with `launchctl kickstart` and confirm the log and record show `awaiting_review`.

## Workflow follow-up

- Gabe reviews round 3 and runs `seeker-schedule approve` to open the gate for round 4.
- Archive the change after the PR to `develop` merges.
