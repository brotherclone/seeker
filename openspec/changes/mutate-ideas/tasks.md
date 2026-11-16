# Tasks

## 1. Ontology: mutation classes and altered slots

- [x] 1.1 In `schema/seeker.yaml`, add the following, all described:
  - the enum `MutationKind` and the classes `Lineage` and `MutationOrigin`, with their slots (design decision 1);
  - `mutator` in `RoleName`;
  - the optional slots `lineage` on `Idea`, `mutation` on `Generation` and `carried_from` on `Debate`, and `both_orders` (`ifabsent: false`) on `Tournament`;
  - a sentence in `DrawBatch`'s description on mutated batches.

  Run `make schema`. Verify `linkml-lint` and `tests/test_schema.py` pass.
- [x] 1.2 Add `seeker/ontology/mutation.py` with `MutationKind`, `Lineage` and `MutationOrigin`, with rich `Field` metadata. `Lineage` must require `swapped_axis` and `replaced_card` exactly when the kind is `card_swap`. Export them from `seeker.ontology`. Verify the conformance test, and unit tests for the `Lineage` validator.
- [x] 1.3 Add `lineage` to `Idea` and `mutation` to `Generation`. `Generation` must validate that ideas have a lineage exactly when `mutation` is set. Add `mutator` to `RoleName`. Verify:
  - the conformance test passes;
  - both round-1 generation records load with no lineage;
  - a generation with `mutation` but an idea lacking lineage is rejected.
- [x] 1.4 Add `carried_from` to `Debate` and `both_orders` to `Tournament`. Verify the conformance test passes, and `debates/2026-11-14-round-1-literal.yaml` loads with `both_orders` false and its ratings recompute exactly.

## 2. Config and the mutator role

- [x] 2.1 Add a `mutation` config section (`reworkings`, default 2, minimum 1) and `tournament.both_orders` (default true) to `SeekerConfig`. Raise the `tournament.max_comparisons` default to 132. Update `seeker.yaml` to match. Verify with config tests for each default and for `mutation.reworkings: 0` being rejected.
- [x] 2.2 Write `prompts/mutator.yaml`:
  - model `claude-opus-5-5`, `effort: high`;
  - the generator's persona, copied verbatim;
  - a system prompt with the reworking and card-swap rules from design decision 4;
  - the three `reading_guidance` entries.

  Verify the role loads through `LoadedRole`, and `prompts/generator.yaml`'s digest is unchanged.

## 3. Mutation plan

- [x] 3.1 Implement `MutationPlan` in `seeker/mutate/plan.py`. It is a pure build from the parent run, the parent generation, the deck set, the seed and the reworkings setting. It emits the child and carried draws with positions and lineages, using `TournamentStream(seed, "mutation")` for swaps (design decision 3). Verify with unit tests on fixture decks:
  - the default plan has 12 children in the right kinds and order, then 3 carried;
  - a swap keeps the axes, the home field and the other two cards;
  - the home-field narrowing applies when the replaced card was the only one listing the field;
  - no replacement repeats a card in the plan;
  - the same inputs give identical plans.
- [x] 3.2 Add the plan's refusals: a parent run whose tournament did not finish, and a parent generation whose digest doesn't match the run's `generation_digest`. With fewer than three survivors, the plan covers just those. Verify with unit tests that each refusal message names its reason, and that a two-survivor run plans 8 children and 2 carried.

## 4. Mutator and record

- [x] 4.1 Implement `MutationPrompt` in `seeker/mutate/prompt.py` (design decision 4). For reworkings, it renders the parent's final form and parts, card readings, critiques with replies, and the draw. For swaps, it marks the new card. The second reworking also sees the first's statement. Verify with tests that:
  - a revised parent's prompt contains its revision, three failures and three replies;
  - a swap prompt names the new card;
  - the second reworking's prompt contains the first child's statement.
- [x] 4.2 Implement `IdeaMutator`. Each child is generated through `IdeaDraft` with one retry, and checked by `problems_for(child_draw)`. The result gets its plan lineage, and failures become `GenerationFailure`s. Carried parents are copied with their new position and a `carried` lineage, and make no call. Verify with a fake `LanguageModel`:
  - 12 calls for the default plan;
  - a reading naming the replaced card is retried and then recorded as a failure;
  - the carried ideas equal their parents except for position and lineage.
- [x] 4.3 Save after each child, through the existing `GenerationSink`. Resume skips covered positions. It refuses, naming the field, a mismatch in the parent run digest, mutation seed, mutator role digest, model or deck set digest. Verify with tests for:
  - resume after 5 children;
  - a changed parent run file is refused;
  - a changed deck file is refused.

## 5. Debate: carried debates and two-order judging

