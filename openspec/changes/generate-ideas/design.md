# Design

## Context

- `seeker.ontology` mirrors `schema/seeker.yaml`, and a two-way conformance test keeps them in sync.
- `seeker.draw.BatchDrawer` produces `DrawBatch` records, which are written to `batches/`.
- No code calls a model yet. The project runs locally on Gabe's Mac, takes every location from config, and caps nightly spend. Cost here is measured but not enforced; enforcement comes with the run change.
- Motivation is in proposal.md; requirements are in `specs/idea-generation/spec.md`.

## Goals / Non-Goals

**Goals:**
- One `Idea` per draw, structured and validated, with the generator's reading of every card kept for the critics later.
- Patterns the debate roles will reuse unchanged:
  - roles as YAML;
  - a model client with a test double;
  - structured output through a tool;
  - usage and cost accounting;
  - incremental, resumable records.
- A cheap way to tune prompts: `--dry-run` shows exactly what the model would see.

**Non-Goals:**
- Scoring or judging ideas.
- Prior-art search.
- The Batch API.
- Enforcing the spend cap.
- Writing to the vault.
- SQLite.
- More than one role.

## Decisions

### 1. Ontology additions (schema first)

```yaml
types:
  ModelId:   {typeof: string, pattern: "^claude-[a-z0-9-]+$"}       # e.g. claude-opus-5-5
  GitCommit: {typeof: string, pattern: "^[0-9a-f]{40}(-dirty)?$"}   # -dirty when the tree had changes

enums:
  Reading:  {literal, loose, metaphorical}     # each value described
  Effort:   {low, medium, high, xhigh, max}    # the API's output_config.effort
  RoleName: {generator}                        # debate-ideas adds prosecutor, skeptic, ...

classes:
  CardReading:       card (Card ref by CardId), interpretation (string, required)
  Idea:              position, statement, subject, behavior, rationale,
                     card_readings (CardReading x3, inlined), usage (Usage)
  GenerationFailure: position, reason, usage
  Usage:             input_tokens, output_tokens, cache_read_tokens, cache_write_tokens (integers >= 0)
  ReadingGuidance:   reading (Reading), guidance (string)
  Role:              role_name, model, persona, system_prompt,
                     reading_guidance (ReadingGuidance x3, inlined), max_output_tokens, effort (Effort)
  Generation:        draw_batch (DrawBatch, inlined), reading, role_name, model,
                     role_digest (Sha256Digest), git_commit (optional), generated_at (datetime),
                     ideas (Idea*), failures (GenerationFailure*), usage (Usage), estimated_cost_usd (float)
```

- **The batch is embedded, not referenced.** A generation record is self-contained: it holds the batch, so the ideas, cards and seed are all in one file. The batch is small, about 2 KB.
- **`Idea` keeps both the sentence and its parts.** The sentence is what a person reads. The parts keep the X/Y/Z form honest, and the critics can attack a specific part later.
- **`CardReading` holds an interpretation per card.** Under a metaphorical reading this is the only record of what "Oramics" was taken to mean, and both the critics and Gabe need it.
- **The conformance test gains `datetime` → `datetime` and `float` → `float`.** Python models live in `seeker/ontology/generation.py` and `role.py`.

### 2. Structured output through a forced tool call

The generator receives one tool, `submit_idea`, and `tool_choice` forces the model to call it. The tool's `input_schema` is `IdeaDraft.model_json_schema()`. `IdeaDraft` is a slim model (statement, the three parts, card readings) without usage or position, which are known locally.

Validation runs in two layers:
1. **Shape:** Pydantic parses the tool input JSON into `IdeaDraft`.
2. **Meaning:** `IdeaDraft.problems_for(draw)` returns typed `DraftProblem`s, each of which can be read out in plain words:
   - **One sentence:** after trimming there must be no sentence-ending `.`, `!` or `?` followed by whitespace and then more text. Abbreviations like "e.g." are excepted.
   - **Length:** at most 60 words.
   - **Card coverage:** the card readings' ids equal the draw's `drawn_cards`, in order.
   - **Content:** every part and interpretation is non-empty.

