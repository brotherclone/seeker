# Design

## Context

- **What can be reused.** Generation already has every piece mutation needs:
  - `LoadedRole`, the `LanguageModel.reply(ModelRequest)` boundary, `IdeaDraft` (parse, `problems_for(draw)`, `to_idea`) with one retry;
  - `DrawPrompt` for rendering cards, and `GenerationSink` with its resume checks (`seeker/generate/`).
  - `IdeaDraft.problems_for(draw)` already rejects card readings that don't match the draw, so a child is validated against its own draw for free.
- **What debate reads.** `seeker-debate` reads a `Generation`: its `ideas` and its `draw_batch.draws`, matched by position. `DebateRunner`, `TournamentRunner` and `SurvivorReport` read nothing else from it. A mutated generation that is a valid `Generation` therefore runs through debate with no change, except for carried parents.
- **The schedule today.** `Schedule.build` already seeds which idea is A (the `sides` stream), so the 44/66 novelty skew is the judge's, not the schedule's. `Ladder.play` treats each `Comparison` as one Elo game.
- **Round-1 cost.** The 66 Sonnet judge calls took about 300k input and 21k output tokens, about $0.81. The 12 debates cost about $1.41.
- **Pointers.** Motivation is in proposal.md. Requirements are in `specs/idea-mutation`, `specs/idea-tournament`, `specs/idea-debate` and `specs/idea-generation`.

## Goals / Non-Goals

**Goals:**
- **One shape for every generation.** A mutated generation is an ordinary `Generation`, so debate, tournament and report treat round 2 like round 1.
- **No paying twice.** Parents are never debated again.
- **Reproducible as before.** Draws and schedules are seeded, and every record pins its parent by digest.

**Non-Goals:**
- More than one round per command, or any scheduling (the nightly-run change).
- SQLite. Lineage is followed through `MutationOrigin` paths and digests; one hop per round is cheap at this scale.
- Crossover between two parents, or mutating the constraint card.
- Changing the judge's prompt. Only its schedule changes.
- Deduplicating a child that turns out too close to its parent. The tournament and the report's "outrated its parent" line show it.

## Decisions

### 1. Schema first: what LinkML gains

New enum and classes:

```yaml
MutationKind:
  description: How an idea in a mutated generation relates to its parent.
  permissible_values:
    reworking: {description: The parent's three cards, rewritten into a different idea after reading its debate.}
    card_swap: {description: The parent's draw with one non-constraint card replaced by a seeded card from the same deck.}
    carried:   {description: The parent itself, carried into the next round with its debate.}

Lineage:
  description: Where an idea in a mutated generation came from.
  slots: [parent_position, mutation_kind, swapped_axis, replaced_card]
  slot_usage:
    swapped_axis:  {required: false}   # card_swap only
    replaced_card: {required: false}   # card_swap only

MutationOrigin:
  description: The debate run a mutated generation was bred from.
  slots: [parent_run_path, parent_run_digest, mutation_seed, round]

parent_position:   {range: integer, minimum_value: 1, slot_uri: seeker:parentPosition}
mutation_kind:     {range: MutationKind, slot_uri: seeker:mutationKind}
swapped_axis:      {range: AxisId, slot_uri: seeker:swappedAxis}
replaced_card:     {range: CardId, slot_uri: seeker:replacedCard}
parent_run_path:   {range: string, slot_uri: seeker:parentRunPath}
parent_run_digest: {range: Sha256Digest, slot_uri: seeker:parentRunDigest}
mutation_seed:     {range: integer, minimum_value: 0, slot_uri: seeker:mutationSeed}
round:             {range: integer, minimum_value: 2, slot_uri: seeker:round}
```

Altered elements. Every new slot is optional or has a default, so all existing records validate unchanged:

```yaml
RoleName:   {permissible_values: {mutator: {description: Breeds new ideas from a debated survivor.}}}
Idea:       {slots: [..., lineage]}          # lineage: {range: Lineage, required: false}
Generation: {slots: [..., mutation]}         # mutation: {range: MutationOrigin, required: false}
Debate:     {slots: [..., carried_from]}     # carried_from: {range: integer, minimum_value: 1, required: false}
Tournament: {slots: [..., both_orders]}      # both_orders: {range: boolean, ifabsent: false}
```

`DrawBatch`'s description gains a sentence. A mutated generation's batch is rebuilt from its `MutationOrigin`, not by `BatchDrawer`, and its `seed` is the mutation seed.

