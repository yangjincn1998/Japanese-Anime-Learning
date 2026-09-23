# Architecture

This repository is the standalone Japanese learning project extracted from
`skills-development`. It owns the local learning database, subtitle analysis
workflow, and future Anki synchronization bridge.

## Repository Layout

```text
japanese-learning/
  pyproject.toml
  alembic.ini
  src/
    japanese_learning/
      migrations/
  tests/
    unit/
    integration/
    contract/
    e2e/
  docs/
```

`src/` contains importable Python code only. Tests mirror the production code
by test type:

- `tests/unit` tests pure functions, value objects, and policies.
- `tests/integration` uses temporary SQLite databases and real adapters.
- `tests/contract` verifies JSONL, subtitle, APKG, and external adapter
  contracts.
- `tests/e2e` exercises a public CLI or Skill entrypoint.

## Dependency Direction

The target dependency direction follows Clean Architecture:

```text
entrypoints -> application -> domain
                    |
                    v
                  ports
                    ^
                    |
                 adapters
```

Rules:

- `domain` must not import SQLAlchemy, Alembic, Anki, LLM, or CLI code.
- `application` coordinates use cases and depends only on `domain` and
  `ports`.
- `adapters` implement ports using SQLAlchemy, files, AnkiConnect, or model
  clients.
- `entrypoints` parse input, invoke an application use case, and format output.
- `bootstrap` is the composition root and is the only place that wires
  concrete adapters to use cases.

This project is intentionally not implementing a full DDD system. Domain code
is introduced only for real rules and decisions such as:

- directory/deck tree correspondence;
- analysis root selection;
- occurrence identity and deduplication;
- home deck selection;
- Anki note create, append, move, and skip decisions.

## Migration Sequence

The package was first moved to a `src/` layout without changing database
behavior. The next refactors should be kept separate:

1. Split the ORM into dictionary, learning, and Anki modules.
2. Introduce application services for dictionary import and analysis.
3. Introduce ports and repository adapters.
4. Move deterministic domain policies out of persistence code.
5. Add contract and end-to-end tests before external Anki or LLM integration.

No schema migration is required merely to change source layout or import paths.
