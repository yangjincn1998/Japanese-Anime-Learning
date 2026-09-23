# Japanese Learning

Local Japanese learning database for dictionary imports, subtitle analysis,
word occurrences, and Anki synchronization.

See [Architecture](docs/architecture.md) for the package layout and dependency
rules, and [Database Design](docs/database-design.md) for schema constraints.

The dictionary importer is deterministic. It does not call an LLM or JMdict.
The dictionary portion currently uses these tables:

- `source_deck`: the unique `(level, frequency_class)` pair for each 5mdld deck.
- `word`: one entry per 5mdld source note, linked to its main form and deck.
- `word_form`: canonical lemma/reading pairs belonging to a word.
- `word_form_ruby`: optional per-segment ruby data from JmdictFurigana.
- `dictionary_example`: examples and audio taken directly from 5mdld.

Schema definition and querying use SQLAlchemy 2.0. The importer preallocates
integer IDs and uses Core bulk inserts inside one deferred-foreign-key
transaction to handle the `word.main_form_id <-> word_form.word_id` cycle.

Alembic owns schema upgrades. A fresh import runs `upgrade head` before
inserting data. Existing databases can be upgraded in place.

Each ORM model has a Google-style Chinese docstring, and every table/column has
a SQLAlchemy `comment`. SQLite does not persist `COMMENT` metadata, so the
comments live in the ORM model and Alembic source; databases that support
comments can emit them directly.

Finite string states use `StrEnum` in memory and are stored as TEXT or JSON
strings in SQLite. This applies to POS atoms, JLPT levels, frequency classes,
and example relation types.

## Import

From a complete APKG:

```powershell
uv run japanese-learning import `
  --apkg "C:\path\to\eggrolls-JLPT10k-v3.5.apkg" `
  --output "$HOME\.jlpt-study\jlpt_library.sqlite" `
  --replace
```

The importer also accepts an already extracted `collection.anki21`:

```powershell
uv run japanese-learning import `
  --collection ".work\5mdld\collection.anki21" `
  --output ".work\5mdld\eggrolls-jlpt10k.sqlite" `
  --replace
```

## Query

```powershell
uv run japanese-learning stats `
  --db ".work\5mdld\eggrolls-jlpt10k.sqlite"

uv run japanese-learning lookup `
  --db ".work\5mdld\eggrolls-jlpt10k.sqlite" `
  "出来る"
```

## Migrations

```powershell
uv run japanese-learning db current `
  --db "$HOME\.jlpt-study\jlpt_library.sqlite"

uv run japanese-learning db upgrade `
  --db "$HOME\.jlpt-study\jlpt_library.sqlite"
```

## JmdictFurigana Enhancement

Download a JmdictFurigana release, then replace the derived ruby table:

```powershell
uv run japanese-learning enrich-furigana `
  --db "$HOME\.jlpt-study\jlpt_library.sqlite" `
  --input "C:\path\to\JmdictFurigana.json.zip"
```

Only exact canonical `(lemma, reading)` matches are imported. Forms without a
match retain no ruby data. JmdictFurigana is derived from JMdict and carries the
same attribution and ShareAlike requirements.

## Formatting

Black is installed as a development dependency. Run it after Python changes:

```powershell
uv run black src tests
```