The Pydantic mirrors then follow:
- `Lineage`, `MutationOrigin` and `MutationKind` in a new `seeker/ontology/mutation.py`;
- the new fields on `Idea`, `Generation`, `Debate` and `Tournament`.

Validators:
- `Lineage` requires `swapped_axis` and `replaced_card` exactly when the kind is `card_swap`.
- `Generation` requires that an idea has a lineage exactly when `mutation` is set.
- `Debate` adds no rule for `carried_from`.

The conformance test covers all of them.

### 2. A mutated generation is a `Generation`

`seeker-mutate` writes a `Generation` with `mutation` set, and its own `DrawBatch` of 15 draws: 12 children, then 3 carried parents.
- **Alternative:** a separate `Mutation` record type that debate learns to read. Rejected. Every consumer would need a second input type, and records are compared across rounds most easily when they share one shape.
- **Cost:** `DrawBatch` no longer always means "drawn by `BatchDrawer` from a seed". The `mutation` slot marks the exception, and the generation's resume check replays the plan instead of the drawer.

### 3. The mutation plan

`MutationPlan.build(parent_run, parent_generation, deck_set, seed, reworkings)` is pure. For each survivor in rank order, it emits:
- `reworkings` copies of the parent's draw;
- one swap per non-constraint axis, in the draw's axis order;
- after all children, the carried parents.

Swaps draw from `TournamentStream(seed, "mutation")`, a new salt on the existing SHA-256 stream. For each swap, the candidates are:
- the deck's cards that are in no draw of the plan so far and not among the parent run's cards;
- narrowed to cards that list the home field, if the card being replaced was the only card in the draw listing it.

If no candidate is left, the plan fails, naming the parent and axis. That cannot happen with 15-card decks and at most 6 swaps per axis.

Positions run 1 to 15. `Lineage.parent_position` refers to the parent run's position, so it stays meaningful when read next to the parent record.

### 4. The mutator role

`prompts/mutator.yaml` is a new `Role`:
- `role_name: mutator`;
- model `claude-opus-5-5`, `effort: high`;
- the generator's persona, copied verbatim, so the voice that wrote round 1 writes round 2.

Its system prompt adds:
- **Reworking:** "keep the three cards; the advocate's revision is already the polished version, so do not polish it. Find a different idea in the same collision that answers the strongest objection."
- **Card swap:** "one card is new; use all three cards. Keep what the debate showed works, and drop what it showed fails."

The prompt states the idea form, the one-sentence rule and the "commit to one idea" rule exactly as the generator's prompt does. `reading_guidance` is copied too.

- **Alternative:** add mutation instructions to `generator.yaml`. Rejected. It changes the generator's digest, so the round-1 generation records would no longer resume. It also gives one role two jobs.
- **Alternative:** a different model for the mutator. Rejected for now. The voice that matters for consensus collapse is the critics', and they are unchanged.

`MutationPrompt` renders, in this order:
- the parent's final statement and parts (the revision's when it was revised);
- its card readings;
- each critique's failure and argument, with the advocate's move and reply;
- the child's draw, through `DrawPrompt.card_lines()`.

Critiques here keep their role names. The mutator is not a judge, and knowing that an objection came from the prior-art prosecutor is useful to it. For a swap, the prompt says which card is new. The second reworking's prompt gets the first's statement, under "already taken; go elsewhere".

### 5. Carried debates

`DebateRunner.start` (and resume) receives `CarriedDebates`, loaded by the CLI when `generation.mutation` is set:
- it reads `parent_run_path` relative to the repository root;
- it checks the file's SHA-256 against `parent_run_digest`;
- it copies each carried idea's debate with `position` renumbered and `carried_from` set.

Carried debates are inserted before the first new debate, with no usage. `debate_all` then skips their positions. The dry run lists them as "carried" and counts no calls for them.

The tournament's `entrants()` needs no change. A carried parent's `Idea` is in the generation and its `Debate` is in the run.

### 6. Judging in both orders

`Schedule.build(entrants, seed, max_comparisons, both_orders)` picks the pair set as before, from `max_comparisons // 2` pairs when `both_orders` is set. After the seeded pair order and seeded sides, it emits each `Pairing` followed directly by its reverse.
- **Elo:** each comparison stays one game. Over a pair's two games, position bias adds to one side and subtracts from the other, so it roughly cancels.
- **Alternative:** combine the two judgments of a pair into one game, scoring a split as a draw (0.5). Rejected for now. It needs a new paired-comparison class and changes `Ladder`. Two games per pair keep the record shape, and `Ratings.recompute` is unchanged.
- **Records:**
  - `Tournament.both_orders` is set from config at tournament start.
  - On resume, the recorded value wins, so an old single-order run replays its own schedule.
  - `TournamentConfig` gains `both_orders` (default true), and `max_comparisons` defaults to 132.
