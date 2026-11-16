# Proposal: mutate-ideas

## Why

The first live debate (`debates/2026-11-14-round-1-literal.yaml`) produced a ranking, and three survivors by promise: #10 (camera obscura evensong), #6 (felled-oak comic) and #3 (drowned-village map). The concept's loop stops there: "winners loop back to the generator for mutation", and survivors should reach Gabe only after several rounds. `debate-ideas` deferred mutation until rankings had been seen. They have now been seen, so mutation is the next step.

The same run showed a position bias that mutation would inherit. The judge picked whichever idea was shown as A on novelty 44 of 66 times, which is very unlikely to be chance. Survivors are chosen on promise (34 of 66, unremarkable), but mutation selects on these ladders round after round, so the bias should be fixed before it compounds.

## What Changes

- **A `mutator` role** (`prompts/mutator.yaml`). It is a versioned role file with the generator's model and persona, plus instructions for turning a debated survivor into a new idea. The generator's own file is unchanged, so round-1 generation records stay resumable.
- **Two kinds of child idea per survivor**, four children in all:
  - two **reworkings**: the mutator reads the survivor's final statement, its critiques and the advocate's replies, and writes a different idea on the same three cards. The second reworking is shown the first and must differ from it in subject or behavior.
  - two **card swaps**: one for each non-constraint card. The card is replaced by a seeded draw from the same deck, and the mutator writes an idea on the new triple, carrying over what survived the debate.
  - With three survivors, that makes 12 children, the size of a round-1 batch.
- **Lineage.** Every child records its parent (the parent run and the parent's position) and how it was made. A mutated `Generation` records the debate run it came from, the mutation seed and its round number.
- **Parents compete again.** The survivors are carried into the mutated generation alongside their children. They keep the debates they already have, so they are not debated or paid for twice. Round 2 then ranks 15 entrants, and the ranking shows whether any child beat its parent.
- **A `seeker-mutate` command.** It reads a finished `DebateRun` and writes a mutated `Generation`. The record is saved after each child and can be resumed. `--dry-run` prints every prompt. `seeker-debate` then debates and ranks the mutated generation unchanged, apart from copying the carried debates. One command makes one round; looping is left to the nightly-run change.
- **The judge sees each pair in both orders.** Each scheduled pair is judged twice, back to back, with A and B swapped. Each judgment is one Elo game, so position bias cancels instead of deciding ratings. `max_comparisons` keeps counting judge calls, so its default rises from 66 to 132 to keep round robin for 12 ideas.
- **The report shows lineage and judge health.** For each entrant, the survivors report shows its parent, how it was made and whether it beat its parent. A judge-health section shows the A-win rate per axis, how many pairs the judge split between the two orders, and the spread of critique severities and defense outcomes.

Agent roles touched: adds `mutator`. The `judge`'s prompt is unchanged, but its schedule doubles. Engine stages touched: adds a mutation stage after the tournament, which feeds back into debate. No deck changes.

## Ontology

- **New classes:**
  - `Lineage`: an idea's parent position, its `MutationKind`, and the swapped axis and replaced card for a swap.
  - `MutationOrigin`: the parent run's path and digest, the mutation seed and the round number.
- **New enum:** `MutationKind`, with the values `reworking`, `card_swap` and `carried`.
- **Altered enum:** `RoleName` gains `mutator`.
- **Altered classes**, each with an optional slot so existing records stay valid:
  - `Idea` gains `lineage`;
  - `Generation` gains `mutation`;
  - `Debate` gains `carried_from`, the position in the parent run a carried debate was copied from;
  - `Tournament` gains `both_orders`, which defaults to false for records written before this change.

## Reproducibility and resumability

- **A mutated `Generation` is pinned like any other:** the mutator's role digest, model, git commit and reading, plus its `MutationOrigin`, which holds the parent run's digest. Its draws are a pure function of the parent run, the mutation seed and the deck set. Replaying them against a changed parent or changed decks is refused.
- **Resume works as it does for generations.** `seeker-mutate` saves after each child. A resume with a different parent digest, seed, role digest, model or deck set is refused, naming the field.
- **Carried debates are byte-for-byte copies** of the parent run's debates, verified against the pinned parent digest. A chain of rounds can be followed back through each record's `MutationOrigin`.
- **The two-order schedule is seeded like the old one.** Ratings are still recomputed exactly from the stored comparisons. A `DebateRun` written before this change replays its single-order schedule.

## Capabilities

### New Capabilities
- `idea-mutation`: the mutator role, the two kinds of mutation, child draws and lineage, carried parents, the mutated generation record and `seeker-mutate`.

### Modified Capabilities
- `idea-tournament`:
  - pairings are judged in both orders, and the default `max_comparisons` becomes 132;
  - the tournament ontology gains `both_orders`;
  - the report gains lineage and judge health.
- `idea-debate`:
  - carried ideas keep their parent's debate instead of being debated again;
  - the debate ontology gains `carried_from`.
- `idea-generation`:
  - the shared ontology gains `lineage` on `Idea`, `mutation` on `Generation` and `mutator` in `RoleName`;
  - config gains the mutation settings.

## Impact

- **Schema:** `schema/seeker.yaml` and the regenerated `schema/generated/`.
- **Code:**
  - `seeker/ontology/`: the new and altered models;
  - a new `seeker/mutate/` package (plan, prompts, mutator, record, CLI);
  - `seeker/debate/`: carried debates in the runner, the two-order schedule, and report sections;
  - `seeker/config.py`: a `mutation` section.
- **Other files:**
  - `prompts/mutator.yaml`;
  - `seeker.yaml`: `mutation` settings, and `tournament.max_comparisons: 132` with `both_orders: true`;
  - `pyproject.toml`: the `seeker-mutate` script.
- **Vault:**
  - new Ontology notes for `Lineage`, `MutationOrigin` and `MutationKind`;
  - updated notes for `Idea`, `Generation`, `Debate`, `Tournament`, `RoleName` and `Role`;
  - a decision note on mutation and two-order judging;
  - a hub update, renaming the planned `mutate-survivors` to `mutate-ideas`.
- **Cost:** a round 2 is estimated at about $3.50, inside the $5 cap:
  - about $0.60 for 12 Opus mutator calls;
  - about $1.40 to debate 12 children;
  - about $1.50 for 120 Sonnet judge calls (60 pairs in both orders, within the 132-call cap);
  - nothing to re-debate the 3 carried parents.
- **Dependencies:** none new.
