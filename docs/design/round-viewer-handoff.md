# Round Viewer: design handoff

A brief for Claude Design: a UI for reading Seeker's round outputs. Attach `round-sample.json` (in this folder). It holds real data from rounds 1–4, so design with it rather than placeholder text.

## What Seeker is

Seeker is an idea engine for creative technology. It draws one card from each of three independent decks, such as *real-time only* + *zoetrope* + *liturgy*. A generator turns each draw into a one-sentence idea in a fixed shape: **"a/an X that does Y because Z"**.

Each idea is then argued over by AI critics:
- a **prosecutor** who searches for prior art;
- a **skeptic** who attacks feasibility;
- a **taste critic** who attacks whether it's interesting;
- an **advocate** who answers each critique and may revise the idea.

A blind **judge** then compares ideas two at a time and keeps three separate Elo ladders: **novelty**, **feasibility** and **promise**. The top three by promise are the round's **survivors**.

Survivors breed the next round. Each gets two *reworkings* (same cards, a new idea that answers its debate) and two *card swaps* (one card replaced), and the survivors themselves are *carried* into the next round to compete against their children. A scheduled job runs one round every other day, about $4.70 a round. Every 3 rounds it pauses until Gabe reviews the survivors and signs off.

## Who uses it, and for what

One person: Gabe, the creator. He's a creative technologist and musician, and he reads closely. He opens it in two moods:

1. **The review** (every 3 rounds, about 30–60 minutes): read the survivors and their debates, see whether mutation is improving things or circling, and decide whether to sign off. This is the main job.
2. **The check-in** (a minute, any morning): did last night's round run, what did it cost, and is anything interesting in the survivors?

Today he reads a long Markdown report per round (`reports/*.md`, about 160 lines). The UI should make a round **scannable in a minute and readable in depth**, and make the **lineage across rounds** visible. The Markdown can't do the second at all.

## Screens to design

### 1. Lineage overview (home)

The story so far, across rounds.
- **One row or column per round:** its date, its cost against the $5 cap, and its three survivors as short labels.
- **The family tree:** which survivor came from which parent, and how (reworking, card swap or carried). Data: `ideas[].lineage` points to `parent_position` in the previous round.
- **Children against parents:** did any child beat its parent? In round 2, 9 of 12 children beat their parent on promise. In round 4, none did: all three survivors were carried round-3 parents.
- **The schedule's state:** last trigger and its outcome (`advanced`, `too_soon`, `awaiting_review`, `budget` or `failed`), next round due, and whether a review is pending. At a review point, this is the first thing on screen.

### 2. Round view