*Alternative considered: free text parsed with a regex.* Rejected: brittle, and it can't carry card readings.

*Alternative considered: the SDK's native structured-output mode.* It's viable, but forced tool use is the long-standing, well-understood path, and it carries the same Pydantic schema. If the native mode proves simpler, switching later only touches `AnthropicModel`.

### 3. The model client

`seeker/models/`:
- `ModelRequest` holds system blocks, user turns, the tool, max tokens and effort.
- The `anthropic` 2.x SDK has no sampling parameters, so there is no `temperature`. Effort (`low` to `max`) is sent as `output_config.effort`. A test checks every argument against the installed SDK's `Messages.create` signature.
- `ModelReply` holds the tool input as raw JSON text, the `Usage` and the stop reason.
- `LanguageModel` is an abstract base class with `reply(request) -> ModelReply`. It has two implementations:
  - `AnthropicModel` wraps the `anthropic` SDK. It maps SDK usage fields to `Usage` and turns SDK errors into a `ModelCallFailed` error. The tool input is serialized with `json.dumps`, so no dict ever leaves the adapter.
  - `ScriptedModel(replies)` returns scripted replies in order and records the requests it received. All tests use it, so no test needs network access or a key. One opt-in smoke test (`SEEKER_LIVE=1`) calls the real API with Haiku.
- **Prompt caching:** the system block (persona, rules, reading guidance) is identical for every draw in a generation, so it is marked `cache_control: ephemeral`. Draws 2 to 12 then read it from cache, and that shows up in the cache-read token counts.

### 4. The generator role: a first draft of the prompt

`prompts/generator.yaml` (a `Role`):

```yaml
role_name: generator
model: claude-opus-5-5
max_output_tokens: 1200
effort: high
persona: >-
  You are an artist-engineer who has shipped instruments, zines, small games,
  installations and odd hardware, mostly alone and on small budgets. You read
  NIME proceedings and demoscene NFOs with equal pleasure. You are allergic to
  "an app that uses AI to..." and to ideas that only work as a pitch deck.
system_prompt: >-
  You receive three cards drawn from Seeker's decks: always one constraint,
  plus two of technique, medium, historical artifact and domain. Collide them
  into ONE idea and submit it with the submit_idea tool.
  Rules:
  - State the idea as one sentence of the form "a/an X that does Y because Z".
    Z must be a real reason the idea works or matters, not a restatement.
  - Use all three cards. The constraint is binding: the idea must satisfy it.
  - The idea must be buildable or performable by one person with modest means.
  - Anchor it in the draw's home field.
  - For each card, say in one line how you read it.
  - No hedging, no options, no lists of variations. Commit to one idea.
reading_guidance:
  - reading: literal
    guidance: >-
      Read each card as exactly what it names. Oramics means Daphne Oram's
      drawn-sound machine and the technique of drawing sound on film.
  - reading: loose
    guidance: >-
      Read each card by its spirit as well as its letter. Oramics may mean
      drawing as a way of composing, not necessarily on film.
  - reading: metaphorical
    guidance: >-
      Read each card for what it evokes. Oramics may stand for a lone inventor
      building a machine nobody asked for, or for sound you can see. Say in
      your card readings what you took each card to stand for.
```

**The user message** is assembled in code (`DrawPrompt.render()`), not templated in YAML. It lists the draw's home field, then each card with its axis, name, synonyms, fields and note. That way every card is always presented the same way. The literal text of every prompt is visible with `--dry-run`.

**The role digest** is the SHA-256 of the role file's bytes, so any edit, including to a comment, creates a new digest.

### 5. Config: `seeker.yaml` and `SeekerConfig`

