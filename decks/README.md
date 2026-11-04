# Decks

Every idea starts as a draw of one card from each of several decks. Each file here holds one **axis** of the morphological box, and the axes are independent, so any card can combine with any other.

| File | Axis | What it contributes |
|---|---|---|
| `technique.yaml` | technique | How something is made |
| `medium.yaml` | medium | What it ends up as |
| `historical-artifact.yaml` | historical-artifact | A real machine or work to resurrect or misread |
| `constraint.yaml` | constraint | A hard limit the idea can visibly fail |
| `domain.yaml` | domain | A field outside the arts to steal structure from |

These five axes are required. To add another, create a new `<axis>.yaml` file.

The format is defined by the `Deck` and `Card` classes in [`schema/seeker.yaml`](../schema/seeker.yaml), which is the ontology of record.

## A card, annotated

```yaml
axis: technique                  # must match the file name (technique.yaml)
name: Technique
description: How something is made, as a process, algorithm or craft method.
cards:
  - id: granular-synthesis       # CardId: kebab-case, unique across ALL decks
    name: granular synthesis     # as it appears in prompts and reports
    synonyms:                    # other communities' words for it; these drive
      - microsound               #   prior-art search, so use real search terms.
      - grain cloud              #   Must not repeat the name or each other.
    fields: [music]              # CreativeField values; omit for cross-cutting
    tags: [demoscene]            # optional free labels (kebab-case)
    note: Grains of 1-100 ms.    # optional: what the card means or excludes
```

Only `id` and `name` are required. Any slot not listed above is rejected.

## Creative fields

`fields` is drawn from a fixed vocabulary:

- `music`
- `visual-art`
- `film`
- `electronics`
- `writing`
- `comics`
- `games` (board, card and electronic)

A card can list several fields. Cards that span fields, such as cellular automata (music, visual art and games), are the most valuable: they're the bridges between literatures that don't read each other. A card with no fields applies to every field.

The four core decks each keep at least three cards per field, and `tests/test_seed_decks.py` checks this.

## Validating

```
uv run seeker-decks validate
```

This prints each axis with its card count and digest, then the digest of the whole deck set. Every error from every file is reported in one run, naming the file, the card and the slot. Use `--dir` to point at another directory.

A digest changes when any card or the card order changes. Comments, formatting and key order don't affect it. Runs will record the deck-set digest next to the git commit they used.

For a second, schema-only check of each file:

```
uv run linkml-validate -s schema/seeker.yaml -C Deck decks/*.yaml
```

## Rules the schema can't express

These are checked by `seeker-decks`:

- Each file's `axis` matches its file name.
- All five required axes are present.
- Card ids are unique across every deck. A concept that belongs on two axes needs two ids, such as `tape` and `phonogene`.

## Drawing

```
uv run seeker-draw batch --seed 7 --size 12
```

Every draw is a **triple**: one `constraint` card plus cards from two of technique, medium, historical-artifact and domain. That gives six shapes. The constraint is always there because it's the card that forces a real idea.

A batch is **balanced, not filtered**:

- **Shapes:** each of the six appears equally often, give or take one, so 12 draws use each shape twice.
- **Cards:** no card repeats within a batch.
- **Home fields:** each draw has a home field that rotates through the seven creative fields, and at least one of its cards lists it.

Within those rules, which cards land together is uniform, so odd collisions are as likely as tame ones.

### Seeds and replay

A batch is fully determined by its **seed**, the **deck content** and the **size**. Leave out `--seed` and one is chosen and printed, so you can always reproduce what you saw. The random stream is SHA-256 based, so a seed draws the same batch on every Python version. If you edit any card, the deck-set digest changes, and replaying an old batch fails with an error naming both digests rather than silently drawing something else.

### Capacity

No-repeat sets a ceiling on batch size. For these decks it's **30**, because `domain` has 15 cards and appears in half the draws. Asking for more fails with an error naming the limit.

### Which batches to keep

```
uv run seeker-draw batch --seed 7 --out batches/2026-11-03-round-1.yaml   # keep: commit it
uv run seeker-draw batch --scratch                                         # throwaway
```

- **Commit** batches that feed a real run to `batches/YYYY-MM-DD-<label>.yaml`. They're tiny, and together they form the experiment log: each one pins its seed and deck-set digest, sitting in git next to the deck and prompt commits that produced it.
- **Explore** with `--scratch`, which writes `batches/scratch/<seed>.yaml`. That folder is gitignored. If a scratch draw turns out to matter, redraw its seed with `--out` before you edit the decks.