One round, ranked.
- **Survivors first:** the final statement, the three cards, all three ratings, and the lineage label.
- **The rest, ranked by promise,** in a compact form.
- **Ratings stay separate.** Novelty, feasibility and promise are never combined into one score. That's a core rule of the project, so don't show an "overall".
- **Critique severities at a glance** per idea: three critics, each rating `fatal`, `serious` or `minor`. Also show the debate outcome: `defended`, `revised` or `withdrawn` (withdrawn ideas don't compete).
- **Judge health:** a small diagnostic panel. It shows how often the idea shown first won on each axis (50% is ideal), how many pairs got different verdicts when judged in both orders, and how severities spread for each critic. This tells Gabe whether to trust the ranking. Real figures, round 4: novelty 58%, feasibility 50%, promise 56%; 10–12 of 63 pairs split.
- **Prior-art search health:** prosecutions that got results, errors, citations. Round 3 was 10 of 10 with results; rounds 1–2 had search broken, with almost none.

### 3. Idea detail

One idea's whole debate. This is where Gabe reads.
- **The statement:** if the advocate revised it, show the original and the revision.
- **The cards**, each with the generator's reading of it.
- **Each critique:**
  - the critic and its severity;
  - what it attacks (`subject`, `behavior`, `rationale`, `card_reading` or `constraint`);
  - a one-sentence failure, then the full argument;
  - citations, for the prosecutor.
- **The advocate's reply to each critique:** `concede` or `rebut`, with its argument. Pair each reply with its critique visually.
- **Ratings, with a few judge rulings:** one-sentence reasons per axis, as in `full_debate_example.sample_rulings`.
- **Lineage:** the parent idea in the previous round, and the children it produced in the next.

### 4. Review and sign-off (state, not a form, for now)

At a review point, frame what Gabe has to decide: these three survivors, the lineage so far, and the trend in cost and quality. The sign-off itself is a terminal command today:

```
uv run seeker-schedule approve debates/<run>.yaml --note "..."
```

The UI can show the command, with a copy button, plus the `--note` he left last time. An in-UI approve button is a later step.

## The content, honestly

The text is long and dense, and it's the point. Design for reading.

| Text | Median | Max |
|---|---|---|
| Final statement (one sentence) | 56 words | 60 words |
| Critique failure (one sentence) | 30 words | 40 words |
| Critique argument | 118 words | 299 words |
| Advocate reply | 105 words | 188 words |

- Statements are single long sentences, not titles. A list needs a sensible shortened form: the card names, or the "X" clause (`subject`).
- A round has 12–15 ideas. The lineage so far is 4 rounds; plan for 20 or more.
- Card names are short (*Kriegsspiel*, *camera obscura*, *real-time only*). They come from five decks, or axes: technique, medium, historical artifact, constraint, domain. Each draw is one constraint plus two of the other four, so the axis is a useful colour or label.

## Edge cases the data really has

- **Withdrawn ideas:** they have a debate but no ratings (`ratings` are null).
- **Generation failures:** a position with no idea. Round 4 position 7 failed because it was too long after a retry.
- **Carried ideas:** the debate was copied from an earlier round (`debate.carried_from`). Their prosecutor text may say search failed, because those debates ran before the fix. Mark carried debates as inherited.
- **Role failures:** a critic gave no valid answer, so an idea can have only two critiques.
- **A round stopped at the cap:** unfinished, with a partial tournament. It resumes at the next trigger.
- **A round still running,** or a review pending with nothing new to show.

## Constraints

- **Local-first and personal.** It runs on Gabe's Mac and reads the YAML records in `generations/`, `debates/` and `reports/`. No accounts, sharing or multi-user features.
- **No implementation is decided yet:** a static site generated per round, a small local app, or an Obsidian-adjacent view are all possible. Design the screens, not the stack. The data shape in `round-sample.json` is what any of these would read.
- **Desktop first;** check-ins also happen on a phone.
- **Both light and dark.**
- **No existing design system.** Seeker has none yet, so this sets the first visual identity.

## Tone

Seeker's world is a **morphological box**: Zwicky's matrix of independent axes, with cards drawn from decks. Add to that a **tribunal** (prosecutor, skeptic, critic, advocate, judge) and an **evolutionary lineage** (generations, parents, children, survivors).

The ideas themselves are odd, specific and often grave: war memorials, camera obscuras, beehives, Kriegsspiel. The UI should feel like a serious instrument for reading arguments, closer to a well-made research notebook or a court record than a dashboard. Leave out gamification, celebratory confetti and growth-metric styling.

## Out of scope for this pass

- Editing ideas or decks, or starting runs from the UI.
- Approving from the UI (show the command instead).
- The Obsidian vault's own notes (works, cards, decisions).

## What to hand back

- The four screens above at desktop width, and the overview and round view at phone width.
- The visual language: type, colour tokens for light and dark, how severity, outcome, axis and lineage kind are encoded, and the critique–reply pairing pattern.
- How the family tree reads at 4 rounds and at 20.
- Open questions or data the design needs that the sample lacks. For example, if the overview needs a per-round summary that has to be computed, say so.

## Glossary

| Term | Meaning |
|---|---|
| Card | One topic on one axis (deck), e.g. *zoetrope* on historical artifact |
| Draw | The three cards an idea starts from |
| Reading | How literally cards are read: `literal`, `loose` or `metaphorical`. This lineage is literal. |
| Round | One generation of ideas, debated and ranked |
| Survivor | One of the top three by promise. Survivors breed the next round. |
| Reworking, card swap, carried | The three ways a next-round idea relates to its parent |
| Severity | `fatal`, `serious` or `minor`: how bad a critic thinks the flaw is |
| Outcome | `defended`, `revised` or `withdrawn`: how the advocate's defense ended |
| Elo rating | Per-axis score from the blind pairwise judging; 1500 is the starting point |
| Review point | Every 3 rounds. The schedule pauses until Gabe signs off. |
