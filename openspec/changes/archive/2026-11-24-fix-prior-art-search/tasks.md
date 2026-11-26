# Tasks

## 1. Ontology

- [x] 1.1 In `schema/seeker.yaml`, add the following, all with descriptions (design decision 1):
  - the enum `SearchTool` (`basic`, `filtered`);
  - the classes `SearchError` (`error_code`, `error_message`) and `SearchReport` (`results_returned`, `search_errors`);
  - the optional slots `search_tool` on `Role` and `search` on `Critique`.

  Run `make schema`. Verify `linkml-lint` and `tests/test_schema.py` pass.
- [x] 1.2 Add `SearchTool` and `Role.search_tool` to `seeker/ontology/role.py`, and `SearchError`, `SearchReport` and `Critique.search` to `seeker/ontology/debate.py`, all with full `Field` metadata. `Role` must require `search_tool` exactly when `max_searches > 0`. Export the new names from `seeker.ontology`. Verify:
  - the conformance test passes;
  - role-model tests reject `max_searches: 3` without `search_tool`, and `search_tool: basic` with `max_searches: 0`;
  - the round-1 and round-2 debate records load with no critique carrying `search`.

## 2. Role file and adapter

- [x] 2.1 Set `search_tool: basic` in `prompts/prosecutor.yaml`, and change nothing else in it. Verify that `DebateRoles.load` succeeds, and that the generator, mutator, skeptic, taste_critic, advocate and judge files still load unchanged.
- [x] 2.2 Make the following changes:
  - add `search_tool` to `ModelRequest`, with the same rule as `Role`;
  - pass it from `Debater._ask`;
  - in `AnthropicModel`, map `basic` to `web_search_20250305` and `filtered` to `web_search_20260209`.

  Verify with adapter tests on a stub client that:
  - a `basic` request sends `web_search_20250305` with `max_uses` 3;
  - a `filtered` request sends `web_search_20260209`;
  - a request with `max_searches` 0 sends no tools.
- [x] 2.3 Add `search_errors` to `ModelReply`, collected by `AnthropicModel` from search error result objects and from failed code-execution results (design decision 3), across paused turns. Verify with stub-client tests built from the probe's block shapes:
  - a `max_uses_exceeded` error object yields a `SearchError` with that code;
  - an encrypted code-execution result with return code 1 and stderr "Server tool use limit exceeded during code execution." yields `search_code_failed` with that message;
  - a clean basic response yields no errors and keeps its result URLs.

## 3. Debate record

- [x] 3.1 In `Debater._ask`, add up search results and errors across attempts. Attach a `SearchReport` to the critiques of roles with `max_searches > 0`, and only to those. Verify with debater tests on a fake model:
  - a prosecutor reply with 18 results gets `results_returned` 18 and no errors;
  - a reply with an error records it;
  - a retried prosecution sums both attempts;
  - skeptic and taste_critic critiques have no `search`;
  - a prosecution whose retry call fails keeps the first call's `SearchReport` on its `DebateFailure`.
- [x] 3.2 Print "prior-art search: N of M with results, K with errors" in the `seeker-debate` run summary. Verify with a CLI test on a fake model with one failing prosecution.

- [x] 3.3 Check each prosecutor answer's URLs against the search results of every call of that prosecution so far, not only the current call (design decision 6). `results_returned` stays per call. Verify with debater tests that:
  - a retry with no new search that cites a URL from the first call's results is accepted;
  - a URL that no call returned is still rejected and retried, then recorded as a failure.

## 4. Report

- [x] 4.1 Add `SearchHealth` to `JudgeHealth` (design decision 5), with carried debates excluded. Render it in the judge-health section, and give each prosecutor critique a search line. Verify with report tests that:
  - a fixture run shows "11 of 12" prosecutions with results, 1 with errors and its citation count;
  - `debates/2026-11-16-round-2-literal.yaml` renders "search outcomes were not recorded";
  - `reports/2026-11-14-round-1-literal.md`, re-rendered, differs only by that line.

## 5. Docs and vault

- [x] 5.1 Update `docs/debating.md`: the prosecutor's search tool, `SearchReport`, the new report lines, and why `filtered` is not used. Update the `seeker.yaml` prices comment, which says code-execution filtering is uncharged, to name the basic tool. Re-render `reports/2026-11-16-round-2-literal.md` and `reports/2026-11-14-round-1-literal.md`. Verify the full test suite and `ruff` pass.
- [x] 5.2 In the vault:
  - add `Ontology/SearchTool.md`, `Ontology/SearchReport.md` and `Ontology/SearchError.md`, each with frontmatter `type: concept` and `openspec: fix-prior-art-search`, slots with ranges, and links back to `[[Seeker]]`;
  - update `Ontology/Role.md` and `Ontology/Critique.md`;
  - write `Decisions/2026-11-17 Basic web search for the prosecutor.md`, with the probe evidence and the rejected alternatives;
  - update `Seeker.md`: the ontology list, the status line and the Next list.

  Verify that every new note links to `[[Seeker]]` and that the hub links the decision.

## Workflow follow-up

- Open a PR from `feature/fix-prior-art-search` into `develop`.
- After merge, check the next live debate's report. Prior-art search should show nearly every prosecution with results, and citations well above round 2's 2. Update the debate severity watch memory with whether the prosecutor's severities spread out once it can see evidence.
- Archive the change.
