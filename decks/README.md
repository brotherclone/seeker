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
seeker-decks validate
```

This prints each axis with its card count and digest, then the digest of the whole deck set. Every error from every file is reported in one run, naming the file, the card and the slot. Use `--dir` to point at another directory.

A digest changes when any card or the card order changes. Comments, formatting and key order don't affect it. Runs will record the deck-set digest next to the git commit they used.

For a second, schema-only check of each file:

```
linkml-validate -s schema/seeker.yaml -C Deck decks/*.yaml
```

## Rules the schema can't express

These are checked by `seeker-decks`:

- Each file's `axis` matches its file name.
- All five required axes are present.
- Card ids are unique across every deck. A concept that belongs on two axes needs two ids, such as `tape` and `phonogene`.
