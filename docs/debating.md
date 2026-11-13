# Debating ideas

`seeker-debate` puts every idea of a recorded generation through one round of adversarial debate, then ranks the survivors in a blind tournament.

```
uv run seeker-debate generations/2026-11-04-round-1-literal.yaml --dry-run      # every prompt and the planned calls; free
uv run seeker-debate generations/2026-11-04-round-1-literal.yaml --scratch      # a real run, written to debates/scratch/
uv run seeker-debate generations/2026-11-04-round-1-literal.yaml --out debates/2026-11-12-round-1-literal.yaml
uv run seeker-debate report debates/2026-11-12-round-1-literal.yaml             # reports/2026-11-12-round-1-literal.md
```

`run` is the default command, so `seeker-debate GENERATION` and `seeker-debate run GENERATION` are the same.

## The roles

Each idea faces three critics, who never see each other, and then the advocate. The judge compares debated ideas two at a time. Every role is a file in `prompts/`, validated as a `Role`. Each run records every file's SHA-256.

| Role | Model | Argues | Why this model |
|---|---|---|---|
| `prosecutor` | Sonnet 5.5, medium | It has been done | Good at searching, and cheaper than Opus across a run's searches |
| `skeptic` | Haiku 5.5, medium | It can't be built with Gabe's gear, stack and time | Fast and blunt, in a different voice from Opus |
| `taste_critic` | Sonnet 5.5, high | It's boring | Needs judgment, but is kept off the generator's own model |
| `advocate` | Opus 5.5, high | Answers each critique, then defends, revises or withdraws the idea | Revisions often produce the real idea |
| `judge` | Sonnet 5.5, high | Picks A or B on novelty, feasibility and promise | Not the generator's model, to limit self-preference |

No two critics may share both model and persona, and every role's model must be in the price table. Either problem stops the run before any call.

The skeptic's gear list and the taste critic's persona are Gabe's own. Edit them in `prompts/` as the setup or taste changes; each run records the new digest.

## Named failures

Every critique names:
- the part of the idea that fails: `subject`, `behavior`, `rationale`, `card_reading` (with the card) or `constraint`;
- a severity: `fatal`, `serious` or `minor`;
- the failure, in one sentence.

These rules are checked in code:
- **The failure is one sentence of 8 to 40 words.** "This might be hard to build" is too short to name anything.
- **It says something the idea doesn't.** It is rejected when its content words overlap the statement's by 70% or more, or when it adds no word beyond the statement and the card names.
- **A `card_reading` target names a card from the draw.**

A rejected answer is sent back once with the problems listed. A second failure is recorded as a `DebateFailure`.

The advocate must answer every critique exactly once. If it concedes a `fatal` critique, it can't keep the idea as stated: it must revise or withdraw. A revision keeps the "a/an X that does Y because Z" form and the draw's three cards. It's checked by the generator's own sentence rules, and it may not name a card from outside the draw. A revised idea competes in its revised form, and the record keeps the original.

## The prosecutor: catalog first, then search

Before searching, the prosecutor is shown every captured work in the vault that links two or more of the draw's cards (`seeker-works check`). It then runs up to `max_searches` web searches (3 by default) with Claude's server-side search tool.

Every prior-art critique must do one of two things:
- cite evidence: a search result by its exact URL, or a catalog work by its id;
- declare `none_found`, with no citations and severity `minor`.

A URL that wasn't among that call's search results is rejected, so it can't invent precedent.

Each cited URL that isn't already in the catalog becomes a new note in `Works/` with:
- `captured_by: prosecutor`;
- `kind: other`;
- `cards` limited to the draw's cards that the citation names.

Existing notes are never touched. A taken file name gets ` (2)`. A URL the catalog already has is cited by its work id instead. Later ideas in the same run see the new works. Gabe can find every one by `captured_by: prosecutor`.

The vault comes from `SEEKER_VAULT`, as for `seeker-works`. A real run needs it. A dry run without it shows the prosecutor an empty catalog.

## Budget and resume

A run writes its `DebateRun` record after every debate and every comparison, so `--out` or `--scratch` is required.

| Flag | Writes to | Git |
|---|---|---|
| `--out PATH` | anywhere (`debates/` for runs worth keeping) | commit runs you keep |
| `--scratch` | `debates/scratch/<date>-<generation>.yaml` | ignored |

Before each debate and each comparison, the run checks its estimated spend against the budget. The budget is `budget_usd` in `seeker.yaml` (default $5), or `--budget`. At the budget it stops cleanly, records `stop_reason: budget`, and exits with status 3. The overshoot is at most one debate, about $0.40.

Rerun the same command with a higher `--budget` to continue. Resuming is refused, naming the field, if any of these changed:
- the generation file;
- any role file;
- the seed.

The works catalog is allowed to change, because the run's own captures change it.

`--no-tournament` debates every idea and stops before ranking. Running again without the flag starts the tournament from the saved record.

## The tournament and survivors

- **Who competes.** Ideas whose debate ended `defended` or `revised`. Withdrawn ideas, and ideas whose advocate failed, sit out.
- **Blind.** The judge sees two ideas labelled only A and B, each with its objections in a seeded shuffled order and the replies to them. Role names, models, personas and severities are stripped. Severities are self-reported, and the judge should read the arguments, not count labels.
- **Pairings.** A round robin while it fits in `tournament.max_comparisons` (66 by default: 12 ideas). Above that, every idea gets the same number of seeded opponents, with no pair repeated. The tournament seed sets the pairing, the A/B order and the objection order. It defaults to the generation's batch seed; set it with `--seed`.
- **Ratings.** One Elo ladder per axis: novelty, feasibility and promise. Every idea starts at 1500 and K is 32. The axes are never blended. Ratings can be recomputed exactly from the stored comparisons. A failed comparison changes nothing.
- **Survivors.** The top three by promise rating, with ties broken by promise wins, then position.

## The report

`seeker-debate report RUN` writes `reports/<run>.md` without calling any model. It holds:
- each survivor, with its three ratings and its cards, its original statement if it was revised, and every critique with the advocate's reply and linked citations;
- a table of the rest, by promise;
- the ideas that weren't ranked, and why;
- the run's provenance and cost.

## Cost

Each critique, defense, failure and comparison records its model and token usage, including web searches. The run's `estimated_cost_usd` prices each one at its own model's rates, plus $0.01 per search.

Each search pulls about 39k input tokens of results into the prosecutor's call, so the prosecutor is the biggest cost: about $0.10 to $0.25 per idea. A 12-idea run is estimated at $2.50 to $4.50, under the $5 budget. To spend less, lower `max_searches` in `prompts/prosecutor.yaml`.