```yaml
paths:                          # relative to this file
  decks: decks
  batches: batches
  generations: generations
  prompts: prompts
  vault: null                   # e.g. ~/Documents/Claude/Projects/Bracers/Projects; used by later changes
prices:                         # USD per million tokens; prices are data, update as they change
  as_of: 2026-11-04
  models:
    - {model: claude-opus-5-5,   input: 4.00, output: 20.00, cache_read: 0.40,  cache_write: 5.00}
    - {model: claude-sonnet-5-5, input: 2.00, output: 10.00, cache_read: 0.20,  cache_write: 2.50}
    - {model: claude-haiku-5-5,  input: 0.10, output: 0.50,  cache_read: 0.01,  cache_write: 0.125}
```

- **Finding the file:** `SeekerConfig.load()` uses `SEEKER_CONFIG` if it's set, and otherwise walks up from the current directory to the nearest `seeker.yaml`. Paths are resolved relative to the file, and `~` is expanded.
- **API key:** read from `ANTHROPIC_API_KEY`, falling back to `.env` next to `seeker.yaml`. A tiny `KEY=value` parser handles `.env`, so no new dependency is needed. The config model forbids an `api_key` key.
- **Prices:** the list input and output prices were checked on 2026-11-04. The cache multipliers (0.1× read, 1.25× write) are assumed standard and should be verified against the official pricing page during apply. `ModelPrice.cost(usage)` computes dollars.
- These config models are tooling models: they have no `class_uri`, following the same pattern as `DeckDigest`.

### 6. The generation loop and resume

`IdeaGenerator(role, model, config).generate(batch, reading, record=None)` works through the draws in position order:
- It skips positions already covered by `record`.
- It calls the model, validates, and retries once with the problems as a follow-up user turn, keeping the conversation so the model sees its own attempt.
- It records an `Idea` or a `GenerationFailure` with the summed usage.
- When writing to a file, it rewrites the record atomically after each draw (write to a temp file, then `os.replace`). An interruption loses at most the draw in flight.

**Resume checks:** the existing record's batch (seed and digest), reading and role digest must equal the request, or `ResumeMismatch` is raised, naming the differing field.

### 7. Command line

```
seeker-generate run (--batch PATH | --seed N [--size 12]) [--reading literal|loose|metaphorical]
                    [--role prompts/generator.yaml] [--out PATH | --scratch] [--label NAME] [--dry-run]

 1  [music]     a webcomic that can only be read by ... because ...
 2  [visual-art] ...
 4  FAILED  two sentences after retry
12 ideas · 1 failure · 18,420 in / 6,100 out / 15,900 cache-read tokens · est. $0.21 (claude-opus-5-5, literal)
```

- `--scratch` writes `generations/scratch/<date>-<seed>-<reading>.yaml`.
- `--out` without a path suffix gets `generations/<date>-<label>.yaml`.
- `generations/scratch/` is added to `.gitignore`, and `generations/.gitkeep` is created.

### 8. Obsidian

- Concept notes `Idea`, `Generation`, `Role` and `Reading`.
- A decision note: `2026-11-04 Generator role and structured ideas`.
- A hub update.

## Risks / Trade-offs

- [The one-sentence check is a heuristic and can misfire on abbreviations or quotes] → There is an abbreviation allowlist, and a misfire only costs a retry. Unit tests cover the known cases.
- [The forced tool schema rejects creative formatting] → Intended: the critics need structure. The persona and rules leave all the creativity in the content.
- [The price table goes stale] → Prices are data with an `as_of` date, and the estimate is labelled as an estimate. The run change can warn when `as_of` is old.
- [The draft prompt is a guess] → `--dry-run` and a 12-idea generation at about $0.15 make it cheap to iterate. Each edit shows up as a new role digest, so results stay attributable.
- [Opus for the generator costs more than needed] → The model is one line in the role file, and the generation records which model ran. Comparing Opus and Sonnet is a one-night experiment.

## Open Questions

- Should the generator see the deck's one-line axis descriptions as framing? That's a prompt tweak, testable with `--dry-run`. It doesn't affect the specs.
