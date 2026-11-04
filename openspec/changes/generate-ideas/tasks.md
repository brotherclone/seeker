# Tasks

## 1. Ontology

- [x] 1.1 Add the `ModelId` and `GitCommit` types, the `Reading` and `RoleName` enums, and the `Usage`, `CardReading`, `Idea`, `GenerationFailure`, `ReadingGuidance`, `Role` and `Generation` classes with their slots to `schema/seeker.yaml` per design decision 1, every element described. Run `make schema`. Verify that `linkml-lint` and `tests/test_schema.py` pass.
- [x] 1.2 Extend the conformance test so `datetime` maps to `datetime` and `float` to `float`. Verify that the existing conformance tests still pass and that a planted model with `generated_at: str` fails.
- [x] 1.3 Implement the Python types, enums and models (`seeker/ontology/generation.py` and `role.py`), with `Usage.__add__`, `Role.guidance_for(reading)` and a `Role` validator requiring exactly one guidance per reading. Export them from `seeker.ontology`. Verify the conformance test passes, and that unit tests cover usage addition, guidance lookup, missing or duplicate guidance, temperature and token bounds, and `GitCommit`/`ModelId` patterns.
- [x] 1.4 Write the Obsidian concept notes `Idea`, `Generation`, `Role` and `Reading`, linked to `[[Draw]]`, `[[DrawBatch]]`, `[[Card]]` and the hub. Verify that their slot tables match the schema.

## 2. Config

- [x] 2.1 Add `seeker.yaml` per design decision 5 and implement `SeekerConfig`, `PathsConfig`, `PriceTable` and `ModelPrice` in `seeker/config.py`: discovery through `SEEKER_CONFIG` or the nearest file walking up, relative and `~` paths, `.env` parsing, refusing `api_key`, and `ModelPrice.cost(usage)`. Verify unit tests for discovery, path resolution, `.env` precedence, a missing key, a refused `api_key`, an unpriced model, and a cost calculation on known usage.
- [x] 2.2 Check the cache-read and cache-write multipliers against the official pricing page and correct `seeker.yaml` if they differ. Verify the `as_of` date and the values are recorded, with the source URL in a comment.

## 3. Model client

- [x] 3.1 Implement `ModelRequest`, `ModelReply`, the `LanguageModel` abstract base class, `ModelCallFailed` and `ScriptedModel` in `seeker/models/`. Verify that tests show `ScriptedModel` replays in order, records requests, and raises when it runs out of scripted replies.
- [x] 3.2 Implement `AnthropicModel`: forced tool choice, the system block marked for caching, the usage mapping, error wrapping, and the tool input serialized to JSON text. Add `anthropic` to the dependencies. Verify unit tests with the SDK client stubbed, plus an opt-in live smoke test with Haiku (`SEEKER_LIVE=1`) that is skipped by default.

## 4. Generator

- [x] 4.1 Add `prompts/generator.yaml` from design decision 4, and implement `RoleFile` loading with the digest. Verify that the file loads as a `Role` named `generator` with all three readings, and that a fixture missing `metaphorical` fails, naming the file and the reading.
- [x] 4.2 Implement `DrawPrompt.render()` (home field; each card's axis, name, synonyms, fields and note) and the system block built from the persona, rules and the selected reading's guidance. Verify tests: a card note appears in the prompt; metaphorical prompts contain only the metaphorical guidance; the default reading is literal; an unknown reading is rejected, naming all three.
- [x] 4.3 Implement `IdeaDraft`, its JSON tool schema, and `problems_for(draw)` (one sentence, at most 60 words, card coverage and order, non-empty parts). Verify unit tests for valid drafts, two sentences, abbreviations that should pass, too long, a missing card, a wrong card, and a wrong order.
- [x] 4.4 Implement `IdeaGenerator.generate` with one retry carrying the problems back, `GenerationFailure` on a second failure or a call error, per-idea usage, totals and estimated cost, and the unpriced-model check before any call. Verify `ScriptedModel` tests: a valid run of 12; recovery on retry, with both calls counted; a double failure at position 4 followed by later positions continuing; totals equal the sums; cost equals the priced totals; an unpriced model makes no calls.
- [x] 4.5 Implement incremental atomic writes, resume (skipping covered positions) and `ResumeMismatch`, plus the role digest and git-commit provenance. Verify tests: an interrupted run resumes with only the remaining draws sent; a reading mismatch is rejected, naming both readings; editing the role file changes the recorded digest; the record validates with `linkml-validate -C Generation`.

## 5. Command line and docs

- [x] 5.1 Implement `seeker-generate run` per design decision 7, with the console script. Add `generations/scratch/` to `.gitignore` and create `generations/.gitkeep`. Verify CLI tests with `ScriptedModel` injected:
  - a batch file and seed/size inputs;
  - the summary line;
  - `--dry-run` prints 12 prompts with no key and no calls;
  - a missing key fails before any call;
  - `--scratch` writes under `generations/scratch/`, and `git check-ignore` reports it ignored.
- [x] 5.2 Write `docs/generating.md` covering readings, the role file, `--dry-run` for prompt tuning, records and resume, cost estimates and the price table. Verify the documented dry-run command runs as written.

## 6. Record the decision

- [x] 6.1 Write `Seeker/Decisions/2026-11-04 Generator role and structured ideas.md`, covering structured output through a tool, card readings, the embedded batch, the readings, and cost measured but not enforced. Update the hub. Verify that the note links to the hub, the concept notes and `generate-ideas`.

## Workflow follow-up

- Open a PR from `feature/generate-ideas` into `develop`, and archive the change after merge.
- First real use: `seeker-generate run --batch batches/2026-11-04-round-1.yaml --out ...`, reviewed by Gabe before `prior-art-works` and `debate-ideas`.
