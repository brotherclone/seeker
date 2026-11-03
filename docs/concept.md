# Idea Engine — Concept

Initial concept, 2026-11-02 · Gabriel Walsh
Living version: https://claude.ai/artifact/AgpFeCWTVwzvMULqvdYwzi

## Premise

The idea engine generates novel creative-technology concepts by colliding random topic cards, checking for prior art, and letting batches of agents argue each idea to death before a human ever sees it. Only ideas that survive several rounds of adversarial debate reach Gabe.

Creative tech is fertile ground because its knowledge is scattered across venues that rarely read each other: NIME and ICMC proceedings, SIGGRAPH, demoscene archives, itch.io, Bandcamp liner notes, patents, and old *Computer Music Journal* issues. Gaps between those silos are where unexplored combinations live.

Unlike science, an idea here only has to be coherent, buildable and interesting, not true. The test is whether it becomes a working patch, instrument, sketch or piece.

## Lineage

The method stacks three known techniques; the novelty is pointing them at creative tech and automating the critique.

| Source | What it contributes |
|---|---|
| Fritz Zwicky's morphological box | Break a problem into independent axes and enumerate combinations across them. The card decks. |
| Don Swanson's literature-based discovery (1986) | Linked fish oil to Raynaud's syndrome by finding two literatures that shared intermediate terms but never cited each other. The prior-art search and bridging terms. |
| Google's AI co-scientist (2025) | Generator, reflection and ranking agents; pairwise debate tournaments scored with Elo; winners mutated and recombined. The adversarial loop. |
| The YouTube Short that started this | Topic cards combined at random, prior research checked, probability that something is there assessed, ideas fed to agent batches that argue for and against. |

## Method

Each idea starts as a triple of cards drawn from separate decks, stated as one concrete claim, then checked against prior art and scored.

**Decks.** Cards live on independent axes so draws aren't noun soup. Starting axes:

| Axis | Example cards |
|---|---|
| Technique | granular synthesis, physical modeling, cellular automata, L-systems |
| Medium / output | tape, LÖVE game, 500-series module, web artifact |
| Historical artifact | Oramics, Telharmonium, Votrax speech chip, Raymond Scott's Electronium |
| Constraint | no screen, 7-bit, real-time only |
| Domain to steal from | mycology, cartography, liturgy, tax law |

**Draws.** Triples, not pairs. Pairs tend to be either obvious or nonsense; the third card, usually a constraint, forces a real idea.

**Idea format.** One sentence: an X that does Y because Z. If it can't be stated in one sentence, it scores zero.

**Prior-art search.** Generate synonyms and adjacent vocabulary for each combination, then search the specialist venues, not just the open web. A search that finds nothing is weak evidence, since the work may exist under other words. Record near-misses with links.

**Scoring.** Separate axes, never one blended number:
- Novelty: how far the nearest prior art is
- Feasibility: buildable with Gabe's actual gear and stack
- Promise: is there something there

**Example draw.** Granular × liturgy × no screen → a call-and-response sampler where the congregation's spoken responses set grain density. Search it, find the closest NIME paper, decide whether the gap is worth taking.

## Agent roles

Adversarial debate loop, 6 roles:

1. **Generator** — draws a card triple, states one concrete claim.
2. **Prior-art prosecutor** — argues it has been done; must cite search results.
3. **Feasibility skeptic** — argues it cannot be built with real gear and time.
4. **Taste critic** — argues it is boring, even if new and buildable.
5. **Advocate** — rebuts all three critics and may revise the idea.
6. **Judge** — blind pairwise comparisons, ranked by Elo. Winners loop back to the generator for mutation; top survivors go to Gabe for review only after several rounds.

Every idea faces three critics with different objections; the advocate's revisions often produce the real idea.

## Failure modes

The biggest risk is consensus collapse: agents on the same model agree politely and the debate becomes theater.

| Failure | Countermeasure |
|---|---|
| Consensus collapse | Mix models and personas per role (e.g. Haiku as a fast, cranky skeptic; Opus as advocate) |
| Judge favors a familiar voice | Blind judging: arguments stripped of who made them |
| Vague critique | Penalize any critique that doesn't name a specific failure |
| Unfalsifiable ideas | Require a one-sentence concrete claim before debate starts |
| False novelty | Prosecutor must cite search results; synonym expansion before searching |
| Noun-soup draws | Separate axes per deck; triples with a constraint card |

## Architecture sketch

A Python orchestrator on the Claude API, with decks and prompts as versioned YAML in git and all run state in SQLite, so runs are resumable and can go overnight.

- `decks/*.yaml`: one file per axis, cards with optional synonyms and tags
- `prompts/*.yaml`: one per role, with model and persona settings
- `engine/`: draw, generate, search, debate, judge, mutate
- `ideas.db` (SQLite): ideas, lineage (parent ideas), debate transcripts, citations, Elo history, run metadata
- `reports/`: top-N survivors per run, written up for human review

Decks and prompts in git matter once prompt tuning starts: every run records the commit it used, so results can be compared across prompt versions. The White chain-agent setup already has much of this plumbing and may be reusable.

## Plan

Run one test batch by hand first to tune decks and prompts, then build the standalone tool.

1. **Workspace.** Local directory and git remote are created. This Claude Project (Seeker) is the design notebook; the repo stays the source of truth for decks, prompts and code.
2. **Seed decks.** About 15 cards per axis, skewed toward Gabe's world.
3. **Test batch.** One generation run with parallel agents: about 12 ideas, debated and ranked, top 3 written up.
4. **Review.** Gabe judges whether the survivors are worth having; adjust decks, roles and scoring.
5. **Standalone tool.** Build the orchestrator from the architecture sketch; resumable overnight runs.

- [ ] Seed decks
- [ ] Draft role prompts
- [ ] Run test batch
- [ ] Review survivors
- [ ] Scaffold orchestrator in the repo

## Open questions

- Which cards are must-haves in the first decks?
- How many debate rounds before an idea counts as a survivor?
- Should promise be judged by agents alone, or does Gabe's taste get encoded as a persona?
- Which search sources can the prosecutor actually reach (NIME archive, arXiv, GitHub, Bandcamp, patents)?
- What's the budget per overnight run?
- Is this a sibling of the White pipeline or fully separate?
