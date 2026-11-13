# Seeker

An idea engine for creative tech: random card triples from independent decks, prior-art checks, and adversarial agent debate before anything reaches a human. See [docs/concept.md](docs/concept.md).

## Setup

Seeker uses [uv](https://docs.astral.sh/uv/), which installs the right Python (pinned in `.python-version`) and every dependency from `uv.lock`:

```
brew install uv          # or: curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync                  # creates .venv with Python 3.13, Seeker and the dev tools
uv run pytest            # the test suite
```

Run any Seeker command through `uv run` (for example `uv run seeker-draw batch --seed 7`), or activate `.venv` first and drop the prefix. `make setup|test|lint|validate|schema` wraps the common ones.

For real model calls, put `ANTHROPIC_API_KEY=...` in `.env`, which is git-ignored. To use the works catalog, add `SEEKER_VAULT=/path/to/your/vault` there too (see [docs/works.md](docs/works.md)).

The pipeline:
- `seeker-draw` draws card triples;
- `seeker-generate` turns each triple into an idea ([docs/generating.md](docs/generating.md));
- `seeker-debate` puts the ideas through critics, an advocate and a blind tournament, and reports the survivors ([docs/debating.md](docs/debating.md)).

## Workflow

Changes go through [OpenSpec](https://github.com/Fission-AI/OpenSpec) (`openspec/`). In Claude Code:

- `/opsx:explore` think a change through
- `/opsx:propose <name>` draft proposal, specs, design and tasks under `openspec/changes/`
- `/opsx:apply` implement the tasks
- `/opsx:archive` merge spec deltas into `openspec/specs/` and file the change

Living specs in `openspec/specs/` are the source of truth for behavior.
