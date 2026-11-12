# Proposal: debate-ideas

## Why

Seeker can draw cards and turn each draw into a one-sentence idea, but nothing yet tests those ideas. Every idea in round 1 reached Gabe unexamined, which is the opposite of the concept: only ideas that survive adversarial critique should reach him. Prior-art capture now exists (`seeker-works check`), so the prosecutor has an offline catalog to read before it spends anything on web search. That makes this the right moment to build the debate and the judge.

## What Changes

- **Five new agent roles**, each a versioned YAML file in `prompts/`, each on a deliberately different model and persona to resist consensus collapse:
  - `prosecutor`: argues the idea has been done. It reads the `seeker-works check` hits for the idea's draw first, then runs a capped number of Claude web searches.
  - `skeptic`: argues the idea can't be built with Gabe's actual gear, stack and time.
  - `taste_critic`: argues the idea is boring. Its persona is written from Gabe's captured works and notes.
  - `advocate`: answers each critique (concede or rebut), and may revise the idea or withdraw it.
  - `judge`: compares two ideas blind and picks a winner on each of novelty, feasibility and promise.
- **Debate stage.** Each idea in a `Generation` gets exactly one round: three critiques, then one defense. Every `Critique` must name a specific failure: its target part of the idea, a severity, and a one-sentence failure. Critiques that don't are rejected and retried, as generator output already is. The prosecutor must cite search results or catalog works, or explicitly report that it found none.
- **Prosecutor findings become works.** A web result the prosecutor cites that isn't already in the catalog is written to the vault's works folder as a `Work` note with `captured_by: prosecutor`. Its card links are limited to cards from the idea's draw. Existing notes are never changed.
- **Tournament stage.** Withdrawn ideas are dropped. The rest meet in blind pairwise `Comparison`s: role names are stripped, objections are shuffled, and A/B order is seeded. Comparisons update one Elo ladder per axis (`novelty`, `feasibility`, `promise`), never a blended score. Survivors are the top 3 by `promise`, reported with all three ratings.
- **A `seeker-debate` command** runs both stages over a recorded `Generation`. It writes a `DebateRun` record incrementally so a stopped run resumes, supports `--dry-run` (shows prompts, call counts and comparison counts), and renders a survivors report.
- **A spend stop.** The run stops cleanly when its estimated cost reaches a budget (default $5 from config) and can be resumed later. The nightly scheduling change will reuse this meter.
- **Web search is metered.** `Usage` gains a web-search request count, and the price table gains a per-search price, so a run's cost includes its searches.
- **Mutation is out of scope.** Sending winners back to the generator gets its own follow-up change, once rankings have been seen.

Agent roles touched: adds `prosecutor`, `skeptic`, `taste_critic`, `advocate` and `judge`. The `generator` is unchanged. Engine stages touched: adds the debate and tournament stages after generation. No deck changes.

## Ontology

- **New classes:** `Citation`, `Critique`, `Reply`, `Defense`, `IdeaRevision`, `Debate`, `DebateFailure`, `AxisVerdict`, `Comparison`, `Rating`, `Tournament`, `RoleDigest`, `DebateRun`.
- **New enums:** `CritiqueTarget`, `Severity`, `DefenseMove`, `DefenseOutcome`, `ScoreAxis`.
- **Altered enum:** `RoleName` gains `prosecutor`, `skeptic`, `taste_critic`, `advocate` and `judge`.
- **Altered classes:**
  - `Usage` gains `web_search_requests`.
  - `Role` gains an optional `max_searches`, default 0. The generator role file stays valid unchanged.
- **`CaptureSource: prosecutor`** already exists. This change is the first to use it.

## Reproducibility and resumability

A `DebateRun` pins everything it can:
- the digest of the `Generation` file it read, and the `Generation`'s own pinned inputs;
- the SHA-256 of every role file;
- the catalog digest at start;
- the git commit and the tournament seed.

Resuming with any pinned input changed is refused, as it is for generations. The run is saved after every debate and every comparison, so a crash or a budget stop loses at most one call's work.

Elo ratings are recomputed deterministically from the stored comparisons, in seeded order. Model output and web search results are not deterministic, so a fresh run of the same inputs can differ. The record keeps exactly what was said and cited.

## Capabilities

### New Capabilities
- `idea-debate`: critic roles, the advocate's defense, the named-failure rule, prosecutor citations and their caching as works, and the debate record.
- `idea-tournament`: blind pairwise comparison, per-axis Elo ladders, survivor selection and the survivors report.

### Modified Capabilities
- `idea-generation`: these requirements change:
  - the shared ontology: new `RoleName` values, and `web_search_requests` on `Usage`;
  - role files: optional `max_searches`;
  - usage and cost: searches are priced;
  - config: debate and report locations, and the run budget.

## Impact

- **Schema:** `schema/seeker.yaml` and the regenerated `schema/generated/`.
- **Code:**
  - `seeker/ontology/`: new models;
  - `seeker/models/`: web search on `ModelRequest`, plus search counts, citations and `pause_turn` in `AnthropicModel`;
  - a new `seeker/debate/` package (roles, prompts, critic and advocate runners, tournament, record, report, CLI);
  - `seeker/config.py`: `debates` and `reports` paths, `budget_usd`, and the per-search price.
- **Other files:**
  - `prompts/`: five new role files;
  - `seeker.yaml`: the new paths, budget and search price;
  - `pyproject.toml`: the `seeker-debate` script.
- **Vault:**
  - new Ontology notes for each new class and enum;
  - updated notes for `Role`, `RoleName`, `Usage` and `CaptureSource`;
  - a decision note on the debate shape and blind per-axis Elo;
  - a hub update.
  - Runs also write prosecutor-found `Work` notes into `Works/`.
- **Cost:** a 12-idea run is estimated at $1.50-$3:
  - about 48 debate calls plus up to 36 searches;
  - 66 judge comparisons.
- **Dependencies:** none new. This uses the `anthropic` SDK already pinned.
