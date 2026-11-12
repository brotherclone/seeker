# Tasks

## 1. Spike: web search with structured output

- [x] 1.1 Write a throwaway script in `generations/scratch/` (git-ignored). It sends one `claude-sonnet-5-5` request with `web_search_20260209` (`max_uses: 2`) and `output_config.format` set to a small JSON schema with a `urls` array. Record in design decision 3, with a dated note, whether:
  - the call succeeds;
  - the final text block is valid JSON;
  - `usage.server_tool_use.web_search_requests` is populated;
  - `pause_turn` occurred.

  Choose the one-call or the two-call prosecutor accordingly. Verify by the recorded outcome and the request id. Spend is under $0.10.
- [x] 1.2 Check the web-search price and the 5.5 cache rates on the official pricing page. Record them in the `seeker.yaml` price comments with the date. Verify the comment cites the page and the date.

## 2. Ontology: shared changes

- [x] 2.1 In `schema/seeker.yaml`:
  - add the five `RoleName` values, `web_search_requests` on `Usage` and `max_searches` on `Role`, with `ifabsent` 0 and descriptions (design decision 1);
  - update the `RoleName` description, which says only the generator exists.

  Run `make schema`. Verify `linkml-lint` and `tests/test_schema.py` pass.
- [x] 2.2 Mirror the 2.1 changes in `Usage` (including `+`/`total`/`zero`), `Role` and `RoleName`. Verify:
  - the conformance test passes;
  - both round-1 generation records still load, with `web_search_requests` 0;
  - `prompts/generator.yaml` loads with `max_searches` 0;
  - `max_searches: -1` fails, naming the file and the slot.
- [x] 2.3 Add `PriceTable.web_search_per_request` and `PriceTable.cost(model, usage)`, including searches. Add `paths.debates`, `paths.reports`, `budget_usd` (default 5.00) and `tournament.max_comparisons` (default 66) to `SeekerConfig` and `seeker.yaml`. Git-ignore `debates/scratch/`. Verify config tests: the defaults, relative path resolution, and that 3 searches at $0.01 add $0.03; and that `git check-ignore debates/scratch/x.yaml` passes.

## 3. Ontology: debate and tournament classes

- [x] 3.1 Add the enums `CritiqueTarget`, `Severity`, `DefenseMove`, `DefenseOutcome` and `ScoreAxis`, the classes `Citation`, `Critique`, `Reply`, `IdeaRevision`, `Defense`, `Debate` and `DebateFailure`, and their slots to the schema, all described. Run `make schema`. Verify `linkml-lint` passes.
- [x] 3.2 Add `AxisVerdict`, `Comparison`, `Rating`, `Tournament`, `RoleDigest` and `DebateRun` to the schema. Run `make schema`. Verify `linkml-lint` passes.
- [x] 3.3 Implement the 3.1 models in `seeker/ontology/debate.py`, with rich `Field` metadata. Include these validators:
  - `Citation` has exactly one of `url` and `work`;
  - `card` is required when the target is `card_reading`;
  - `none_found` implies `minor` severity and no citations;
  - `revision` is present only for `revised`.

  Verify that the conformance test and unit tests cover each validator.
- [x] 3.4 Implement the 3.2 models in `seeker/ontology/tournament.py` and `DebateRun`. Verify:
  - the conformance test passes;
  - a hand-built `DebateRun` fixture validates against the LinkML schema with `DebateRun` as the target class.

## 4. Role files

- [x] 4.1 Write `prompts/prosecutor.yaml`, `skeptic.yaml`, `taste_critic.yaml`, `advocate.yaml` and `judge.yaml` with the models, efforts, `max_searches` and personas from design decision 2, three reading guidances each.
  - The skeptic's gear-and-stack list and the taste critic's persona are drafted from the vault's `Works/` and `Notes/`, and marked `# DRAFT: Gabe to edit`.

  Verify that all five load as `Role`s.
- [x] 4.2 Implement `seeker/debate/roles.py`. It loads the five roles with their digests and rejects:
  - critics that share both model and persona;
  - any unpriced model, before any call.

  Verify tests for both rejections and for the happy path.
- [ ] 4.3 Gabe reviews and edits the skeptic's gear list and the taste critic's persona, and removes the DRAFT markers. Verify the markers are gone and Gabe has approved in the PR.

## 5. Model boundary: web search

- [x] 5.1 Extend `ModelRequest` (`max_searches`) and `ModelReply` (`search_results`, search count in `Usage`). In `AnthropicModel`:
  - add the web search tool when `max_searches` is above 0;
  - collect result URLs and titles;
  - resume `pause_turn` up to 3 times;
  - treat search error blocks as no results.

  Skip `code_execution_tool_result` blocks (spike 1.1 found them). Verify stub-client tests: tool presence and absence, the `max_uses` value, result collection, the search count, `pause_turn` resume and give-up, and an error block.

## 6. Debate stage

- [x] 6.1 Implement the `CritiqueDraft` parse and checks from design decision 4: the one-sentence `failure` of 8-40 words, the restatement check, the card target, and the prosecutor evidence rules. Verify unit tests for every reject path in the spec: a vague failure, a restatement, an uncited `fatal`, an invented URL, an unknown `WorkId`, and an out-of-draw citation card that is dropped.
- [x] 6.2 Implement the `DefenseDraft` parse and checks: one reply per critique, the conceded-fatal rules, and the revision form via the `IdeaDraft` checks. Verify tests for each scenario in the spec's "advocate answers" and "revisions keep the form" requirements.
- [x] 6.3 Implement the critic and advocate prompt renderers in `seeker/debate/prompts.py`. The prosecutor's prompt includes the `DrawPriorArt` hits, or an explicit no-hits line. Verify snapshot tests:
  - no critic prompt contains another critic's text;
  - the reading guidance appears;
  - a catalog hit appears in the prosecutor prompt.
