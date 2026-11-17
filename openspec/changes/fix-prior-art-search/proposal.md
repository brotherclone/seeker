# Proposal

## Why

The prior-art prosecutor has barely checked prior art in either live run. Round 1 and round 2 together cite 2 URLs, and most prosecutor critiques say the search tool "hit its usage limit" and returned nothing. That leaves the prosecutor's uniform `minor` severities and every `none_found` unverified, and it weakens the novelty axis the tournament already judges least consistently.

A live probe on 2026-11-17 traced the cause to the prosecutor role and the model adapter (`seeker/models/anthropic_model.py`).
- The adapter offers `web_search_20260209`. That version filters results by having the model write code that calls `web_search` from a sandbox.
- The prosecutor writes one script with three or four queries, and two things go wrong:
  - A fourth query exceeds `max_uses: 3`. That aborts the whole script ("Server tool use limit exceeded during code execution"), so every result the script had already printed is lost.
  - Inside the sandbox, `web_search` returns a JSON string, so the model's `x.get('url')` code fails. Each retry spends more of the budget.
- Either way, the model never sees a result, even though 18–27 results came back and were billed.
- The adapter collects those result URLs, but it silently drops error result objects and failed code-execution blocks. So nothing in the run record shows that the search failed.

The same probe with the basic `web_search_20250305` tool ran 2 searches per idea, cited 3–4 URLs per idea (all in the returned results), and needed no code.

## What Changes

- **Search tool per role.** A role file that searches names which tool version to use: `basic` (no code execution; results go straight to the model) or `filtered` (dynamic filtering through code execution). The adapter sends the matching tool type. A role with `max_searches` above 0 must name one, so a run's role digest pins the tool version.
- **The prosecutor uses `basic`.** `prompts/prosecutor.yaml` sets `search_tool: basic`. This changes the prosecutor role digest.
- **Search problems are recorded.** The adapter returns typed `SearchError`s for search error results (such as `max_uses_exceeded`) and for search code that failed with a non-zero return code. It no longer drops them.
- **Each searching critique records its search.** It gets a `SearchReport` with the number of results returned and any errors. A `none_found` from a search that returned nothing, or one that errored, is then visible as unverified.
- **The run shows search health.** `seeker-debate`'s summary line and the report's judge-health section give, per run:
  - how many prosecutions got results;
  - how many hit errors;
  - how many citations they made.
- **Docs and vault.** `docs/debating.md` and the `seeker.yaml` prices comment, which currently mentions code-execution filtering, are updated. So is the vault: new Ontology notes and a Decisions note.

This changes no command-line flags. Older records still load, because the new slots are optional and the round-1 and round-2 records have none.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `idea-generation`: the role ontology and role files gain the `SearchTool` enum and `Role.search_tool`, which a role must set when it searches.
- `idea-debate`: the debate ontology gains `SearchReport` and `SearchError` and `Critique.search`. The prosecutor's search requirement now names the tool version and requires search outcomes, errors included, to be recorded.
- `idea-tournament`: the report's judge-health section gains prior-art search health.

## Impact

- **Engine stage:** the debate, and only the prosecutor role. Other roles don't search. The generator, mutator, skeptic, taste critic, advocate and judge are unchanged.
- **Ontology:**
  - new enum `SearchTool`;
  - new classes `SearchReport` and `SearchError`;
  - new slots `search_tool` (on `Role`), `search` (on `Critique`), `results_returned` and `search_errors` (on `SearchReport`), and `error_code` and `error_message` (on `SearchError`).
  - SHACL and OWL are regenerated.
- **Code:**
  - `seeker/models/base.py` (`ModelRequest`, `ModelReply`);
  - `seeker/models/anthropic_model.py`;
  - `seeker/ontology/role.py` and `seeker/ontology/debate.py`;
  - `seeker/debate/debater.py`, `health.py`, `report.py` and `cli.py`;
  - `prompts/prosecutor.yaml`.
- **Reproducibility:** each run records the tool version through the role digest, rather than a constant in the adapter that could change without trace. Editing `prompts/prosecutor.yaml` changes its digest. Resuming a run started before this change is refused, naming the prosecutor digest, as for any role edit. Round 1 and round 2 are both finished, so nothing is left to resume.
- **Cost:** about the same. The basic tool uses about 2 searches per idea at $0.01 each, and results take more input tokens because nothing filters them. On the probe, each prosecutor call cost a few cents more.
