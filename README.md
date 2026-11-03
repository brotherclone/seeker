# Seeker

An idea engine for creative tech: random card triples from independent decks, prior-art checks, and adversarial agent debate before anything reaches a human. See [docs/concept.md](docs/concept.md).

## Workflow

Changes go through [OpenSpec](https://github.com/Fission-AI/OpenSpec) (`openspec/`). In Claude Code:

- `/opsx:explore` think a change through
- `/opsx:propose <name>` draft proposal, specs, design and tasks under `openspec/changes/`
- `/opsx:apply` implement the tasks
- `/opsx:archive` merge spec deltas into `openspec/specs/` and file the change

Living specs in `openspec/specs/` are the source of truth for behavior.
