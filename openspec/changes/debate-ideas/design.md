# Design

## Context

- **Generator.** The generator (`seeker/generate/`) is the pattern this change copies:
  - a `LoadedRole` (a `Role` plus its file's SHA-256) and a `LanguageModel.reply(ModelRequest)` boundary with native JSON-schema output;
  - a draft model that parses and validates the answer, with one retry carrying `DraftProblem` feedback;
  - a `GenerationSink` that rewrites the YAML record after every unit, and resume checks that refuse mismatched inputs.
- **Pricing.** `ModelPrice.cost(usage)` prices one model's usage. `Generation` assumes one model, but a debate mixes five.
- **Prior art.** `seeker.works` gives `WorkNotes.catalog()` and `BatchCheck`/`DrawPriorArt` (the offline prior-art check), plus `NoteFile.new(...).with_values(...).save()` for writing notes without damaging existing ones.
- **`Role` model.** `Role` requires exactly three `ReadingGuidance` entries. Every new role keeps that: critics and the judge need to know how freely the cards were read, so they don't penalise a metaphorical idea for not being literal.
- **Inputs.** Two recorded generations exist, `generations/2026-11-04-round-1-literal.yaml` and `-metaphorical.yaml`, with 12 ideas each. They are the first inputs.
- **Pointers.** Motivation is in proposal.md. Requirements are in `specs/idea-debate`, `specs/idea-tournament` and `specs/idea-generation`.

## Goals / Non-Goals

**Goals:**
- **Distinct voices.** Five roles on distinct model and persona pairs, none of them the generator's exact voice.
- **Cheap rules in code.** Every rule that can be checked cheaply (named failure, citations, form, coverage of replies) is enforced in code, not left to the prompt.
- **Same habits as generation.** A debate run is resumable, budget-bounded and reproducible as far as model output allows.
- **Run in one sitting.** A 12-idea run finishes well under the $5 nightly cap.

**Non-Goals:**
- Mutation, or more than one debate round.
- Parallel or batched API calls. Calls run sequentially: about 115 calls for 12 ideas, roughly 30-45 minutes, which is fine for a nightly run.
- SQLite. Run state stays in YAML records, like generations.
- Search sources beyond Claude web search (arXiv, NIME archive or GitHub APIs).
- Writing survivors into the vault as nightly notes. That belongs to the scheduling change.

## Decisions

### 1. Schema first: what LinkML gains

`RoleName` gains five values, `Usage` gains a slot, `Role` gains an optional slot:

```yaml
RoleName:
  permissible_values:
    generator:    {description: Turns one draw into one idea stated as a single sentence.}
    prosecutor:   {description: Argues an idea has been done, citing catalog works and web results.}
    skeptic:      {description: Argues an idea cannot be built with Gabe's gear, stack and time.}
    taste_critic: {description: Argues an idea is boring even if new and buildable.}
    advocate:     {description: Answers every critique and may revise or withdraw the idea.}
    judge:        {description: Compares two debated ideas blind and picks a winner per axis.}
web_search_requests: {range: integer, minimum_value: 0, ifabsent: int(0), slot_uri: seeker:webSearchRequests}
max_searches:        {range: integer, minimum_value: 0, ifabsent: int(0), slot_uri: seeker:maxSearches}
```

New enums:

```yaml
CritiqueTarget: {permissible_values: {subject: {}, behavior: {}, rationale: {}, card_reading: {}, constraint: {}}}
Severity:       {permissible_values: {fatal: {}, serious: {}, minor: {}}}
DefenseMove:    {permissible_values: {concede: {}, rebut: {}}}
DefenseOutcome: {permissible_values: {defended: {}, revised: {}, withdrawn: {}}}
ScoreAxis:      {permissible_values: {novelty: {}, feasibility: {}, promise: {}}}
```

Every value gets a description in the real schema.

New classes (slots abbreviated):

| Class | Slots |
|---|---|
| `Citation` | `url` (Url, optional), `work` (Work by `WorkId`, optional; exactly one of the two), `title`, `relevance` (one sentence), `cards` (draw cards the work embodies) |
| `Critique` | `role_name`, `model`, `target`, `card` (when `target` is `card_reading`), `severity`, `failure`, `argument`, `citations`, `none_found` (bool, prosecutor only), `usage` |
| `Reply` | `role_name` (of the critique answered), `move`, `argument` |
| `IdeaRevision` | `statement`, `subject`, `behavior`, `rationale` |
| `Defense` | `model`, `replies`, `outcome`, `revision` (when `outcome` is `revised`), `usage` |
| `Debate` | `position`, `critiques` (3), `defense`, `final_statement` |
| `DebateFailure` | `position`, `role_name`, `model`, `failure_reason`, `discarded_critiques` (the critiques kept when the advocate fails, added during implementation), `usage` |
| `AxisVerdict` | `axis`, `winner` (position), `reason` |
| `Comparison` | `first`, `second` (positions as shown, A then B), `verdicts` (3), `failed` (bool), `model`, `usage` |
| `Rating` | `position`, `axis`, `rating`, `wins`, `losses` |
| `Tournament` | `seed`, `k_factor` (32), `initial_rating` (1500), `max_comparisons`, `schedule` (ordered position pairs), `comparisons`, `ratings`, `survivors` |
| `RoleDigest` | `role_name`, `digest` |
| `DebateRun` | `generation_path`, `generation_digest`, `role_digests`, `catalog_digest`, `git_commit`, `started_at`, `budget_usd`, `stop_reason`, `debates`, `failures`, `tournament`, `usage`, `estimated_cost_usd` |

The Python models in `seeker/ontology/debate.py` and `seeker/ontology/tournament.py` mirror these, with titles, descriptions, examples and slot URIs, under the conformance test. `Rating.rating` is a float, so Elo updates aren't rounded away. `Debate.final_statement` is derived from the defense (validated, not free input).

### 2. Roles: model and persona per role

Every role file is a `Role` with three `ReadingGuidance` entries. The critics' guidance tells them how to judge an idea at that reading. For example, under `metaphorical`: "attack whether the reading is earned, not whether the card was taken literally".

| Role | Model | Effort | Persona (summary) | Why this model |
|---|---|---|---|---|
| `prosecutor` | `claude-sonnet-5-5` | medium | An archivist of NIME/ICMC proceedings, SIGGRAPH, demoscene archives, itch.io, Bandcamp liner notes and patents, who is delighted to find precedent. `max_searches: 3`. | Good at searching, and much cheaper than Opus across 36 searches' worth of context |
| `skeptic` | `claude-haiku-5-5` | medium | A cranky bench tech who has repaired synths and shipped kits, and who asks what it costs, what it needs and how long it takes. Its system prompt carries Gabe's gear-and-stack list. | Fast and blunt, as the concept suggests, and a different model family voice from Opus |
| `taste_critic` | `claude-sonnet-5-5` | high | Written from Gabe's captured works and vault notes: what he keeps, what bores him, and the "pitch-deck idea" smell. Gabe signs off on it before the first live run. | Needs judgment. Kept off Opus, so it isn't the generator's voice grading itself |
| `advocate` | `claude-opus-5-5` | high | The generator's artist-engineer at its most stubborn: defends what's real, concedes what isn't, and revises toward the idea hiding inside the critiques. | The concept puts Opus on the advocate, because revisions often produce the real idea |
| `judge` | `claude-sonnet-5-5` | high | A neutral curator for a creative-tech festival who has seen everything once. It is deliberately not Gabe's taste: the taste critic already carries that. | Not the same model as the generator and advocate, to limit self-preference |

Each persona and system prompt is written out in its `prompts/*.yaml` file during implementation. The skeptic's gear list and the taste critic's persona are drafted from the vault and the White project context, and marked for Gabe's edit, because only Gabe knows them.

### 3. Web search at the model boundary

- **Request.** `ModelRequest` gains `max_searches: int = 0`. When it is above 0, `AnthropicModel` adds `{"type": "web_search_20260209", "name": "web_search", "max_uses": n}`.
- **Reply.** `ModelReply` gains `search_results: tuple[SearchResult, ...]` (url, title), collected from `web_search_tool_result` blocks, plus a search count read from `usage.server_tool_use.web_search_requests`.
- **`pause_turn`.** It is resumed by re-sending the assistant content, at most 3 times. After that the call fails as `ModelCallFailed`.
- **Errors.** A search error comes back as a result block holding an error object (for example `max_uses_exceeded`). It is treated as zero results, not as an exception.
- **The JSON answer** is the final text block.

Two items are unverified in this skill's docs:
- whether `output_config.format` (strict JSON) can be combined with the web search tool in one call;
- whether the citations that web search attaches to text trip the "citations are incompatible with structured output" 400.

The first implementation task is a live spike that settles both. **Fallback**, which is equivalent behind the same `LanguageModel` boundary: the prosecutor makes two calls.
1. A search call with the tool and free-text notes, and no output format.
2. A structured call with no tools, given those notes and the result list.

Only `seeker/debate/prosecutor.py` would notice. The spec is unaffected, because URLs are still validated against the results of that idea's searches.

**Spike result (2026-11-12, request `req_011CgyFphGRSv3r8ZJN7tzbn`, `claude-sonnet-5-5`, SDK 2.4.0): one call works.**
- `web_search_20260209` with `max_uses: 2` and a strict `output_config.format` returned `end_turn` with no `pause_turn`.
- The single final text block was valid JSON with no citations attached, and every URL it gave was among the 10 search results.
- `usage.server_tool_use.web_search_requests` was 1.
- The content also held `code_execution_tool_result` blocks. That is the tool's built-in dynamic filtering, which the boundary must skip.
- Input was 39,013 tokens for one search (about $0.096 for the call). The prosecutor is the run's biggest cost: about $0.10–$0.25 per idea at 1–3 searches. The 12-idea estimate rises to about **$2.50–$4.50**, still under the $5 budget.

So the prosecutor is one call, and the two-call fallback is dropped. If cost becomes a problem, the first lever is `max_searches` 1–2, and the second is trying the basic `web_search_20250305` variant (no dynamic filtering) on Sonnet 5.5.

Alternatives considered:
- Scraping specialist venues directly: more reach, much more code to maintain. Deferred.
- Search through MCP: adds a dependency for no gain over the server tool.

### 4. Checking the named-failure rule in code

`CritiqueDraft.problems_for(idea, draw, search_results, catalog)` applies these checks:
- **One sentence.** `failure` is one sentence, using the same sentence check as `IdeaDraft`, and is 8-40 words long.
- **Not a restatement.** It is rejected when its word-set overlap with the idea's statement is 0.7 or more (Jaccard), or when it contains no word outside the statement, the stop words and the card names.
- **Card target.** `target: card_reading` names a card id from the draw.
- **Prosecutor evidence.** Citations or `none_found: true`; `none_found` implies severity `minor` and no citations; URLs are among `search_results`; `work` ids are in the catalog; citation `cards` are within the draw (cards outside it are dropped, not rejected).

`DefenseDraft` checks:
- exactly one reply per critique `role_name`;
- a conceded `fatal` critique forces `revised` or `withdrawn`;
- a conceded `fatal` with no revision forces `withdrawn`;
- `revised` requires a revision, which must pass the `IdeaDraft` form checks. A revision mentions a card by name only if the card is in the draw.

**Phrase lists rejected:** a "vague phrase" blocklist ("might be hard", "could be", ...) is brittle and easy to game. The overlap and novelty checks above catch restatement. Vagueness that survives them is left to the judge, who sees every objection.

### 5. Debate flow and records

- **Per idea:** prosecutor, then skeptic, then taste critic (independent prompts), then advocate (sees all three), then prosecutor findings are written as works. After each idea, the `DebateRun` is saved through a `DebateSink`, the same pattern as `GenerationSink`.
- **One failing critic** records a `DebateFailure`. The idea still goes to the advocate with the critiques that succeeded, and its `Debate` holds fewer than three critiques, flagged in the report. Dropping the idea would let one model error remove a good idea.
- **A failing advocate** records a `DebateFailure`, and the idea is excluded from the tournament.
- **Storage:** YAML in `paths.debates` (default `debates/`, with a git-ignored `debates/scratch/`), one file per run.
  - Alternative: SQLite `ideas.db`, as in the concept sketch. Rejected for now: generation records are YAML and diffable in PRs, the round-1/round-2 comparison relied on that, and one run is a few hundred KB. Revisit when mutation needs lineage queries across runs.

### 6. Caching prosecutor finds as works

`ProsecutorFindings.capture(citations, draw, catalog, vault)`:
- normalises URLs (lowercase scheme and host, strip a trailing `/` and `utm_*` parameters);
- skips any URL a catalog work already has, and rewrites that citation to point at the work's id;
- writes `Works/<Title>.md` through `NoteFile.new`, with frontmatter `type: work`, `title`, `url`, `kind: other`, `cards`, `captured_by: prosecutor`, `captured_on` and `summary` (the citation's relevance line);
- on a file-name collision, appends ` (2)`, ` (3)` and so on;
- reloads the catalog afterwards, so later ideas in the same run see the new works. That is why the catalog digest is allowed to change on resume.

`creators` and `year` are left empty, for Gabe or `seeker-works suggest` to fill in. Notes are only ever created.

### 7. Blind comparisons and per-axis Elo

- **What the judge sees.** For each of A and B:
  - the final statement, its parts and card readings;
  - "Objection 1-3", with each failure and argument, in seeded shuffled order;
  - the reply to each.

  Severities, role names, models and personas are stripped. Severity is self-reported by the critics, and showing it would let the judge count labels instead of reading arguments.
- **Schedule.**
  - Up to `max_comparisons` (default 66, set in `seeker.yaml` under `tournament:`), a round robin.
  - Above that, a seeded schedule giving every entrant the same number of opponents (k = ⌊2·max/n⌋, no repeated pair).
  - A/B order per pair comes from the seed, through a SHA-256 stream like the draw stream.
- **Ratings.** Elo with K = 32, starting at 1500, applied in schedule order, on three independent ladders. A failed comparison leaves the ratings unchanged.
- **Survivors.** The top 3 by `promise`, with ties broken by promise wins, then position.
- **Alternatives considered:**
  - A blended score: rejected, because the concept says never to blend axes.
  - Bradley-Terry fitting, which is order-independent and statistically nicer. Elo was chosen to match the concept, and because the stored comparisons let a BT fit be added later without rerunning anything.
  - Judging both A/B orders: doubles the judge's cost. A seeded order plus the record allows a later position-bias audit.

### 8. Cost meter and budget

- **Prices.** The price table gains a top-level `web_search_per_request` ($10 per 1,000 searches, so 0.01; to be checked against the pricing page when the table is updated). `ModelPrice.cost` stays per model, and `PriceTable.cost(model, usage)` adds searches.
- **Meter.** A `CostMeter` holds the run's budget. Before each debate and each comparison it checks the recorded spend so far against the budget; it does not try to predict the next unit's cost. (Revised during implementation: checking before every call would discard a half-finished debate's paid-for critiques when the budget trips between critic and advocate, leaving spend unrecorded. Checking per unit keeps every call in the record, at the cost of overshooting by at most one debate, about $0.40.)
- **Stopping.** At the budget, the run saves with `stop_reason: budget` and the CLI exits with status 3. Resuming with `--budget` continues.

### 9. Package layout

`seeker/debate/`:

| Module | Contents |
|---|---|
| `roles.py` | Loads and checks the five roles (distinct model/persona, all priced) |
| `prompts.py` | Critic, advocate and judge prompt renderers, including blinding |
| `drafts.py` | `CritiqueDraft` and `DefenseDraft` with output specs and problem checks |
| `prosecutor.py` | Catalog check plus search plus citation validation |
| `findings.py` | Caching works |
| `debater.py` | The per-idea flow |
| `tournament.py` | Schedule, judge calls and Elo |
| `meter.py` | Cost meter and budget |
| `record.py` | Sink and resume checks |
| `report.py` | Markdown survivors report |
| `cli.py` | `seeker-debate [run] GENERATION ...` and `seeker-debate report RUN` |

### 10. Obsidian notes

- **Created in `Ontology/`:**
  - classes: `Citation`, `Critique`, `Reply`, `Defense`, `IdeaRevision`, `Debate`, `DebateFailure`, `AxisVerdict`, `Comparison`, `Rating`, `Tournament`, `RoleDigest`, `DebateRun`;
  - enums: `CritiqueTarget`, `Severity`, `DefenseMove`, `DefenseOutcome`, `ScoreAxis`.
- **Updated in `Ontology/`:**
  - `Role` (`max_searches`), `RoleName` (five values) and `Usage` (`web_search_requests`);
  - `CaptureSource` (prosecutor now writes works);
  - `Idea` and `Generation` (linked from `Debate` and `DebateRun`), and `Work` (linked from `Citation`).
- **Decision:** `Decisions/2026-11-12 Debate shape and blind per-axis Elo.md`. It covers one round, the model and persona per role, named-failure checks, severity hidden from the judge, per-axis Elo with survivors by promise, and YAML over SQLite.
- **Hub:** `Seeker.md` gets a status line for `debate-ideas` and the reordered "Next" list (mutation, then scheduling).

## Risks / Trade-offs

- **[Structured output and web search don't combine]** → Settled by the spike in task 1, with the two-call prosecutor fallback (Decision 3).
- **[Critics agree politely anyway]** → Distinct models and personas, required severities and named failures. The report shows each idea's severity spread, so a run where every critique is `minor` stands out. Tuning the prompts is expected after the first live run.
- **[The advocate withdraws too much or too little]** → The outcome counts are printed per run. Withdrawal is forced only by a conceded `fatal` with no revision, never by any other rule.
- **[The judge prefers longer or more fluent debates]** → Objections are blinded and shuffled, and the reply argument length is capped by the output token limit. Comparisons are stored so a length-bias check can be run later.
- **[Prosecutor notes clutter the vault]** → They are tagged `captured_by: prosecutor`. `seeker-works validate` already treats them as normal works, and Gabe can bulk-delete by that key.
- **[Elo depends on order]** → The order is seeded and recorded, and ratings are exactly recomputable. With 66 comparisons for 12 entrants, order effects on the top 3 are small.
- **[Persona and gear lists are guesses]** → They are drafted, then Gabe edits them before the first live run (task 4.3). The role digest makes every later edit traceable.

## Migration Plan

- **Additive.** `web_search_requests` and `max_searches` default to 0, so existing generation records and `prompts/generator.yaml` load unchanged (covered by a scenario).
- **Config.** `seeker.yaml` gains `paths.debates`, `paths.reports`, `budget_usd`, `prices.web_search_per_request` and `tournament.max_comparisons`, all with defaults.
- **Rollback.** Revert the merge. Prosecutor-captured work notes in the vault stay, and they remain valid `Work` notes.

## Open Questions

- **Reading per axis.** Should the medium card stay literal under a metaphorical reading? This was held over from the round-2 note. Answer it by debating both round-1 generations once this lands, as a separate baseline branch. It changes prompts, not this design.
- **Batches API for the judge.** It costs 50% less, but results are asynchronous. Worth it once runs are nightly; it doesn't change the record shape.
- **Judge prompt tuning.** Whether the judge should also see the original statement of a revised idea. Decide after the first live tournament.
