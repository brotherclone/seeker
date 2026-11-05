# Works in the vault

Seeker's prior art lives in your Obsidian vault. Each work you come across (a record, an instrument, a game, a paper) is one note, with frontmatter shaped like the LinkML `Work` class and links to the cards it embodies. `seeker-works` validates those notes, suggests card links, keeps one note per deck card in step with the decks, and checks draws against the catalog before anything is spent on web search.

## Setup

Point Seeker at the vault in the git-ignored `.env` beside `seeker.yaml`:

```
SEEKER_VAULT=~/Documents/Claude/Projects/Bracers/Projects
```

The order of precedence is:
1. `SEEKER_VAULT` in the environment;
2. `SEEKER_VAULT` in `.env`;
3. `paths.vault` in `seeker.yaml`, which stays `null` in the repo.

The folders inside the vault are a shared convention in `seeker.yaml`:

```yaml
vault_folders:
  works: Seeker/Works
  cards: Seeker/Cards
```

With no vault set, every `seeker-works` command stops with a message naming `SEEKER_VAULT` and touches nothing.

## Card notes

```
uv run seeker-works sync-cards
```

This writes one note per deck card to `Seeker/Cards/<card-id>.md`. Run it again whenever the decks change.

What Seeker owns in a card note:
- the frontmatter keys `type`, `card_id`, `axis`, `fields`, `tags` and `aliases`;
- the text between `<!-- seeker:card -->` and `<!-- /seeker:card -->`.

Everything else is yours: other properties (a `rating`, say), and anything you write above or below the block. A resync rewrites only what Seeker owns, writes a note only when it changed, and never deletes a note, even for a card that has left the decks. A card note whose frontmatter isn't valid YAML is skipped and reported, never overwritten.

`aliases` holds the card's name and synonyms, so `[[microsound]]` and `[[granular synthesis]]` both resolve to `granular-synthesis.md`.

## Capturing a work

1. In the Obsidian Web Clipper, go to **Settings → Templates → Import** and choose `capture/seeker-work.clipper.json`.
2. On a page you want to keep, clip it with the **Seeker work** template. The note lands in `Seeker/Works`.
   - The template fills in `title`, `url`, `creators` (the page author, as a wikilink), `year` (the published date) and `summary` (the page description).
   - It sets `type: work`, `kind: other`, `captured_by: gabe` and today's `captured_on`.
   - The Clipper's interpreter writes three sentences about the work into the body. That gives card matching more to go on.
3. Fix `kind` by hand if `other` is wrong: `piece`, `recording`, `instrument`, `software`, `game`, `publication`, `performance`, `installation`, `paper` or `product`.

A work note looks like this:

```markdown
---
type: work
title: Oramics demo tape
creators: ["[[Daphne Oram]]"]
year: 1962
url: https://daphneoram.org/
kind: recording
fields: [music]
cards: ["[[oramics]]", "[[tape]]"]
summary: Daphne Oram demonstrating drawn sound.
captured_by: gabe
captured_on: 2026-11-05
---
Anything you like.
```

The work's id comes from the file name, so `Oramics demo tape (1962).md` is `oramics-demo-tape-1962`. `cards` and `creators` take plain values or wikilinks (`[[x]]` or `[[x|label]]`), and empty values count as absent. Properties that aren't `Work` slots are yours and are ignored.

## Linking cards

```
uv run seeker-works suggest
uv run seeker-works suggest --apply
```

`suggest` looks for every card's name and synonyms in each work's title, summary and body, and lists the cards the work doesn't link yet.
- Matches are whole words, ignore case, and treat hyphens and spaces alike, so "Karplus Strong" finds `karplus-strong`.
- Single-word terms of three characters or fewer (`FDN`, `SMF`) only match in their exact case.

Read the list, then run `--apply` to add the suggestions to `cards` as wikilinks. Only the `cards` lines of the note change.

## Validating

```
uv run seeker-works validate
```

This prints the number of works and the catalog digest, or every problem at once, each naming the note and the property: bad frontmatter, an unknown card, or two notes that reduce to the same id. The digest covers the `Work` fields only, so editing a note's body never changes it.

## Checking draws

```
uv run seeker-works check --batch batches/2026-11-04-round-1.yaml
```

For every draw, this lists the works that already link two of its three cards (`[2 of 3]`) or all of them (`[all 3]`). A draw with no overlap says `no prior art in the vault`. The prosecutor will read this before it searches the web.

## Caveats

- Seeker rewrites only the frontmatter keys it changes, so the formatting and comments on your other lines survive. A key it does rewrite comes out in PyYAML's style, and any comment on that key's own lines is lost.
- A vault synced through iCloud or similar can show half-written files. Those notes are reported as problems rather than crashing the command; run it again once sync settles.
