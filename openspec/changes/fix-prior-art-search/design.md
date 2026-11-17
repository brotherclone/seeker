# Design

## Context

Two files hold the current wiring.
- `AnthropicModel` (`seeker/models/anthropic_model.py`):
  - offers the hard-coded `web_search_20260209` with `max_uses` set from `ModelRequest.max_searches`;
  - collects result URLs only from `web_search_tool_result` blocks whose content is a list;
  - skips everything else, which means error objects and code-execution results are dropped.
- The debater (`seeker/debate/debater.py`) checks each prosecutor citation against `ModelReply.result_urls`.

The probe evidence is in proposal.md, under Why. The key fact is that the adapter did collect the URLs, but the model never saw them. So citations were never rejected. The model simply had nothing to cite.

Roles involved: only the prosecutor (`claude-sonnet-5-5`, effort `medium`, `max_searches: 3`, the archivist persona). Its persona and system prompt are unchanged, and the only edit to its file is `search_tool: basic`.

## Goals / Non-Goals

**Goals:**
- The prosecutor sees its search results.
- The run record pins which search tool version was used.
- A search that fails can never again pass silently. It is recorded on the critique and counted in the summary line and report.

**Non-Goals:**
- Raising `max_searches`, or rewording the prosecutor prompt. Two searches per idea were enough on the probe.
- Fixing the filtered tool's sandbox handling. The `filtered` value stays available for a future role, with its failure mode documented.
- Retrying a prosecution whose search failed. It is recorded and shown. Retrying would mean adding a third path to `_ask`, and the root fix should make it rare.
- Re-running rounds 1 or 2.

## Decisions

### 1. Schema first

`schema/seeker.yaml` gains the following.

```yaml
enums:
  SearchTool:
    description: Which version of the web search tool a role is offered.
    permissible_values:
      basic:    {description: "Each search's results go straight to the model (web_search_20250305)."}
      filtered: {description: "The model filters results with code it writes before it sees them (web_search_20260209)."}
classes:
  SearchError:   # slots: error_code (required), error_message (required)
  SearchReport:  # slots: results_returned (integer, min 0, required), search_errors (SearchError, multivalued)
slots:
  search_tool: {range: SearchTool}   # on Role
  search:      {range: SearchReport} # on Critique
```

`error_code` uses the API's code, such as `max_uses_exceeded`. When code running the searches failed, it is `search_code_failed`, and `error_message` carries the stderr text.

Then the models that mirror the schema:
- `SearchTool` in `seeker/ontology/role.py`, plus `Role.search_tool`;
- `SearchError` and `SearchReport` in `seeker/ontology/debate.py`, plus `Critique.search`.

All of them carry the usual `Field` metadata.

### 2. The tool version lives in the role file, not the adapter

`Role` validates that `search_tool` is set exactly when `max_searches > 0`. `ModelRequest` gains `search_tool: SearchTool | None`, with the same rule enforced. The adapter maps `basic` to `web_search_20250305` and `filtered` to `web_search_20260209`, with the mapping in one place on the adapter.

Alternatives considered:
- **Hard-code the basic version in the adapter.** This is simpler, but a later change to the constant would leave no trace in the run records. That is exactly how this bug went unseen.
- **Keep `filtered` and state the budget in the prompt.** I probed this, and it failed: the script also crashes because the sandbox's `web_search` returns a JSON string, which the model doesn't expect.
- **Raise `max_uses`.** This doesn't fix the parse crash, and it pays for more searches whose results the model still never sees.

### 3. The adapter reports errors instead of dropping them

`ModelReply` gains `search_errors: tuple[SearchError, ...]`, and `AnthropicModel` collects them from:
- a `web_search_tool_result` whose content is an error object, which gives its `error_code`;
- any code-execution result block, of any of the current types, with a non-zero `return_code`, when the request offered search. That gives `search_code_failed` and the stderr.

A paused turn that is resumed accumulates errors the same way it accumulates results.

### 4. One SearchReport per critique, accumulated like usage

`Debater._ask` adds up search results and errors across attempts, in the same way it adds up `Usage`. When the role's `max_searches > 0`, the critique gets `SearchReport(results_returned=..., search_errors=...)`. Counting every attempt keeps the report consistent with the usage it sits beside. `results_returned` counts results, not distinct URLs, because that is what the API returned.

### 5. Health counts the run's own prosecutions

`JudgeHealth` gains `search: SearchHealth | None`, computed from prosecutor critiques in debates that were not carried:
- prosecutions with a `SearchReport`;
- those with results above 0;
- those with any error;
- URL citations.

`None` means no prosecutor critique had a report, as in rounds 1 and 2. The report then says search outcomes were not recorded. The run summary line in `seeker-debate` uses the same counts. Each prosecutor critique in the report also gets a short line: "search: N results", or the error codes when there were errors.

## Risks / Trade-offs

- **More input tokens.** Unfiltered results add tokens to the prosecutor's input. → The probe calls cost a few cents more each. The budget meter already prices tokens. Watch the per-run cost in the next live run.
- **The basic tool version could be retired for newer models.** → The version is now one line in the role file, and a resume or new run pins it through the digest.
- **Changing the prosecutor's digest refuses resumes of earlier runs.** → Rounds 1 and 2 are finished, so nothing is left to resume.
- **`filtered` stays offered even though it is known to misbehave.** → The enum description and `docs/debating.md` say so. No current role uses it.

## Migration Plan

- Old records load unchanged, because both slots are optional.
- No data migration is needed.
- The next live debate is the end-to-end check. Its report should show nearly every prosecution with results, and citations well above round 2's 2.

Vault notes:
- new: `Ontology/SearchTool.md`, `Ontology/SearchReport.md`, `Ontology/SearchError.md`;
- updated: `Ontology/Role.md`, `Ontology/Critique.md`;
- `Decisions/2026-11-17 Basic web search for the prosecutor.md`;
- `Seeker.md`: the ontology list, the status line and the Next list.
