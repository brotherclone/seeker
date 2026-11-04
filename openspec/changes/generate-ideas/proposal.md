# Proposal

## Why

Seeker can draw balanced, reproducible triples, but nothing turns a triple into an idea yet. This is the first agent role and the cheapest end-to-end test of the whole bet: draw 12, get 12 one-sentence ideas, and judge whether they're worth arguing about before building the debate. It also sets the patterns every later role reuses:
- prompts as versioned YAML;
- a per-role model;
- structured output validated against the ontology;
- token and cost accounting.

## What Changes

- **New ontology classes:**
  - `Idea`: one sentence of the form "an X that does Y because Z", stored as both the full statement and its three parts, plus a reading of each drawn card.
  - `CardReading`: how the generator interpreted one card.
  - `Generation`: one generator pass over a `DrawBatch`, with its ideas, failures, provenance and usage.
  - `Role`: a role's model, persona, prompts and per-reading guidance.
  - `Usage`, `GenerationFailure` and `ReadingGuidance`.
- **New enums and types:**
  - `Reading`: `literal`, `loose`, `metaphorical`.
  - `RoleName`: `generator` for now; the debate change adds the rest.
  - `ModelId` and `GitCommit`.
- **`prompts/generator.yaml`:** the generator role as a `Role` instance. The model defaults to Opus, and each reading level has its own guidance text. It is versioned in git, and every generation records the prompt file's digest.
- **The reading setting:** `literal` by default, while round 2 will use `metaphorical`. The chosen reading's guidance goes into the prompt, and the reading is recorded on the `Generation`.
- **Structured output:**
  - The generator answers through a tool whose input schema comes from the ontology.
  - The response is validated: one sentence, all three cards read, each reading tied to the right card.
  - An invalid response gets one retry with the validation errors sent back. If it fails again, the draw is recorded as a `GenerationFailure` and the batch continues.
- **Accounting:**
  - Every model call's tokens (input, output, cache reads and writes) are recorded per idea and totalled.
  - The estimated dollar cost comes from a price table in config, so prices are data, not code.
- **Local config (`seeker.yaml`):**
  - Locations: decks, batches, generations and the vault.
  - The model price table.
  - The API key comes from the environment or a git-ignored `.env`.
- **New command:** `seeker-generate` takes a recorded batch or a seed/size, a `--reading` and `--out | --scratch`, plus `--dry-run`, which renders every prompt with no API calls. It writes a `Generation` record to `generations/`. As with batches, `generations/scratch/` is git-ignored.

Out of scope:
- **Critics, advocate, judge, prior-art search and `debate-ideas`.** Only the `generator` role exists for now.
- **The Batch API, the nightly launchd job, the hard spend cap and Keychain lookup.** These belong to the run/scheduling change. This change measures cost but doesn't enforce the cap.
- **Writing ideas into the Obsidian vault.** Nightly notes come with the run change. The vault path is only read from config here, so the config shape is settled now.
- **Persisting to SQLite.** A generation is a YAML record for now.

## Capabilities

### New Capabilities
- `idea-generation`: turning each `Draw` of a `DrawBatch` into one structured, validated `Idea` at a chosen `Reading`, with usage, cost and provenance recorded in a `Generation`.

### Modified Capabilities
None. `card-decks` and `card-draws` are only read.

## Impact

- **Engine stage and role:** this adds the **generator** role, the stage after the draw. The decks and the draw are unchanged.
- **Reproducibility:**
  - Model output isn't deterministic, so a generation can't be replayed byte for byte. Everything that goes into it is pinned instead: the embedded `DrawBatch` (seed and deck-set digest), the role's model id, the prompt-file digest, the reading, and the git commit when available.
  - Two generations that differ only in reading are a controlled comparison, which is round 2.
  - Resumability: if a run is interrupted, a batch re-run skips draws that already have ideas in the target record. Full resumable runs come with the run change.
- **Ontology:**
  - classes `Idea`, `CardReading`, `Generation`, `GenerationFailure`, `Role`, `ReadingGuidance`, `Usage`;
  - enums `Reading`, `RoleName`;
  - types `ModelId`, `GitCommit`;
  - slots for each.
  - The conformance test learns the `datetime` and `float` ranges.
- **Code:**
  - `seeker/config.py` for `SeekerConfig`;
  - `seeker/models/`, the language-model client: `AnthropicModel` for real calls and `ScriptedModel` for tests;
  - `seeker/generate/`, with the `IdeaGenerator`, prompt rendering and CLI;
  - `prompts/generator.yaml` and `seeker.yaml`.
- **Dependencies:** `anthropic`, the official SDK.
- **Cost:** about $0.15 per 12-idea generation on Opus at list price (estimated). `--dry-run` costs nothing.
- **Docs and notes:** `docs/generating.md`; Obsidian concept notes for `Idea`, `Generation`, `Role` and `Reading`; a decision note.