- [x] 5.1 Implement `CarriedDebates`. It loads the parent run from `MutationOrigin.parent_run_path`, checks its SHA-256, and copies each carried idea's debate with the new position and `carried_from`. Wire it into `DebateRunner.start` and resume, so carried positions are filled with no usage and skipped. Verify with runner tests:
  - a mutated generation with 3 carried ideas makes calls for the children only;
  - the carried debates equal their parents' except for position and `carried_from`;
  - a tampered parent file is refused before any call.
- [x] 5.2 Update `seeker-debate --dry-run` to list carried positions as carried, with no critic prompts and no calls counted for them. Verify with a CLI test on a fixture mutated generation: 12 prompted ideas, 3 carried, and a tournament planned for 15 entrants.
- [x] 5.3 Add `both_orders` to `Schedule.build`. Pairs are chosen from `max_comparisons // 2`, and each pairing is followed directly by its reverse. Without the flag, the existing schedule is unchanged. Verify with schedule tests:
  - 12 entrants with 132 give 132 comparisons over 66 distinct pairs, each reverse adjacent;
  - 15 entrants give equal opponents and no repeated pair;
  - the round-1 record's schedule still matches its recorded comparisons.
- [x] 5.4 In `TournamentRunner`, set `Tournament.both_orders` from config at start, and use the recorded value on resume. Verify with tournament tests:
  - a new run records `both_orders` true;
  - resuming a recorded single-order run keeps its single-order schedule;
  - a budget stop between a pair and its reverse resumes with the reverse.

## 6. Report

- [x] 6.1 Add the judge-health section to `SurvivorReport`. It shows:
  - the A-win share per axis;
  - the split count per axis for two-order tournaments;
  - critique severities per critic;
  - defense-outcome counts.

  Verify a report test on `debates/2026-11-14-round-1-literal.yaml` shows A winning 44/66 on novelty, 29/66 on feasibility and 34/66 on promise. Verify a fixture two-order tournament counts one split for a pair judged "A" both times.
- [x] 6.2 Add lineage to the report for mutated generations: a parent/kind column with ↑/↓ against the parent's promise rating, a per-parent block of children, and `carried` markers. Add a note when the parent run's role digests differ from this run's. Verify with a report test on a fixture mutated run.
- [x] 6.3 Re-render `reports/2026-11-14-round-1-literal.md` with `seeker-debate report`. Verify the only diff is the new judge-health section.

## 7. Command line

- [x] 7.1 Add `seeker-mutate` (`seeker/mutate/cli.py`, with a script in `pyproject.toml`), with `RUN`, `--out`/`--scratch`, `--seed`, `--dry-run` and `--config` (design decision 8). It prints a line per child and a usage summary. Without `--out`, `--scratch` or `--dry-run`, it errors. Verify with CLI tests using a fake model:
  - the dry run prints 12 prompts and 3 carried lines, with no key needed;
  - a scratch run lands in `generations/scratch/`, which `git check-ignore` reports ignored;
  - an unfinished run exits 1 with the reason.
- [x] 7.2 Integration check: run the fake-model pipeline end to end on fixtures. `seeker-mutate` feeds `seeker-debate run`, which feeds `seeker-debate report`. Verify:
  - the mutated generation and the debate run both validate against the schema (with `Generation` and `DebateRun` as target classes);
  - the report lists 15 entrants with lineage and judge health.

## 8. Documentation and vault

- [x] 8.1 Update `README.md` with the `seeker-mutate` command and the round-2 workflow (mutate, then debate, then report). Update `docs/concept.md`'s plan to mark mutation as built. Verify that the commands as written run in dry-run mode.
- [x] 8.2 In the vault:
  - add `Ontology/Lineage.md`, `Ontology/MutationOrigin.md` and `Ontology/MutationKind.md`, each with its definition, its slots with ranges, and wikilinks;
  - update `Idea.md`, `Generation.md`, `Debate.md`, `Tournament.md`, `RoleName.md`, `Role.md` and `DrawBatch.md`.

  Verify every new note links back to `[[Seeker]]` and its frontmatter has `type: concept` and `openspec: mutate-ideas`.
- [x] 8.3 Write `Decisions/2026-11-16 Mutation and two-order judging.md` covering the choices in design decision 9. Update `Seeker.md`:
  - the new ontology entries;
  - the `mutate-ideas` status line;
  - the "Next" list, with `mutate-survivors` renamed and the first live debate marked done.

  Verify the decision note links to its concepts and to the change, and that the hub links it.

## Workflow follow-up

- Open a PR from `feature/mutate-ideas` into `develop`.
- After merge, run round 2 live: `seeker-mutate debates/2026-11-14-round-1-literal.yaml --out generations/<date>-round-2-literal.yaml`, then `seeker-debate` on the result, committed on its own `feature/` branch like PR #16.
- Check the round-2 judge-health section against the debate severity watch.
- Archive the change.