- **The judge's objection shuffle.** It is salted by `(first, second, position)`, so the reversed pairing gets a different objection order. That also blinds order effects within each side.

With 15 entrants and 132 calls, the schedule fits 66 pairs: `k = min(14, 2·66 // 15) = 8` opponents each. That is 60 pairs and 120 calls. A child need not meet its own parent: the report compares their promise ratings, not a head-to-head result. Round robin would need 210 calls (about $2.70). Keeping to 132 holds round 2 near $3.50.

### 7. Report sections

`SurvivorReport` gains two sections. Both are computed from the records, with no API call.
- **Lineage**, when `generation.mutation` is set. It is a column in the ranking tables: the parent, the kind, and "↑" or "↓" against the parent's promise rating in this tournament. It also has a short per-parent block listing its children in promise order.
- **Judge health:**
  - the A-win share per axis;
  - for two-order tournaments, the split count per axis (pairs whose two comparisons named different winners);
  - severity counts per critic;
  - defense-outcome counts.

  This is the "debate severity watch" made routine, rather than a check done by hand each run.

### 8. Command line

`seeker-mutate RUN.yaml [--out PATH | --scratch] [--seed N] [--dry-run] [--config PATH]`. It is structured like `seeker-generate`:
- it loads the config, the decks, the mutator role and the parent run with its generation;
- it refuses an unfinished run;
- it builds the plan and generates the children, saving after each;
- it prints a line per child and a usage summary.

The default `--out` suggestion in the help is `generations/<date>-round-<n>-<reading>.yaml`. It is not written implicitly. As in debate, either `--out` or `--scratch` is required unless `--dry-run` is given.

### 9. Obsidian notes

New `Ontology/` notes:
- `Lineage.md`
- `MutationOrigin.md`
- `MutationKind.md`

Updated `Ontology/` notes:
- `Idea.md` (lineage)
- `Generation.md` (mutation)
- `Debate.md` (carried_from)
- `Tournament.md` (both_orders)
- `RoleName.md` and `Role.md` (mutator)
- `DrawBatch.md` (the mutated-batch exception)

Decision: `Decisions/2026-11-16 Mutation and two-order judging.md` records:
- reworkings plus swaps;
- carried parents;
- one round per command;
- a separate mutator role;
- a mutated generation as a `Generation`;
- two games per pair, rather than a draw on splits;
- the 132-call cap.

The hub, `Seeker.md`:
- the `mutate-ideas` status line;
- the "Next" list, with `mutate-survivors` renamed to `mutate-ideas`;
- the new ontology entries.

## Risks / Trade-offs

- [Reworkings collapse onto the parent, because the advocate's revision has already taken the obvious fix] → The prompt forbids polishing the revision, and the second reworking must avoid the first. The report's ↑/↓ line shows it if it happens anyway.
- [Carried parents are judged against children debated under newer critic prompts] → A role edit between rounds changes the critics' role digests, which the `DebateRun` records. The report notes when the parent run's role digests differ from this run's.
- [Two games per pair still let a consistent first-position bias shift ratings when a budget stop leaves one pair half-played] → The schedule puts each reverse right after its pair, so at most one pair is unbalanced. A resume completes it.
- [The judge is still biased, so its effective sample size halves] → Accepted: 120 calls for 15 entrants is still 8 opponents each. The judge-health section shows whether splits are common enough to justify the draw-scoring alternative later.
- [Round 2 costs about $3.50, not far under the $5 cap] → Mutation and debate are separate commands with separate budgets, and the debate run's meter still stops cleanly. The nightly change can lower `max_comparisons` if needed.
- [A carried parent's position changes (10 becomes 13), which could confuse reading the records side by side] → `carried_from` and `Lineage.parent_position` both keep the original number, and the report shows both.

## Migration Plan

- Existing records need no migration: every new slot is optional or defaults off.
- `seeker.yaml` gets `mutation: {reworkings: 2}` and `tournament: {max_comparisons: 132, both_orders: true}`.
- Re-rendering the round-1 report adds the judge-health section, which makes the 44/66 novelty skew visible in the committed report.
- Rollback is reverting the branch. Mutated generation files would then fail to load, which is acceptable for an experimental tool.