- [x] 6.4 Implement `ProsecutorFindings.capture` (design decision 6): URL normalisation, catalog dedupe and citation rewrite, note creation through `NoteFile.new`, the collision suffix, and a catalog reload. Verify fixture-vault tests:
  - a new note loads as a valid `Work` with `captured_by: prosecutor`;
  - a known URL writes nothing;
  - an existing file name gets ` (2)`;
  - existing notes are byte-identical afterwards.
- [x] 6.5 Implement `Debater`, the per-idea flow with one retry per role:
  - a failing critic still gets the advocate;
  - a failing advocate excludes the idea;
  - each record has a model and usage.

  Verify fake-model tests for the full flow, critic failure and advocate failure.
- [ ] 6.6 Implement `CostMeter` and `DebateSink` with resume checks:
  - refuse changes to the generation digest, role digests or seed;
  - allow a change to the catalog digest;
  - add `stop_reason` at the budget.

  Verify tests for: resume after 5 of 12 debates, a changed skeptic digest refused by name, and a budget stop followed by a resume with a higher budget.

## 7. Tournament stage

- [ ] 7.1 Implement the pairing schedule from design decision 7: round robin up to `max_comparisons`, otherwise k equal seeded opponents with no repeated pair, and A/B order from a SHA-256 stream. Verify tests:
  - 12 entrants give 66 pairs;
  - 30 entrants give equal counts, at most 66 pairs and no repeats;
  - the same seed gives the same schedule.
- [ ] 7.2 Implement the judge prompt with blinding (A/B labels, objections shuffled by seed, severities, role names, models and personas stripped) and the `AxisVerdict` draft checks (all three axes, winner in the pair, no ties). Verify:
  - a test asserting that no role name, model id or persona text appears in any rendered comparison;
  - retry tests for a missing axis and an outside position.
- [ ] 7.3 Implement the per-axis Elo (K = 32, start 1500, a failed comparison leaves ratings unchanged), recomputation from stored comparisons, and survivors (top 3 by promise, ties broken by wins, then position). Exclude withdrawn ideas, and skip the tournament under two entrants. Verify tests:
  - the hand-computed Elo for a 3-idea fixture;
  - recompute equals the record;
  - axes move independently;
  - the survivor tie-break;
  - withdrawn ideas are excluded;
  - the skip case.
- [ ] 7.4 Wire the tournament into the run, saving after each comparison and respecting the meter. Verify a fake-model test that a run interrupted mid-tournament resumes with no repeated comparison.

## 8. Command line, report and docs

- [ ] 8.1 Implement `seeker-debate` with `--out`/`--scratch`, `--seed`, `--budget`, `--no-tournament` and `--dry-run` (prompts plus call and comparison counts, no key needed), the per-debate lines and summary, and exit status 3 at the budget. Add the console script. Verify CLI tests for each flag, using the round-1 literal generation.
- [ ] 8.2 Implement `seeker-debate report RUN`, writing Markdown to `paths.reports`: the survivors with all three ratings, original and revised statements, critiques and replies, and linked citations; then the non-survivors table, provenance and cost. Verify a snapshot test from a fixture run that makes no model call.
- [ ] 8.3 Write `docs/debating.md`. It covers the roles and why each is on its model, the named-failure rule, the prosecutor's catalog-then-search order and captured works, the budget and resume, the tournament and survivors, and the report. Verify that every documented command runs as written with `--dry-run` or against fixtures.

## 9. Obsidian notes

- [ ] 9.1 Write the `Ontology/` notes for the 13 new classes and 5 new enums (definition, slots with ranges, wikilinks, a link to the hub). Update `Role`, `RoleName`, `Usage`, `CaptureSource`, `Idea`, `Generation` and `Work`. Verify that each slot table matches `schema/seeker.yaml`.
- [ ] 9.2 Write `Decisions/2026-11-12 Debate shape and blind per-axis Elo.md` (context, decision, alternatives, links to concepts and to `debate-ideas`). Update the `Seeker.md` status and "Next" list. Verify the note links to the hub and the change, and the frontmatter has `type: decision` and `openspec: debate-ideas`.

## 10. Integration

- [ ] 10.1 Run `uv run pytest`, `linkml-lint` and `seeker-debate generations/2026-11-04-round-1-literal.yaml --dry-run`. Verify all pass, and that the dry run reports 12 debates, about 48 debate calls and 66 comparisons.

## Workflow follow-up

- First live run, by Gabe or with his go-ahead because it spends money: `uv run seeker-debate generations/2026-11-04-round-1-literal.yaml --out debates/2026-11-12-round-1-literal.yaml`, then `seeker-debate report`. Expected cost is $2.50-$4.50. Review the survivors and the severity spread before tuning prompts.
- Debate the metaphorical generation too, on its own baseline branch, to answer the reading-per-axis question.
- Open a PR from `feature/debate-ideas` into `develop` after PR #12 merges, and archive after merge.
- Next changes: `mutate-survivors`, then the run-and-scheduling change.
