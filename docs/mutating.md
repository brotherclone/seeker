# Mutating survivors

`seeker-mutate` turns the survivors of a finished debate run into the next round: new child ideas plus the survivors themselves, written as an ordinary `Generation` that `seeker-debate` debates and ranks.

```
uv run seeker-mutate debates/2026-11-14-round-1-literal.yaml --dry-run    # every planned draw and prompt; free
uv run seeker-mutate debates/2026-11-14-round-1-literal.yaml --out generations/2026-11-16-round-2-literal.yaml
uv run seeker-debate generations/2026-11-16-round-2-literal.yaml --out debates/2026-11-16-round-2-literal.yaml
uv run seeker-debate report debates/2026-11-16-round-2-literal.yaml
```

One command makes one round. A run whose tournament didn't finish (it stopped at the budget, ran with `--no-tournament`, or was skipped) is refused.

## What each survivor gets

For each survivor, in survivor order:

| Positions | Kind | What it is |
|---|---|---|
| 1-2 | `reworking` | The parent's own three cards. The mutator reads the parent's final statement, its critiques and the advocate's replies, and writes a *different* idea that answers the strongest objection. The second reworking is shown the first and must go elsewhere. |
| 3-4 | `card_swap` | One non-constraint card is replaced by a seeded card from the same deck, once per non-constraint axis. The draw keeps its shape and home field; if the replaced card was the only one listing the home field, the replacement lists it too. No swapped-in card is one already in round 1 or the plan. |

With three survivors that is 12 children. Then the three survivors are **carried** (positions 13-15): copied with a `carried` lineage and no model call. `seeker-debate` copies their debates from the parent run instead of debating them again, so round 2 ranks 15 entrants and shows whether any child beat its parent.

`mutation.reworkings` in `seeker.yaml` sets how many reworkings each parent gets (default 2).

## The mutator

`prompts/mutator.yaml`: Opus 5.5 at high effort, with the generator's persona copied verbatim, so the voice that wrote round 1 writes round 2. It is a separate role file so the generator's digest, pinned by the round-1 generations, never changes. Its output is checked exactly like the generator's: one sentence in the X/Y/Z form, one reading per card of the child's own draw, one retry, then a recorded failure.

## Lineage and reproducibility

- Every child `Idea` carries a `Lineage`: its parent's position in the parent run, its `MutationKind`, and for a swap the axis and the replaced card.
- The mutated `Generation` carries a `MutationOrigin`: the parent run's path and SHA-256, the mutation seed (default: the parent run's tournament seed; set it with `--seed`) and the round number.
- The draws are a pure function of the parent run, the seed and the decks. A resume with a different parent file, seed, mutator file, model or deck set is refused, naming what changed. A resume retries failed children and skips the rest.
- `seeker-debate` checks the parent run against the pinned digest before copying carried debates. Carried debates are not charged to the new run.

## Cost

About $0.60 for 12 Opus mutator calls. Debating the 12 children costs about $1.40, and the two-order tournament about $1.50 (120 judge calls), so a round 2 is about $3.50 in all.
