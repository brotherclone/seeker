# Generating ideas

The generator role turns each draw of a batch into one idea: a single sentence of the form "a/an X that does Y because Z", plus how each of the three cards was read.

```
uv run seeker-generate run --seed 7 --dry-run          # see exactly what the model would see; free
uv run seeker-generate run --seed 7 --scratch          # a real run, written to generations/scratch/
uv run seeker-generate run --batch batches/2026-11-04-round-1.yaml --label round-1-literal
```

## Readings

`--reading` sets how freely the cards may be interpreted. It's the one variable round 2 changes.

| Reading | Cards mean… |
|---|---|
| `literal` (default) | exactly what they name |
| `loose` | their spirit as well as their letter |
| `metaphorical` | something they evoke, and the card readings say what |

Only the chosen reading's guidance reaches the prompt. To compare readings fairly, run the same `--batch` file once per reading.

## The role file

`prompts/generator.yaml` is the generator, validated as a `Role`:
- the model;
- the persona;
- the standing rules;
- one guidance text per reading;
- the token limit and temperature.

Edit it freely. Every generation records the file's SHA-256, so each result can be traced to the exact prompt that produced it. Use `--dry-run` to see the rendered prompts before spending anything.

## Records and resume

| Flag | Writes to | Git |
|---|---|---|
| `--label NAME` | `generations/<date>-<NAME>.yaml` | commit it (experiment log) |
| `--out PATH` | anywhere | your call |
| `--scratch` | `generations/scratch/<date>-<seed>-<reading>.yaml` | ignored |

A record embeds the whole draw batch and pins:
- the reading;
- the model;
- the role-file digest;
- the git commit, marked `-dirty` if there were uncommitted changes.

It's rewritten after every draw. If a run is interrupted, rerun the same command: it picks up the record and generates only the missing positions. If the batch, reading, model or role file differ, the rerun is refused rather than mixing inputs.

If an answer is invalid (two sentences, too long, wrong cards), the model is asked once more with the problems listed. If it fails again, the draw is recorded as a failure and the batch moves on. A resume retries failed draws.

## Cost

Every idea and failure records the tokens its calls used, including the retry, split into input, output, cache-read and cache-write tokens. The record's `estimated_cost_usd` prices the total with the table in `seeker.yaml`.

Prices are data, so update them there when they change. A role whose model has no price is refused before any call is made. The system prompt is cached, so draws 2 to 12 mostly read it from the cache.

A 12-draw batch on Opus is estimated at around $0.15.

## The API key

Set `ANTHROPIC_API_KEY`, or put `ANTHROPIC_API_KEY=...` in `.env` next to `seeker.yaml`. That file is git-ignored. Never put the key in `seeker.yaml`: the config refuses it.
